"""
Bot dispatcher va handlerlar — bu modul HAM webhook rejimida (backend ichida,
production/Render'da), HAM polling rejimida (bot/bot.py orqali, lokal test uchun)
ishlatiladi. Shu sababli Bot/Dispatcher shu yerda bir marta e'lon qilinadi.
"""
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from shared.database import SessionLocal
from shared.models import Listing, ListingStatus

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🚗 E'lonlarni ko'rish / joylash",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    ]])
    await message.answer(
        "Assalomu alaykum! Bu yerda avtomobil sotuvi e'lonlarini ko'rishingiz "
        "va o'zingiz e'lon joylashingiz mumkin.",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("approve:") | F.data.startswith("reject:"))
async def moderation_handler(callback: CallbackQuery):
    if ADMIN_CHAT_ID and str(callback.from_user.id) != str(ADMIN_CHAT_ID):
        await callback.answer("Sizda ruxsat yo'q", show_alert=True)
        return

    action, listing_id_str = callback.data.split(":")
    listing_id = int(listing_id_str)

    db = SessionLocal()
    try:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if not listing:
            await callback.answer("E'lon topilmadi (o'chirilgan bo'lishi mumkin)", show_alert=True)
            return

        listing.status = ListingStatus.approved if action == "approve" else ListingStatus.rejected
        db.commit()

        status_text = "✅ tasdiqlandi" if action == "approve" else "❌ rad etildi"
        await callback.message.edit_text(f"{callback.message.text}\n\nHolat: {status_text}")
        await callback.answer(f"E'lon {status_text}")

        owner = listing.owner
        if owner and owner.telegram_id:
            try:
                if action == "approve":
                    text = f"✅ Sizning {listing.brand} {listing.model} e'loningiz tasdiqlandi va ro'yxatda ko'rinmoqda."
                else:
                    text = f"❌ Sizning {listing.brand} {listing.model} e'loningiz rad etildi."
                await bot.send_message(owner.telegram_id, text)
            except Exception:
                pass
    finally:
        db.close()
