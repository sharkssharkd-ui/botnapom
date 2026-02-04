import os
import sys

# Структура проекта и содержимое файлов
PROJECT_STRUCTURE = {
    ".env": """BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DB_NAME=bot_database.db
""",

    "requirements.txt": """aiogram>=3.0.0
sqlalchemy>=2.0.0
aiosqlite>=0.19.0
python-dotenv>=1.0.0
dateparser>=1.1.8
apscheduler>=3.10.0
""",

    "main.py": """import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.database.core import init_db, session_maker
from bot.middlewares.db import DbSessionMiddleware
from bot.handlers import common, notes, media
from bot.services.scheduler import start_scheduler

load_dotenv()

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token or "YOUR_BOT_TOKEN" in bot_token:
        logging.error("Пожалуйста, укажите корректный BOT_TOKEN в файле .env")
        return

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Инициализация БД
    await init_db()

    # Middleware
    dp.update.middleware(DbSessionMiddleware(session_maker))

    # Роутеры
    dp.include_router(common.router)
    dp.include_router(notes.router)
    dp.include_router(media.router)

    # Планировщик напоминаний
    scheduler = start_scheduler(bot, session_maker)

    try:
        logging.info("Бот запущен...")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
""",

    "bot/__init__.py": "",
    "bot/database/__init__.py": "",
    "bot/handlers/__init__.py": "",
    "bot/keyboards/__init__.py": "",
    "bot/middlewares/__init__.py": "",
    "bot/services/__init__.py": "",

    "bot/database/core.py": """from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os

DB_NAME = os.getenv("DB_NAME", "bot_database.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False)
session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Раскомментировать для сброса БД
        await conn.run_sync(Base.metadata.create_all)
""",

    "bot/database/models.py": """from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.sql import func
from bot.database.core import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Media(Base):
    __tablename__ = "media"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    file_id = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # photo, video, document
    caption = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False)
    is_sent = Column(Boolean, default=False)
""",

    "bot/database/requests.py": """from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import User, Note, Media, Reminder
from datetime import datetime

async def add_user(session: AsyncSession, telegram_id: int, username: str):
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        session.add(User(telegram_id=telegram_id, username=username))
        await session.commit()

async def add_note(session: AsyncSession, telegram_id: int, content: str) -> Note:
    note = Note(user_id=telegram_id, content=content)
    session.add(note)
    await session.commit()
    return note

async def get_notes(session: AsyncSession, telegram_id: int, page: int = 1, limit: int = 5):
    offset = (page - 1) * limit
    result = await session.execute(
        select(Note).where(Note.user_id == telegram_id).order_by(Note.created_at.desc()).limit(limit).offset(offset)
    )
    return result.scalars().all()

async def get_notes_count(session: AsyncSession, telegram_id: int):
    result = await session.execute(select(func.count(Note.id)).where(Note.user_id == telegram_id))
    return result.scalar()

async def get_note_by_id(session: AsyncSession, note_id: int):
    return await session.get(Note, note_id)

async def delete_note(session: AsyncSession, note_id: int):
    await session.execute(delete(Note).where(Note.id == note_id))
    await session.commit()

async def add_reminder(session: AsyncSession, note_id: int, remind_at: datetime):
    session.add(Reminder(note_id=note_id, remind_at=remind_at))
    await session.commit()

async def get_pending_reminders(session: AsyncSession):
    now = datetime.now()
    result = await session.execute(
        select(Reminder, Note)
        .join(Note, Reminder.note_id == Note.id)
        .where(Reminder.is_sent == False, Reminder.remind_at <= now)
    )
    return result.all()

async def mark_reminder_sent(session: AsyncSession, reminder_id: int):
    await session.execute(update(Reminder).where(Reminder.id == reminder_id).values(is_sent=True))
    await session.commit()

# --- Media ---
async def add_media(session: AsyncSession, telegram_id: int, file_id: str, file_type: str, caption: str = None):
    session.add(Media(user_id=telegram_id, file_id=file_id, file_type=file_type, caption=caption))
    await session.commit()

async def get_media_list(session: AsyncSession, telegram_id: int, page: int = 1, limit: int = 5):
    offset = (page - 1) * limit
    result = await session.execute(
        select(Media).where(Media.user_id == telegram_id).order_by(Media.created_at.desc()).limit(limit).offset(offset)
    )
    return result.scalars().all()

async def get_media_count(session: AsyncSession, telegram_id: int):
    result = await session.execute(select(func.count(Media.id)).where(Media.user_id == telegram_id))
    return result.scalar()

async def get_media_by_id(session: AsyncSession, media_id: int):
    return await session.get(Media, media_id)

async def delete_media(session: AsyncSession, media_id: int):
    await session.execute(delete(Media).where(Media.id == media_id))
    await session.commit()

from sqlalchemy import func
""",

    "bot/middlewares/db.py": """from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_maker):
        super().__init__()
        self.session_maker = session_maker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with self.session_maker() as session:
            data["session"] = session
            return await handler(event, data)
""",

    "bot/keyboards/builders.py": """from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Заметки", callback_data="notes_list_1")
    builder.button(text="📷 Фото/Файлы", callback_data="media_list_1")
    builder.button(text="⚙️ Настройки", callback_data="settings")
    builder.adjust(2, 1)
    return builder.as_markup()

def pagination_kb(current_page, total_pages, prefix):
    builder = InlineKeyboardBuilder()
    
    # Кнопки элементов (если нужно, можно добавить выбор элемента тут)
    
    # Навигация
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_list_{current_page - 1}"))
    
    buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_list_{current_page + 1}"))
        
    builder.row(*buttons)
    builder.row(InlineKeyboardButton(text="🔙 В меню", callback_data="main_menu"))
    return builder.as_markup()

def item_control_kb(item_id, item_type):
    # item_type: 'note' or 'media'
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"delete_{item_type}_{item_id}")
    builder.button(text="🔙 Назад", callback_data=f"{item_type}s_list_1")
    return builder.as_markup()
""",

    "bot/services/date_parser.py": """import dateparser
from datetime import datetime

def parse_date_from_text(text: str) -> datetime | None:
    # Используем dateparser для поиска даты и времени
    # Настройки для русского языка
    settings = {
        'PREFER_DATES_FROM': 'future',
        'RELATIVE_BASE': datetime.now(),
        'RETURN_AS_TIMEZONE_AWARE': False # Простой вариант без TimeZone для SQLite
    }
    
    # Пытаемся найти дату
    # В реальном проекте можно использовать search_dates для извлечения,
    # но здесь просто проверим, есть ли явная дата в начале или сам текст является датой
    dt = dateparser.parse(text, languages=['ru', 'en'], settings=settings)
    
    if dt and dt > datetime.now():
        return dt
    return None
""",

    "bot/services/scheduler.py": """from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.database.requests import get_pending_reminders, mark_reminder_sent
from aiogram import Bot
import logging

async def check_reminders_job(bot: Bot, session_maker):
    async with session_maker() as session:
        reminders = await get_pending_reminders(session)
        for reminder, note in reminders:
            try:
                text = f"⏰ <b>Напоминание!</b>\\n\\n{note.content}"
                await bot.send_message(chat_id=note.user_id, text=text, parse_mode="HTML")
                await mark_reminder_sent(session, reminder.id)
            except Exception as e:
                logging.error(f"Не удалось отправить напоминание {reminder.id}: {e}")

def start_scheduler(bot: Bot, session_maker):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_reminders_job, "interval", minutes=1, args=[bot, session_maker])
    scheduler.start()
    return scheduler
""",

    "bot/handlers/common.py": """from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.requests import add_user
from bot.keyboards.builders import main_menu_kb

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    await add_user(session, message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Привет! Я бот для заметок и медиа.\\n"
        "Просто отправь мне текст для заметки или файл для сохранения.\\n"
        "Если в тексте будет дата (например, 'завтра в 15:00'), я поставлю напоминание.",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "settings")
async def settings_handler(callback: CallbackQuery):
    await callback.answer("Настройки пока не реализованы (можно добавить часовой пояс и т.д.)", show_alert=True)
""",

    "bot/handlers/notes.py": """import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import requests as db
from bot.services.date_parser import parse_date_from_text
from bot.keyboards.builders import main_menu_kb, pagination_kb, item_control_kb

router = Router()

# --- Добавление заметки (любой текст, если это не команда) ---
@router.message(F.text & ~F.text.startswith("/"))
async def text_note_handler(message: Message, session: AsyncSession):
    # Сохраняем заметку
    note = await db.add_note(session, message.from_user.id, message.text)
    
    response = "✅ Заметка сохранена."
    
    # Проверка на дату для напоминания
    remind_date = parse_date_from_text(message.text)
    if remind_date:
        await db.add_reminder(session, note.id, remind_date)
        response += f"\\n⏰ Установлено напоминание на: {remind_date.strftime('%d.%m.%Y %H:%M')}"
    
    await message.reply(response, reply_markup=main_menu_kb())

# --- Список заметок ---
@router.callback_query(F.data.startswith("notes_list_"))
async def list_notes(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split("_")[-1])
    limit = 5
    
    notes = await db.get_notes(session, callback.from_user.id, page, limit)
    count = await db.get_notes_count(session, callback.from_user.id)
    total_pages = math.ceil(count / limit) or 1
    
    text = f"📝 <b>Ваши заметки (Стр. {page}/{total_pages}):</b>\\n\\n"
    
    builder = InlineKeyboardBuilder()
    
    if not notes:
        text += "Список пуст."
    else:
        for note in notes:
            preview = (note.content[:30] + '...') if len(note.content) > 30 else note.content
            # Добавляем кнопку для каждой заметки
            builder.row(InlineKeyboardButton(text=f"📄 {preview}", callback_data=f"view_note_{note.id}"))
    
    # Добавляем навигацию снизу
    nav_kb = pagination_kb(page, total_pages, "notes")
    builder.attach(InlineKeyboardBuilder.from_markup(nav_kb))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# --- Просмотр одной заметки ---
@router.callback_query(F.data.startswith("view_note_"))
async def view_note(callback: CallbackQuery, session: AsyncSession):
    note_id = int(callback.data.split("_")[-1])
    note = await db.get_note_by_id(session, note_id)
    
    if not note:
        await callback.answer("Заметка не найдена", show_alert=True)
        return

    text = f"📝 <b>Заметка #{note.id}</b>\\n\\n{note.content}\\n\\n📅 {note.created_at.strftime('%d.%m.%Y %H:%M')}"
    await callback.message.edit_text(text, reply_markup=item_control_kb(note.id, "note"), parse_mode="HTML")

# --- Удаление заметки ---
@router.callback_query(F.data.startswith("delete_note_"))
async def delete_note_handler(callback: CallbackQuery, session: AsyncSession):
    note_id = int(callback.data.split("_")[-1])
    await db.delete_note(session, note_id)
    await callback.answer("Заметка удалена!")
    # Возврат к списку
    await list_notes(callback, session) # Рекурсивный вызов, но с callback.data нужно быть осторожным. 
    # Проще просто вызвать обновление сообщения:
    # Имитируем нажатие на первую страницу
    callback.data = "notes_list_1"
    await list_notes(callback, session)
""",

    "bot/handlers/media.py": """import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import requests as db
from bot.keyboards.builders import main_menu_kb, pagination_kb, item_control_kb

router = Router()

# --- Добавление медиа ---
@router.message(F.photo | F.video | F.document)
async def media_handler(message: Message, session: AsyncSession):
    file_id = None
    file_type = None
    caption = message.caption or ""

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"

    if file_id:
        await db.add_media(session, message.from_user.id, file_id, file_type, caption)
        await message.reply("💾 Медиафайл сохранен!", reply_markup=main_menu_kb())

# --- Список медиа ---
@router.callback_query(F.data.startswith("media_list_"))
async def list_media(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split("_")[-1])
    limit = 5
    
    medias = await db.get_media_list(session, callback.from_user.id, page, limit)
    count = await db.get_media_count(session, callback.from_user.id)
    total_pages = math.ceil(count / limit) or 1
    
    text = f"📷 <b>Ваши файлы (Стр. {page}/{total_pages}):</b>\\n\\n"
    builder = InlineKeyboardBuilder()
    
    icon_map = {"photo": "🖼", "video": "🎥", "document": "📁"}
    
    if not medias:
        text += "Список пуст."
    else:
        for media in medias:
            cap = media.caption if media.caption else "Без названия"
            preview = (cap[:20] + '...') if len(cap) > 20 else cap
            icon = icon_map.get(media.file_type, "❓")
            builder.row(InlineKeyboardButton(text=f"{icon} {preview}", callback_data=f"view_media_{media.id}"))
            
    nav_kb = pagination_kb(page, total_pages, "media")
    builder.attach(InlineKeyboardBuilder.from_markup(nav_kb))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# --- Просмотр медиа ---
@router.callback_query(F.data.startswith("view_media_"))
async def view_media(callback: CallbackQuery, session: AsyncSession):
    media_id = int(callback.data.split("_")[-1])
    media = await db.get_media_by_id(session, media_id)
    
    if not media:
        await callback.answer("Файл не найден", show_alert=True)
        return

    # Удаляем предыдущее меню (текст), отправляем медиа
    await callback.message.delete()
    
    caption = f"{media.caption}\\n📅 {media.created_at.strftime('%d.%m.%Y')}" if media.caption else f"📅 {media.created_at.strftime('%d.%m.%Y')}"
    kb = item_control_kb(media.id, "media")

    if media.file_type == "photo":
        await callback.message.answer_photo(media.file_id, caption=caption, reply_markup=kb)
    elif media.file_type == "video":
        await callback.message.answer_video(media.file_id, caption=caption, reply_markup=kb)
    elif media.file_type == "document":
        await callback.message.answer_document(media.file_id, caption=caption, reply_markup=kb)

# --- Удаление медиа ---
@router.callback_query(F.data.startswith("delete_media_"))
async def delete_media_handler(callback: CallbackQuery, session: AsyncSession):
    media_id = int(callback.data.split("_")[-1])
    await db.delete_media(session, media_id)
    
    # Поскольку мы отправляли новое сообщение с медиа, нам нужно удалить его и отправить меню
    await callback.message.delete()
    await callback.message.answer("🗑 Медиафайл удален.", reply_markup=main_menu_kb())
    # Можно сразу открыть список, но message.answer удобнее здесь, так как контекст медиа потерян
"""
}

def create_structure():
    print("🚀 Начинаю создание структуры проекта...")
    
    for path, content in PROJECT_STRUCTURE.items():
        # Если путь содержит директории, создаем их
        if "/" in path:
            directory = os.path.dirname(path)
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"📁 Создана папка: {directory}")
        
        # Записываем файл
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            print(f"📄 Создан файл: {path}")

    print("\\n✅ Проект успешно создан!")
    print("="*40)
    print("Следующие шаги:")
    print("1. Откройте файл .env и вставьте ваш BOT_TOKEN.")
    print("2. Установите зависимости: pip install -r requirements.txt")
    print("3. Запустите бота: python main.py")
    print("="*40)

if __name__ == "__main__":
    create_structure()