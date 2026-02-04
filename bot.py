import asyncio
import logging
import os
import pytz # ТАЙМЗОНА
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import database as db
from handlers import router

async def scheduler(bot: Bot):
    msk = pytz.timezone('Europe/Moscow')
    while True:
        try:
            # Сравниваем время
            now_msk = datetime.now(msk).replace(tzinfo=None)
            reminders = await db.get_pending_reminders(now_msk)
            
            for r, note in reminders:
                try:
                    await bot.send_message(r.user_id, f"🔔 <b>Напоминание!</b>\n\n{note.content}", parse_mode="HTML")
                    
                    # ОБРАБОТКА ПОВТОРА (или удаление)
                    await db.process_reminder_repeat(r.id)
                    
                except Exception as e:
                    logging.error(f"Send err: {e}")
        except Exception as e:
            logging.error(f"Sched err: {e}")
        await asyncio.sleep(60)

async def main():
    logging.basicConfig(level=logging.WARNING)
    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
    if not bot_token: return print("❌ Нет токена")

    await db.init_db()
    
    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("🚀 Bot v4.0 Ultimate (MSK Timezone + Repeats)")
    asyncio.create_task(scheduler(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
