import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Попытка локальной загрузки
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import database as db
from handlers import router

async def scheduler(bot: Bot):
    while True:
        try:
            reminders = await db.get_pending_reminders()
            for r, note in reminders:
                try:
                    await bot.send_message(r.user_id, f"🔔 <b>Напоминание!</b>\n\n{note.content}", parse_mode="HTML")
                    await db.mark_reminder_done(r.id)
                except Exception as e:
                    logging.error(f"Failed to send reminder: {e}")
        except Exception as e:
            logging.error(f"Scheduler error: {e}")
        await asyncio.sleep(60)

async def main():
    logging.basicConfig(level=logging.INFO)

    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
    if not bot_token:
        print("❌ ОШИБКА: Токен не найден!")
        return

    await db.init_db()
    
    bot = Bot(token=bot_token)
    # Важно: добавляем хранилище для состояний (поиск, редактирование)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.info("✅ Бот запущен v2.0")
    
    asyncio.create_task(scheduler(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")
