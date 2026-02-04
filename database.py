import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, BigInteger, DateTime, ForeignKey, Text, Boolean, select, delete, func, update, or_

# БД
engine = create_async_engine("sqlite+aiosqlite:///bot.db", echo=False)
new_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str] = mapped_column(String, nullable=True)

class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"))
    content: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # НОВОЕ
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    remind_at: Mapped[datetime] = mapped_column(DateTime)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)

class Media(Base):
    __tablename__ = "media"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"))
    file_id: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String)
    caption: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

# --- Функции ---
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def add_user(tg_id: int, username: str):
    async with new_session() as session:
        if not await session.scalar(select(User).where(User.telegram_id == tg_id)):
            session.add(User(telegram_id=tg_id, username=username))
            await session.commit()

async def add_note(tg_id: int, content: str):
    async with new_session() as session:
        note = Note(user_id=tg_id, content=content)
        session.add(note)
        await session.commit()
        return note.id

async def update_note_text(note_id: int, new_text: str):
    async with new_session() as session:
        await session.execute(update(Note).where(Note.id == note_id).values(content=new_text))
        await session.commit()

async def toggle_pin(note_id: int):
    async with new_session() as session:
        note = await session.get(Note, note_id)
        if note:
            new_state = not note.is_pinned
            note.is_pinned = new_state
            await session.commit()
            return new_state
    return False

async def add_reminder(user_id: int, note_id: int, date: datetime):
    async with new_session() as session:
        session.add(Reminder(user_id=user_id, note_id=note_id, remind_at=date))
        await session.commit()

async def get_notes_page(tg_id: int, page: int, limit=5, search_query=None):
    offset = (page - 1) * limit
    async with new_session() as session:
        query = select(Note).where(Note.user_id == tg_id)
        
        if search_query:
            query = query.where(Note.content.ilike(f"%{search_query}%"))
        
        # Сначала закрепленные, потом новые
        query = query.order_by(Note.is_pinned.desc(), Note.created_at.desc()).limit(limit).offset(offset)
        
        notes = await session.scalars(query)
        
        # Считаем кол-во для пагинации
        count_query = select(func.count(Note.id)).where(Note.user_id == tg_id)
        if search_query:
            count_query = count_query.where(Note.content.ilike(f"%{search_query}%"))
        count = await session.scalar(count_query)
        
        return notes.all(), count

async def get_stats(tg_id: int):
    async with new_session() as session:
        n_count = await session.scalar(select(func.count(Note.id)).where(Note.user_id == tg_id))
        m_count = await session.scalar(select(func.count(Media.id)).where(Media.user_id == tg_id))
        return n_count, m_count

async def get_note(note_id: int):
    async with new_session() as session:
        return await session.get(Note, note_id)

async def delete_item(item_type: str, item_id: int):
    async with new_session() as session:
        model = Note if item_type == "note" else Media
        await session.execute(delete(model).where(model.id == item_id))
        await session.commit()

async def add_media(tg_id: int, f_id: str, f_type: str, caption: str):
    async with new_session() as session:
        session.add(Media(user_id=tg_id, file_id=f_id, file_type=f_type, caption=caption))
        await session.commit()

async def get_media_page(tg_id: int, page: int, limit=5):
    offset = (page - 1) * limit
    async with new_session() as session:
        medias = await session.scalars(select(Media).where(Media.user_id == tg_id).order_by(Media.created_at.desc()).limit(limit).offset(offset))
        count = await session.scalar(select(func.count(Media.id)).where(Media.user_id == tg_id))
        return medias.all(), count

async def get_media(media_id: int):
    async with new_session() as session:
        return await session.get(Media, media_id)

async def get_pending_reminders():
    async with new_session() as session:
        res = await session.execute(select(Reminder, Note).join(Note).where(Reminder.is_sent == False, Reminder.remind_at <= datetime.now()))
        return res.all()

async def mark_reminder_done(r_id: int):
    async with new_session() as session:
        await session.execute(delete(Reminder).where(Reminder.id == r_id))
        await session.commit()
