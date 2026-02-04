import asyncio
import logging
import os
from aiogram import Bot, Dispatcher

# Попробуем подключить dotenv для локального запуска, 
# но если его нет (как на хостинге), не страшно.
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
                    logging.error(f"Не смог отправить напоминание: {e}")
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")
        
        await asyncio.sleep(60)

async def main():
    logging.basicConfig(level=logging.INFO)

    # 1. Пытаемся найти токен под именем BOT_TOKEN (стандарт)
    bot_token = os.getenv("BOT_TOKEN")
    
    # 2. Если не нашли, пробуем имя TOKEN (иногда хостинги называют его так)
    if not bot_token:
        bot_token = os.getenv("TOKEN")

    # 3. Если всё равно пусто — выводим ошибку
    if not bot_token:
        print("❌ ОШИБКА: Токен не найден! Проверь настройки 'Startup' на хостинге.")
        # Для отладки можно раскомментировать следующую строку, чтобы увидеть все переменные (осторожно, не показывай никому логи!)
        # print(os.environ) 
        return

    await db.init_db()
    
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    logging.info(f"✅ Бот запускается... Токен получен (длина: {len(bot_token)})")
    
    asyncio.create_task(scheduler(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")
