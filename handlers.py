import math
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
import dateparser
from datetime import datetime
import database as db

router = Router()

# --- Клавиатуры ---
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Заметки", callback_data="list_note_1")
    kb.button(text="💾 Медиа", callback_data="list_media_1")
    return kb.as_markup()

def pagination_kb(page, total_pages, prefix):
    kb = InlineKeyboardBuilder()
    if page > 1: kb.button(text="⬅️", callback_data=f"{prefix}_{page-1}")
    kb.button(text=f"{page}/{total_pages}", callback_data="ignore")
    if page < total_pages: kb.button(text="➡️", callback_data=f"{prefix}_{page+1}")
    kb.row(InlineKeyboardButton(text="🔙 Меню", callback_data="menu"))
    return kb.as_markup()

def item_kb(item_id, item_type):
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"del_{item_type}_{item_id}")
    kb.button(text="🔙 Назад", callback_data=f"list_{item_type}_1")
    return kb.as_markup()

# --- Хендлеры ---

@router.message(CommandStart())
async def start(msg: Message):
    await db.add_user(msg.from_user.id, msg.from_user.username)
    await msg.answer("Привет! Пришли мне текст для заметки или файл (фото/видео).", reply_markup=main_menu())

@router.callback_query(F.data == "menu")
async def back_menu(cb: CallbackQuery):
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu())

# 1. Обработка текста (Заметки + Напоминания)
@router.message(F.text)
async def handle_text(msg: Message):
    note_id = await db.add_note(msg.from_user.id, msg.text)
    response = "✅ Заметка сохранена."
    
    # Парсинг даты
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()})
    if dt and dt > datetime.now():
        await db.add_reminder(msg.from_user.id, note_id, dt)
        response += f"\n⏰ Напомню: {dt.strftime('%d.%m.%Y %H:%M')}"
    
    await msg.answer(response, reply_markup=main_menu())

# 2. Обработка медиа
@router.message(F.photo | F.video | F.document)
async def handle_media(msg: Message):
    f_id, f_type = None, None
    if msg.photo:
        f_id, f_type = msg.photo[-1].file_id, "photo"
    elif msg.video:
        f_id, f_type = msg.video.file_id, "video"
    elif msg.document:
        f_id, f_type = msg.document.file_id, "document"
    
    await db.add_media(msg.from_user.id, f_id, f_type, msg.caption or "")
    await msg.answer("💾 Файл сохранен!", reply_markup=main_menu())

# 3. Списки (Пагинация)
@router.callback_query(F.data.startswith("list_"))
async def show_list(cb: CallbackQuery):
    _, type_, page = cb.data.split("_")
    page = int(page)
    limit = 5
    
    if type_ == "note":
        items, count = await db.get_notes_page(cb.from_user.id, page, limit)
        text_header = "📝 Ваши заметки:"
    else:
        items, count = await db.get_media_page(cb.from_user.id, page, limit)
        text_header = "💾 Ваши файлы:"

    total_pages = math.ceil(count / limit) or 1
    
    kb = InlineKeyboardBuilder()
    for item in items:
        if type_ == "note":
            preview = item.content[:25] + "..."
            kb.row(InlineKeyboardButton(text=preview, callback_data=f"view_note_{item.id}"))
        else:
            caption = item.caption if item.caption else "Файл без имени"
            icon = {"photo": "🖼", "video": "🎥", "document": "📁"}.get(item.file_type, "❓")
            kb.row(InlineKeyboardButton(text=f"{icon} {caption[:20]}", callback_data=f"view_media_{item.id}"))
            
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, total_pages, f"list_{type_}")))
    await cb.message.edit_text(text_header, reply_markup=kb.as_markup())

# 4. Просмотр элемента
@router.callback_query(F.data.startswith("view_"))
async def view_item(cb: CallbackQuery):
    _, type_, item_id = cb.data.split("_")
    item_id = int(item_id)
    
    if type_ == "note":
        note = await db.get_note(item_id)
        if note:
            await cb.message.edit_text(f"📝 {note.created_at.strftime('%d.%m')}\n\n{note.content}", reply_markup=item_kb(note.id, "note"))
    else:
        media = await db.get_media(item_id)
        if media:
            caption = f"{media.caption}\n📅 {media.created_at.strftime('%d.%m')}" if media.caption else ""
            await cb.message.delete() # Удаляем меню, шлем медиа
            method = {"photo": cb.message.answer_photo, "video": cb.message.answer_video, "document": cb.message.answer_document}[media.file_type]
            await method(media.file_id, caption=caption, reply_markup=item_kb(media.id, "media"))

# 5. Удаление
@router.callback_query(F.data.startswith("del_"))
async def delete_item_handler(cb: CallbackQuery):
    _, type_, item_id = cb.data.split("_")
    await db.delete_item(type_, int(item_id))
    
    if type_ == "media": await cb.message.delete()
    
    await cb.message.answer("🗑 Удалено.", reply_markup=main_menu())
