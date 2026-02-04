import math
import dateparser
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, BufferedInputFile
from aiogram.filters import CommandStart, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db

router = Router()

# --- Состояния ---
class BotState(StatesGroup):
    searching = State()
    editing = State()
    setting_reminder = State()

# --- Новое Reply Меню (снизу) ---
def main_reply_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📝 Мои заметки"),
        KeyboardButton(text="💾 Мои файлы")
    )
    builder.row(
        KeyboardButton(text="🔍 Поиск"),
        KeyboardButton(text="👤 Профиль")
    )
    return builder.as_markup(resize_keyboard=True)

# --- Inline Клавиатуры ---
def pagination_kb(page, total_pages, prefix):
    kb = InlineKeyboardBuilder()
    if page > 1: kb.button(text="⬅️", callback_data=f"{prefix}_{page-1}")
    kb.button(text=f"{page}/{total_pages}", callback_data="ignore")
    if page < total_pages: kb.button(text="➡️", callback_data=f"{prefix}_{page+1}")
    return kb.as_markup()

def note_control_kb(note_id, is_pinned):
    kb = InlineKeyboardBuilder()
    pin_text = "🔓 Открепить" if is_pinned else "📌 Закрепить"
    kb.row(InlineKeyboardButton(text="✏️ Изм.", callback_data=f"edit_note_{note_id}"),
           InlineKeyboardButton(text=pin_text, callback_data=f"pin_note_{note_id}"))
    kb.row(InlineKeyboardButton(text="⏰ Напомнить", callback_data=f"remind_note_{note_id}"),
           InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_note_{note_id}"))
    kb.row(InlineKeyboardButton(text="🔙 К списку", callback_data="list_note_1"))
    return kb.as_markup()

def media_control_kb(media_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"del_media_{media_id}")
    kb.button(text="🔙 К списку", callback_data="list_media_1")
    return kb.as_markup()

def profile_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Скачать все заметки (Backup)", callback_data="export_notes")
    return kb.as_markup()

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_action")]])

# --- Старт и Инструкция ---
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    await db.add_user(msg.from_user.id, msg.from_user.username)
    
    text = (
        "<b>👋 Привет! Добро пожаловать в NoteBot v3.0</b>\n\n"
        "Я умею хранить твои мысли и файлы. Меню управления находится снизу 👇\n\n"
        "<b>📚 Как пользоваться:</b>\n"
        "• <b>Текст:</b> Просто отправь мне любое сообщение, и я сохраню его как заметку.\n"
        "• <b>Файлы:</b> Отправь фото, видео, документ или голосовое — я сохраню его в раздел 'Файлы'.\n"
        "• <b>Напоминания:</b> Напиши дату внутри текста (например: <i>'Купить молоко завтра в 18:00'</i>) или добавь напоминание вручную через меню заметки.\n"
        "• <b>Закреп:</b> Важные заметки можно закрепить сверху списка.\n"
        "• <b>Бэкап:</b> В разделе 'Профиль' можно скачать все свои записи одним файлом.\n\n"
        "<i>Начни прямо сейчас! 👇</i>"
    )
    await msg.answer(text, reply_markup=main_reply_menu(), parse_mode="HTML")

# --- Обработка кнопок нижнего меню ---
@router.message(F.text == "📝 Мои заметки")
async def btn_notes(msg: Message):
    # Вызываем функцию списка (переиспользуем логику)
    # Создаем фейковый callback для удобства, или просто пишем логику
    await show_notes_list(msg, msg.from_user.id, 1)

@router.message(F.text == "💾 Мои файлы")
async def btn_media(msg: Message):
    await show_media_list(msg, msg.from_user.id, 1)

@router.message(F.text == "👤 Профиль")
async def btn_profile(msg: Message):
    n, m = await db.get_stats(msg.from_user.id)
    text = (f"👤 <b>Ваш профиль:</b>\n\n"
            f"📝 Заметок: {n}\n"
            f"💾 Файлов: {m}\n"
            f"🆔 ID: {msg.from_user.id}")
    await msg.answer(text, reply_markup=profile_kb(), parse_mode="HTML")

@router.message(F.text == "🔍 Поиск")
async def btn_search(msg: Message, state: FSMContext):
    await state.set_state(BotState.searching)
    await msg.answer("🔍 Введите текст для поиска:", reply_markup=cancel_kb())

# --- Экспорт ---
@router.callback_query(F.data == "export_notes")
async def export_handler(cb: CallbackQuery):
    await cb.answer("⏳ Собираю файл...")
    data = await db.get_all_notes_text(cb.from_user.id)
    
    if len(data) < 50: # Если заметок нет или очень мало
        await cb.message.answer("У вас пока нет заметок для экспорта.")
        return

    # Создаем файл в памяти
    file_bytes = data.encode('utf-8')
    input_file = BufferedInputFile(file_bytes, filename=f"notes_backup_{datetime.now().strftime('%Y%m%d')}.txt")
    
    await cb.message.answer_document(input_file, caption="✅ Ваши заметки выгружены.")

# --- Общая логика отмены ---
@router.callback_query(F.data == "cancel_action")
async def cancel_action(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.delete()
    await cb.message.answer("Действие отменено.", reply_markup=main_reply_menu())

# --- Логика Заметок ---
async def show_notes_list(target, user_id, page):
    notes, count = await db.get_notes_page(user_id, page)
    total_pages = math.ceil(count / 5) or 1
    
    kb = InlineKeyboardBuilder()
    for note in notes:
        pin = "📌 " if note.is_pinned else ""
        prev = note.content[:25].replace("\n", " ") + "..."
        kb.row(InlineKeyboardButton(text=f"{pin}{prev}", callback_data=f"view_note_{note.id}"))
    
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, total_pages, "list_note")))
    
    text = f"📝 Страница {page} из {total_pages} (Всего: {count})"
    # target может быть Message или CallbackQuery.message
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb.as_markup())
    else:
        await target.edit_text(text, reply_markup=kb.as_markup())

@router.message(F.text, StateFilter(None))
async def handle_new_note(msg: Message):
    # Игнорируем нажатия меню, если они вдруг просочились
    if msg.text in ["📝 Мои заметки", "💾 Мои файлы", "🔍 Поиск", "👤 Профиль"]: return

    note_id = await db.add_note(msg.from_user.id, msg.text)
    
    # Парсинг
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()})
    resp = "✅ Заметка сохранена."
    if dt and dt > datetime.now():
        await db.add_reminder(msg.from_user.id, note_id, dt)
        resp += f"\n⏰ Напомню: {dt.strftime('%d.%m %H:%M')}"
    
    await msg.answer(resp) # Не дублируем меню, оно и так внизу

@router.callback_query(F.data.startswith("list_note_"))
async def cb_list_notes(cb: CallbackQuery):
    page = int(cb.data.split("_")[-1])
    await show_notes_list(cb.message, cb.from_user.id, page)
    await cb.answer()

@router.callback_query(F.data.startswith("view_note_"))
async def view_note(cb: CallbackQuery):
    note_id = int(cb.data.split("_")[-1])
    note = await db.get_note(note_id)
    if not note: return await cb.answer("Заметка не найдена", show_alert=True)
    
    text = f"📝 <b>Заметка</b> ({note.created_at.strftime('%d.%m %H:%M')})\n\n{note.content}"
    if note.is_pinned: text = "📌 " + text
    await cb.message.edit_text(text, reply_markup=note_control_kb(note.id, note.is_pinned), parse_mode="HTML")
    await cb.answer()

# --- Логика Медиа (включая Voice) ---
@router.message(F.photo | F.video | F.document | F.voice, StateFilter(None))
async def handle_media(msg: Message):
    f_id, f_type = None, None
    if msg.photo: f_id, f_type = msg.photo[-1].file_id, "photo"
    elif msg.video: f_id, f_type = msg.video.file_id, "video"
    elif msg.document: f_id, f_type = msg.document.file_id, "document"
    elif msg.voice: f_id, f_type = msg.voice.file_id, "voice"
    
    await db.add_media(msg.from_user.id, f_id, f_type, msg.caption or "")
    await msg.answer("💾 Сохранено в 'Мои файлы'!")

async def show_media_list(target, user_id, page):
    medias, count = await db.get_media_page(user_id, page)
    total_pages = math.ceil(count / 5) or 1
    
    kb = InlineKeyboardBuilder()
    icon_map = {"photo": "🖼", "video": "🎥", "document": "📁", "voice": "🎤"}
    
    for m in medias:
        icon = icon_map.get(m.file_type, "❓")
        cap = m.caption if m.caption else (f"Голосовое" if m.file_type == "voice" else "Файл")
        kb.row(InlineKeyboardButton(text=f"{icon} {cap[:20]}", callback_data=f"view_media_{m.id}"))
        
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, total_pages, "list_media")))
    text = f"💾 Файлы (Стр. {page}/{total_pages})"
    
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb.as_markup())
    else:
        await target.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("list_media_"))
async def cb_list_media(cb: CallbackQuery):
    page = int(cb.data.split("_")[-1])
    await show_media_list(cb.message, cb.from_user.id, page)
    await cb.answer()

@router.callback_query(F.data.startswith("view_media_"))
async def view_media(cb: CallbackQuery):
    m_id = int(cb.data.split("_")[-1])
    media = await db.get_media(m_id)
    if not media: return await cb.answer("Файл удален", show_alert=True)
    
    await cb.message.delete()
    caption = f"{media.caption or ''}\n📅 {media.created_at.strftime('%d.%m %H:%M')}"
    
    kb = media_control_kb(media.id)
    if media.file_type == "photo": await cb.message.answer_photo(media.file_id, caption=caption, reply_markup=kb)
    elif media.file_type == "video": await cb.message.answer_video(media.file_id, caption=caption, reply_markup=kb)
    elif media.file_type == "document": await cb.message.answer_document(media.file_id, caption=caption, reply_markup=kb)
    elif media.file_type == "voice": await cb.message.answer_voice(media.file_id, caption=caption, reply_markup=kb)
    await cb.answer()

# --- Редактирование и поиск ---
@router.callback_query(F.data.startswith("pin_note_"))
async def pin_handler(cb: CallbackQuery):
    await db.toggle_pin(int(cb.data.split("_")[-1]))
    await view_note(cb) # Перезагружаем заметку

@router.callback_query(F.data.startswith("del_"))
async def del_handler(cb: CallbackQuery):
    _, type_, i_id = cb.data.split("_")
    await db.delete_item(type_, int(i_id))
    if type_ == "media": await cb.message.delete()
    else: await cb.message.edit_text("🗑 Удалено")
    await cb.answer("Удалено")

@router.callback_query(F.data.startswith("edit_note_"))
async def edit_start(cb: CallbackQuery, state: FSMContext):
    await state.update_data(nid=int(cb.data.split("_")[-1]))
    await state.set_state(BotState.editing)
    await cb.message.answer("✏️ Введите новый текст:", reply_markup=cancel_kb())
    await cb.answer()

@router.message(BotState.editing)
async def edit_finish(msg: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_note_text(data['nid'], msg.text)
    await state.clear()
    await msg.answer("✅ Сохранено!")
    await show_notes_list(msg, msg.from_user.id, 1)

@router.callback_query(F.data.startswith("remind_note_"))
async def remind_start(cb: CallbackQuery, state: FSMContext):
    await state.update_data(nid=int(cb.data.split("_")[-1]))
    await state.set_state(BotState.setting_reminder)
    await cb.message.answer("⏰ Когда напомнить? (например: 'через 15 мин' или 'завтра 9:00')", reply_markup=cancel_kb())
    await cb.answer()

@router.message(BotState.setting_reminder)
async def remind_finish(msg: Message, state: FSMContext):
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()})
    if not dt or dt < datetime.now():
        return await msg.answer("❌ Не понял время. Попробуй еще раз или жми Отмена.")
    
    data = await state.get_data()
    await db.add_reminder(msg.from_user.id, data['nid'], dt)
    await state.clear()
    await msg.answer(f"✅ Напомню {dt.strftime('%d.%m %H:%M')}")

@router.message(BotState.searching)
async def search_run(msg: Message, state: FSMContext):
    await state.clear()
    notes, count = await db.get_notes_page(msg.from_user.id, 1, limit=10, search_query=msg.text)
    if not notes: return await msg.answer("🔍 Ничего не нашел.")
    
    kb = InlineKeyboardBuilder()
    for n in notes: kb.row(InlineKeyboardButton(text=n.content[:30]+"...", callback_data=f"view_note_{n.id}"))
    await msg.answer(f"🔍 Нашел {count} шт:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "ignore")
async def ignore(cb: CallbackQuery): await cb.answer()
