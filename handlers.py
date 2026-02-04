import math
import dateparser
import pytz # <--- ТАЙМЗОНЫ
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters import CommandStart, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db

router = Router()
MSK_TZ = pytz.timezone('Europe/Moscow') # ЖЕСТКО ЗАДАЕМ МОСКВУ

class BotState(StatesGroup):
    searching = State()
    editing = State()
    setting_reminder = State()
    choosing_repeat = State() # Новое состояние для выбора повтора

def main_reply_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📝 Мои заметки"), KeyboardButton(text="💾 Мои файлы"))
    builder.row(KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="👤 Профиль"))
    return builder.as_markup(resize_keyboard=True)

def pagination_kb(page, total_pages, prefix):
    kb = InlineKeyboardBuilder()
    if page > 1: kb.button(text="⬅️", callback_data=f"{prefix}_{page-1}")
    kb.button(text=f"{page}/{total_pages}", callback_data="ignore")
    if page < total_pages: kb.button(text="➡️", callback_data=f"{prefix}_{page+1}")
    return kb.as_markup()

def note_control_kb(note_id, is_pinned):
    kb = InlineKeyboardBuilder()
    pin = "🔓" if is_pinned else "📌"
    kb.row(InlineKeyboardButton(text="✏️ Изм.", callback_data=f"edit_note_{note_id}"),
           InlineKeyboardButton(text=pin, callback_data=f"pin_note_{note_id}"))
    kb.row(InlineKeyboardButton(text="⏰ Напомнить", callback_data=f"remind_note_{note_id}"),
           InlineKeyboardButton(text="🗑", callback_data=f"del_note_{note_id}"))
    kb.row(InlineKeyboardButton(text="🔙 К списку", callback_data="list_note_1"))
    return kb.as_markup()

def media_control_kb(media_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"del_media_{media_id}")
    kb.button(text="🔙 К списку", callback_data="list_media_1")
    return kb.as_markup()

def repeat_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Нет", callback_data="repeat_none")
    kb.button(text="🔁 Каждый день", callback_data="repeat_daily")
    kb.button(text="📅 Каждую неделю", callback_data="repeat_weekly")
    kb.adjust(1)
    return kb.as_markup()

def profile_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎲 Случайная заметка", callback_data="random_note")
    kb.button(text="📥 Скачать всё (Backup)", callback_data="export_notes")
    kb.adjust(1)
    return kb.as_markup()

def cancel_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_action")]])

# --- Start ---
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    await db.add_user(msg.from_user.id, msg.from_user.username)
    await msg.answer("👋 <b>Bot v4.0 Ultimate</b>\n\nЯ запоминаю всё.\nЖми кнопки внизу!", reply_markup=main_reply_menu(), parse_mode="HTML")

# --- Главное меню ---
@router.message(F.text == "📝 Мои заметки")
async def btn_notes(msg: Message): await show_notes_list(msg, msg.from_user.id, 1)

@router.message(F.text == "💾 Мои файлы")
async def btn_media(msg: Message): await show_media_list(msg, msg.from_user.id, 1)

@router.message(F.text == "👤 Профиль")
async def btn_profile(msg: Message):
    n, m, r = await db.get_stats(msg.from_user.id)
    await msg.answer(f"👤 <b>Статистика:</b>\n📝 Заметок: {n}\n💾 Файлов: {m}\n⏰ Напоминаний: {r}\n🌍 Время: Москва (UTC+3)", reply_markup=profile_kb(), parse_mode="HTML")

@router.message(F.text == "🔍 Поиск")
async def btn_search(msg: Message, state: FSMContext):
    await state.set_state(BotState.searching)
    await msg.answer("🔍 Введите текст или #хештег:", reply_markup=cancel_kb())

# --- ХЕШТЕГИ (Обработка клика по тегу) ---
@router.message(F.text.startswith("#"))
async def hashtag_search(msg: Message):
    # Если пользователь нажал на хештег в тексте, Телеграм отправляет сообщение с хештегом
    await search_engine(msg, msg.text)

# --- Добавление заметки ---
@router.message(F.text, StateFilter(None))
async def handle_new_note(msg: Message):
    if msg.text in ["📝 Мои заметки", "💾 Мои файлы", "🔍 Поиск", "👤 Профиль"]: return
    
    note_id = await db.add_note(msg.from_user.id, msg.text)
    
    # Авто-дата (МСК)
    now_msk = datetime.now(MSK_TZ).replace(tzinfo=None)
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now_msk})
    
    resp = "✅ Сохранено."
    if dt and dt > now_msk:
        await db.add_reminder(msg.from_user.id, note_id, dt)
        resp += f"\n⏰ Напомню: {dt.strftime('%d.%m %H:%M')}"
    
    await msg.answer(resp)

# --- Списки ---
async def show_notes_list(target, user_id, page):
    notes, count = await db.get_notes_page(user_id, page)
    total_pages = math.ceil(count / 5) or 1
    kb = InlineKeyboardBuilder()
    for n in notes:
        pin = "📌 " if n.is_pinned else ""
        kb.row(InlineKeyboardButton(text=f"{pin}{n.content[:25]}...", callback_data=f"view_note_{n.id}"))
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, total_pages, "list_note")))
    
    text = f"📝 Заметки ({count} шт)"
    if isinstance(target, Message): await target.answer(text, reply_markup=kb.as_markup())
    else: await target.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("list_note_"))
async def cb_list_notes(cb: CallbackQuery):
    await show_notes_list(cb.message, cb.from_user.id, int(cb.data.split("_")[-1]))
    await cb.answer()

@router.callback_query(F.data.startswith("view_note_"))
async def view_note(cb: CallbackQuery):
    nid = int(cb.data.split("_")[-1])
    note = await db.get_note(nid)
    if not note: return await cb.answer("Удалено", show_alert=True)
    text = f"📝 {note.created_at.strftime('%d.%m %H:%M')}\n\n{note.content}"
    if note.is_pinned: text = "📌 " + text
    await cb.message.edit_text(text, reply_markup=note_control_kb(note.id, note.is_pinned))

# --- Напоминания с повтором ---
@router.callback_query(F.data.startswith("remind_note_"))
async def remind_start(cb: CallbackQuery, state: FSMContext):
    await state.update_data(nid=int(cb.data.split("_")[-1]))
    await state.set_state(BotState.setting_reminder)
    await cb.message.answer("⏰ Напиши время (например 'завтра 9:00'):", reply_markup=cancel_kb())
    await cb.answer()

@router.message(BotState.setting_reminder)
async def remind_time_received(msg: Message, state: FSMContext):
    now_msk = datetime.now(MSK_TZ).replace(tzinfo=None)
    dt = dateparser.parse(msg.text, settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now_msk})
    
    if not dt or dt < now_msk:
        return await msg.answer("❌ Время в прошлом или непонятно.")
    
    await state.update_data(dt=dt) # Сохраняем время во временное хранилище
    await state.set_state(BotState.choosing_repeat) # Переходим к выбору повтора
    await msg.answer(f"⏰ Время: {dt.strftime('%d.%m %H:%M')}.\n\nПовторять это напоминание?", reply_markup=repeat_kb())

@router.callback_query(BotState.choosing_repeat)
async def remind_repeat_received(cb: CallbackQuery, state: FSMContext):
    repeat_mode = cb.data.split("_")[1] # none, daily, weekly
    data = await state.get_data()
    
    await db.add_reminder(cb.from_user.id, data['nid'], data['dt'], repeat_mode)
    await state.clear()
    
    info = {"none": "", "daily": " (Каждый день)", "weekly": " (Раз в неделю)"}[repeat_mode]
    await cb.message.edit_text(f"✅ Напоминание установлено!{info}")

# --- Медиа ---
@router.message(F.photo | F.video | F.document | F.voice)
async def handle_media(msg: Message):
    f_id, f_type = None, None
    if msg.photo: f_id, f_type = msg.photo[-1].file_id, "photo"
    elif msg.video: f_id, f_type = msg.video.file_id, "video"
    elif msg.document: f_id, f_type = msg.document.file_id, "document"
    elif msg.voice: f_id, f_type = msg.voice.file_id, "voice"
    await db.add_media(msg.from_user.id, f_id, f_type, msg.caption or "")
    await msg.answer("💾 Сохранено!")

async def show_media_list(target, user_id, page):
    medias, count = await db.get_media_page(user_id, page)
    kb = InlineKeyboardBuilder()
    for m in medias:
        icon = {"photo":"🖼","video":"🎥","document":"📁","voice":"🎤"}.get(m.file_type, "❓")
        kb.row(InlineKeyboardButton(text=f"{icon} {m.caption or 'Файл'}...", callback_data=f"view_media_{m.id}"))
    kb.attach(InlineKeyboardBuilder.from_markup(pagination_kb(page, math.ceil(count/5) or 1, "list_media")))
    text = f"💾 Файлы ({count})"
    if isinstance(target, Message): await target.answer(text, reply_markup=kb.as_markup())
    else: await target.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("list_media_"))
async def cb_list_media(cb: CallbackQuery): await show_media_list(cb.message, cb.from_user.id, int(cb.data.split("_")[-1]))

@router.callback_query(F.data.startswith("view_media_"))
async def view_media(cb: CallbackQuery):
    m = await db.get_media(int(cb.data.split("_")[-1]))
    if not m: return await cb.answer("Удалено")
    await cb.message.delete()
    cap = f"{m.caption or ''}\n📅 {m.created_at.strftime('%d.%m')}"
    markup = media_control_kb(m.id)
    if m.file_type=="photo": await cb.message.answer_photo(m.file_id, caption=cap, reply_markup=markup)
    elif m.file_type=="video": await cb.message.answer_video(m.file_id, caption=cap, reply_markup=markup)
    elif m.file_type=="document": await cb.message.answer_document(m.file_id, caption=cap, reply_markup=markup)
    elif m.file_type=="voice": await cb.message.answer_voice(m.file_id, caption=cap, reply_markup=markup)

# --- Доп функции ---
@router.message(BotState.searching)
async def search_process(msg: Message, state: FSMContext):
    await state.clear()
    await search_engine(msg, msg.text)

async def search_engine(msg, query):
    notes, count = await db.get_notes_page(msg.from_user.id, 1, 10, query)
    if not notes: return await msg.answer("🔍 Ничего не нашел.")
    kb = InlineKeyboardBuilder()
    for n in notes: kb.row(InlineKeyboardButton(text=n.content[:30]+"...", callback_data=f"view_note_{n.id}"))
    await msg.answer(f"🔍 Поиск '{query}': найдено {count}", reply_markup=kb.as_markup())

@router.callback_query(F.data == "random_note")
async def random_n(cb: CallbackQuery):
    n = await db.get_random_note(cb.from_user.id)
    if not n: return await cb.answer("Пусто :(", show_alert=True)
    await cb.message.edit_text(f"🎲 <b>Random:</b>\n\n{n.content}", reply_markup=note_control_kb(n.id, n.is_pinned), parse_mode="HTML")

@router.callback_query(F.data == "export_notes")
async def export(cb: CallbackQuery):
    data = await db.get_all_notes_text(cb.from_user.id)
    if len(data) < 50: return await cb.answer("Мало данных")
    f = BufferedInputFile(data.encode('utf-8'), filename="backup.txt")
    await cb.message.answer_document(f, caption="✅ Backup")
    await cb.answer()

@router.callback_query(F.data.startswith("del_"))
async def delete_h(cb: CallbackQuery):
    _, t, i = cb.data.split("_")
    await db.delete_item(t, int(i))
    if t=="media": await cb.message.delete()
    else: await cb.message.edit_text("🗑 Удалено")

@router.callback_query(F.data.startswith("edit_note_"))
async def edit_s(cb: CallbackQuery, state: FSMContext):
    await state.update_data(nid=int(cb.data.split("_")[-1]))
    await state.set_state(BotState.editing)
    await cb.message.answer("✏️ Новый текст:", reply_markup=cancel_kb())
    await cb.answer()

@router.message(BotState.editing)
async def edit_f(msg: Message, state: FSMContext):
    d = await state.get_data()
    await db.update_note_text(d['nid'], msg.text)
    await state.clear()
    await msg.answer("✅ Сохранено")

@router.callback_query(F.data.startswith("pin_note_"))
async def pin(cb: CallbackQuery):
    await db.toggle_pin(int(cb.data.split("_")[-1]))
    await view_note(cb)

@router.callback_query(F.data=="cancel_action")
async def canc(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.delete()
    await cb.message.answer("Отмена")
@router.callback_query(F.data=="ignore")
async def ign(cb: CallbackQuery): await cb.answer()
