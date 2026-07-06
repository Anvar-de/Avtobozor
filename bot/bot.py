"""
Faqat LOKAL TEST uchun: botni polling rejimida ishga tushiradi
(hech qanday HTTPS/webhook kerak emas — shuning uchun ngrok'siz ham ishlaydi).

Productionda (Render'da) bot webhook orqali backend/app/main.py ichida ishlaydi —
bu skriptni serverda ishga tushirish shart EMAS.

Ishga tushirish: loyihaning ILDIZ papkasidan
    python bot/bot.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from backend.app.telegram_bot import bot, dp, BOT_TOKEN, setup_menu_button, resolve_bot_username


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi sozlanmagan (.env faylni tekshiring)")
    await resolve_bot_username()
    await setup_menu_button()
    print("Bot polling rejimida ishga tushdi. To'xtatish uchun Ctrl+C.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
