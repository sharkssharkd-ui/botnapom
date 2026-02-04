import math
import dateparser
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db

router = Router()

# --- Состояния ---
class BotState(StatesGroup):
    searching = State()
    editing = State()
    setting_reminder = State()

# --- Клавиатуры ---
def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📝 Заметки", callback_data="list_note_1"),
           InlineKeyboardButton(text="💾 Медиа", callback_data="list_media_1"))
    kb.row(InlineKeyboardButton(text="🔍 Поиск", callback_data="search_start"),
           InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return kb.as_markup()

def pagination_kb(page, total_pages, prefix):
    kb = InlineKeyboardBuilder()
    if page > 1: kb.button(text="⬅️", callback_data=f"{prefix}_{page-1}")
    kb.button(text=f"{page}/{total_pages}", callback_data="ignore")
    if page < total_pages: kb.button(text="➡️", callback_data=f"{prefix}_{page+1}")
    kb.row(InlineKeyboardButton(text="🔙 В меню", callback_data="menu"))
    return kb.as_markup()

def note_control_kb(note_id, is_pinned):
    kb = InlineKeyboardBuilder()
    pin_text = "🔓 Открепить" if is_pinned else "📌 Закрепить"
    
    kb.row(InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_note_{note_id}"),
           InlineKeyboardButton(text=pin_text, callback_data=f"pin_note_{note_id}"))
    
    kb.row(InlineKeyboardButton(text="⏰ Напомнить", callback_data=f"remind_note_{note_id}"),
           InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_note_{note_id}"))
           
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="list_note_1"))
    return kb.as_markup()

def media_control_kb(media_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"del_media_{media_id}")
    kb.button(text="🔙 Назад", callback_data="list_media_1")
    return kb.as_markup()

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_action")]])

# --- Старт и Меню ---
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    await db.add_user(msg.from_user.id, msg.from_user.username)
    await msg.answer("👋 Привет! Я твой личный помощник.\n\n"
                     "✏️ Пиши текст -> я сохраню заметку.\n"
                     "🖼 Шли фото/файл -> я сохраню медиа.\n"
                     "📅 Пиши дату в тексте -> поставлю напоминание.", reply_markup=main_menu_kb())

@router.callback_query(F.data == "menu")
async def back_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu_kb())
    await cb.answer()

@router.callback_query(F.data == "cancel_action")
async def cancel_action(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Действие отменено.", reply_markup=main_menu_kb())
    await cb.answer()

@router.callback_query(F.data == "profile")
async def show_profile(cb: CallbackQuery):
    n, m = await db.get_stats(cb.from_user.id)
    text = (f"👤 <b>Ваш профиль:</b>\n\n"
            f"📝 Всего заметок: {n}\n"
            f"💾 Всего файлов: {m}\n"
            f"🆔 Ваш ID: {cb.from_user.id}")
    await cb.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "ignore")
async def ignore_click(cb: CallbackQuery):
    await cb.answer()

# --- Логика Заметок (Добавление, Просмотр) ---

@router.message(F.text, StateFilter(None))
async def handle_new_note(msg: Message):
    note_id = await db.add_note(msg.from_user.id, msg.text)
    
    # Авто-парсинг напоминания
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()})
    
    response = "✅ Заметка сохранена."
    if dt and dt > datetime.now():
        await db.add_reminder(msg.from_user.id, note_id, dt)
        response += f"\n⏰ Напоминание: {dt.strftime('%d.%m.%Y %H:%M')}"
    
    await msg.answer(response, reply_markup=main_menu_kb())

@router.callback_query(F.data.startswith("list_note_"))
async def list_notes(cb: CallbackQuery):
    page = int(cb.data.split("_")[-1])
    notes, count = await db.get_notes_page(cb.from_user.id, page)
    total_pages = math.ceil(count / 5) or 1
    
    kb = InlineKeyboardBuilder()
    for note in notes:
        pin_icon = "📌 " if note.is_pinned else ""
        preview = note.content[:25].replace("\n", " ") + "..."
        kb.row(InlineKeyboardButton(text=f"{pin_icon}{preview}", callback_data=f"view_note_{note.id}"))
    
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, total_pages, "list_note")))
    await cb.message.edit_text(f"📝 Ваши заметки (Всего: {count}):", reply_markup=kb.as_markup())
    await cb.answer()

@router.callback_query(F.data.startswith("view_note_"))
async def view_note(cb: CallbackQuery):
    note_id = int(cb.data.split("_")[-1])
    note = await db.get_note(note_id)
    if not note:
        await cb.answer("Заметка не найдена", show_alert=True)
        return
    
    text = f"📝 <b>Заметка от {note.created_at.strftime('%d.%m %H:%M')}</b>\n\n{note.content}"
    if note.is_pinned: text = "📌 " + text
    
    await cb.message.edit_text(text, reply_markup=note_control_kb(note.id, note.is_pinned), parse_mode="HTML")
    await cb.answer()

# --- Расширенные функции заметок (Пин, Редакт, Напоминание) ---

@router.callback_query(F.data.startswith("pin_note_"))
async def pin_note_handler(cb: CallbackQuery):
    note_id = int(cb.data.split("_")[-1])
    new_state = await db.toggle_pin(note_id)
    status = "📌 Закреплено" if new_state else "🔓 Откреплено"
    await cb.answer(status)
    # Обновляем вид
    await view_note(cb)

@router.callback_query(F.data.startswith("edit_note_"))
async def edit_note_start(cb: CallbackQuery, state: FSMContext):
    note_id = int(cb.data.split("_")[-1])
    await state.update_data(note_id=note_id)
    await state.set_state(BotState.editing)
    await cb.message.edit_text("✏️ Отправьте новый текст для заметки:", reply_markup=back_kb())
    await cb.answer()

@router.message(BotState.editing)
async def edit_note_finish(msg: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_note_text(data['note_id'], msg.text)
    await state.clear()
    await msg.answer("✅ Заметка обновлена!", reply_markup=main_menu_kb())

@router.callback_query(F.data.startswith("remind_note_"))
async def remind_note_start(cb: CallbackQuery, state: FSMContext):
    note_id = int(cb.data.split("_")[-1])
    await state.update_data(note_id=note_id)
    await state.set_state(BotState.setting_reminder)
    await cb.message.edit_text("⏰ Напишите дату и время для напоминания (например: 'завтра в 10' или 'через 20 минут'):", reply_markup=back_kb())
    await cb.answer()

@router.message(BotState.setting_reminder)
async def remind_note_finish(msg: Message, state: FSMContext):
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()})
    
    if not dt or dt < datetime.now():
        await msg.answer("❌ Не смог распознать время или оно в прошлом. Попробуйте еще раз:", reply_markup=back_kb())
        return

    data = await state.get_data()
    await db.add_reminder(msg.from_user.id, data['note_id'], dt)
    await state.clear()
    await msg.answer(f"✅ Напоминание установлено на {dt.strftime('%d.%m.%Y %H:%M')}", reply_markup=main_menu_kb())

# --- Поиск ---
@router.callback_query(F.data == "search_start")
async def search_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.searching)
    await cb.message.edit_text("🔍 Введите текст для поиска:", reply_markup=back_kb())
    await cb.answer()

@router.message(BotState.searching)
async def search_process(msg: Message, state: FSMContext):
    await state.clear()
    notes, count = await db.get_notes_page(msg.from_user.id, 1, limit=10, search_query=msg.text)
    
    if not notes:
        await msg.answer("🔍 Ничего не найдено.", reply_markup=main_menu_kb())
        return

    kb = InlineKeyboardBuilder()
    for note in notes:
        preview = note.content[:30] + "..."
        kb.row(InlineKeyboardButton(text=preview, callback_data=f"view_note_{note.id}"))
    kb.row(InlineKeyboardButton(text="🔙 В меню", callback_data="menu"))
    
    await msg.answer(f"🔍 Найдено {count} заметок:", reply_markup=kb.as_markup())

# --- Медиа ---
@router.message(F.photo | F.video | F.document, StateFilter(None))
async def handle_media(msg: Message):
    f_id, f_type = None, None
    if msg.photo: f_id, f_type = msg.photo[-1].file_id, "photo"
    elif msg.video: f_id, f_type = msg.video.file_id, "video"
    elif msg.document: f_id, f_type = msg.document.file_id, "document"
    
    await db.add_media(msg.from_user.id, f_id, f_type, msg.caption or "")
    await msg.answer("💾 Файл сохранен!", reply_markup=main_menu_kb())

@router.callback_query(F.data.startswith("list_media_"))
async def list_media(cb: CallbackQuery):
    page = int(cb.data.split("_")[-1])
    medias, count = await db.get_media_page(cb.from_user.id, page)
    total_pages = math.ceil(count / 5) or 1
    
    kb = InlineKeyboardBuilder()
    for m in medias:
        icon = {"photo": "🖼", "video": "🎥", "document": "📁"}.get(m.file_type, "❓")
        cap = m.caption if m.caption else "Без названия"
        kb.row(InlineKeyboardButton(text=f"{icon} {cap[:20]}", callback_data=f"view_media_{m.id}"))
        
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, total_pages, "list_media")))
    await cb.message.edit_text(f"💾 Ваши файлы (Всего: {count}):", reply_markup=kb.as_markup())
    await cb.answer()

@router.callback_query(F.data.startswith("view_media_"))
async def view_media(cb: CallbackQuery):
    m_id = int(cb.data.split("_")[-1])
    media = await db.get_media(m_id)
    if not media: return await cb.answer("Файл удален", show_alert=True)
    
    await cb.message.delete()
    caption = f"{media.caption or ''}\n📅 {media.created_at.strftime('%d.%m %H:%M')}"
    
    method = {"photo": cb.message.answer_photo, "video": cb.message.answer_video, "document": cb.message.answer_document}[media.file_type]
    await method(media.file_id, caption=caption, reply_markup=media_control_kb(media.id))
    await cb.answer()

# --- Удаление ---
@router.callback_query(F.data.startswith("del_"))
async def delete_handler(cb: CallbackQuery):
    _, type_, item_id = cb.data.split("_")
    await db.delete_item(type_, int(item_id))
    if type_ == "media": await cb.message.delete()
    await cb.message.answer("🗑 Удалено.", reply_markup=main_menu_kb())
    await cb.answer()
