import asyncio
import logging
from aiogram import Bot, Dispatcher
import database as db
from handlers import router

# ----------------НАСТРОЙКИ----------------
BOT_TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН_БОТА"
# -----------------------------------------

async def scheduler(bot: Bot):
    """Фоновая задача для проверки напоминаний"""
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
        
        await asyncio.sleep(60) # Проверка каждую минуту

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Инициализация БД
    await db.init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    logging.info("Бот запущен!")
    
    # Запускаем планировщик и бота параллельно
    asyncio.create_task(scheduler(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")
