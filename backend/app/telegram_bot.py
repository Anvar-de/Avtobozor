"""
Bot dispatcher va handlerlar — bu modul HAM webhook rejimida (backend ichida,
production/Render'da), HAM polling rejimida (bot/bot.py orqali, lokal test uchun)
ishlatiladi. Shu sababli Bot/Dispatcher shu yerda bir marta e'lon qilinadi.
"""
import logging
import os
from urllib.parse import urljoin

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MenuButtonWebApp, InputMediaPhoto,
)

from shared.database import SessionLocal
from shared.models import Listing, ListingStatus, User

logger = logging.getLogger("telegram_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
# Tasdiqlangan e'lonlar avtomatik joylanadigan kanal: @kanal_username yoki -100... ko'rinishidagi ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

BOT_USERNAME: str | None = None  # startup vaqtida to'ldiriladi


async def resolve_bot_username():
    """Botning @username'ini bir marta olib, keshda saqlaydi (kanal xabaridagi
    tugma uchun kerak — bot manzilini qo'lda kiritish shart bo'lmasin)."""
    global BOT_USERNAME
    if bot is None:
        return
    me = await bot.get_me()
    BOT_USERNAME = me.username


async def setup_menu_button():
    """Chatning pastki qismida (matn yozish maydoni yonida) doimiy 'Menu'
    tugmasini o'rnatadi — bu tugma har doim ko'rinib turadi, foydalanuvchi
    /start yozishi shart emas."""
    if bot is None:
        return
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="🚗 E'lonlar",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    )


async def post_to_channel(listing: Listing):
    """Tasdiqlangan e'lonni kanalga joylaydi (agar CHANNEL_ID sozlangan bo'lsa)."""
    if bot is None or not CHANNEL_ID:
        return

    caption_lines = [
        f"🚗 <b>{listing.brand} {listing.model}</b>, {listing.year}",
        "",
        f"💰 <b>{listing.price:,.0f}</b> so'm".replace(",", " "),
        f"🛣 {listing.mileage:,} km".replace(",", " "),
    ]
    if listing.transmission:
        caption_lines.append(f"⚙️ {listing.transmission}")
    if listing.fuel_type:
        caption_lines.append(f"⛽ {listing.fuel_type}")
    if listing.region:
        caption_lines.append(f"📍 {listing.region}")
    if listing.description:
        desc = listing.description.strip()
        caption_lines.append("")
        caption_lines.append(desc[:300] + ("…" if len(desc) > 300 else ""))
    if listing.contact_phone:
        caption_lines.append("")
        caption_lines.append(f"📞 {listing.contact_phone}")
    caption = "\n".join(caption_lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🚗 Barcha e'lonlarni ko'rish",
            url=f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else MINI_APP_URL,
        )
    ]])

    try:
        photo_urls = [
            urljoin(MINI_APP_URL + "/", p.file_path.lstrip("/")) for p in listing.photos
        ]

        if len(photo_urls) == 1:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_urls[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        elif len(photo_urls) > 1:
            # Telegram sendMediaGroup tugma (reply_markup) qo'shishga ruxsat bermaydi,
            # shuning uchun avval albom (barcha rasmlar), keyin tugmali kichik xabar yuboramiz.
            media = [
                InputMediaPhoto(media=url, caption=caption if i == 0 else None, parse_mode="HTML")
                for i, url in enumerate(photo_urls[:10])  # Telegram albomda maksimal 10 ta rasm
            ]
            await bot.send_media_group(chat_id=CHANNEL_ID, media=media)
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text="👆 E'lon rasmlari yuqorida",
                reply_markup=keyboard,
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception:
        # Kanalga joylash ishlamay qolsa ham (masalan bot hali admin qilinmagan
        # bo'lsa), asosiy oqim (tasdiqlash) buzilmasligi kerak — shuning uchun
        # xatoni yutib, faqat logga yozamiz.
        logger.exception("Kanalga joylashda xatolik (CHANNEL_ID=%s)", CHANNEL_ID)


@dp.message(CommandStart())
async def start_handler(message: Message):
    # Foydalanuvchini bazaga yozib qo'yamiz — shunda /stats hamma botni
    # ishga tushirganlarni sanaydi, faqat Mini App ochganlarni emas.
    db = SessionLocal()
    try:
        tg = message.from_user
        user = db.query(User).filter(User.telegram_id == tg.id).first()
        if not user:
            full_name = " ".join(filter(None, [tg.first_name, tg.last_name]))
            user = User(telegram_id=tg.id, username=tg.username, full_name=full_name or None)
            db.add(user)
            db.commit()
    finally:
        db.close()

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


@dp.message(Command("stats"))
async def stats_handler(message: Message):
    """Faqat admin ishlata oladi: umumiy statistika."""
    if ADMIN_CHAT_ID and str(message.from_user.id) != str(ADMIN_CHAT_ID):
        return  # oddiy foydalanuvchiga hech narsa javob bermaymiz

    db = SessionLocal()
    try:
        total_users = db.query(User).count()
        total_listings = db.query(Listing).count()
        pending = db.query(Listing).filter(Listing.status == ListingStatus.pending).count()
        approved = db.query(Listing).filter(Listing.status == ListingStatus.approved).count()
        rejected = db.query(Listing).filter(Listing.status == ListingStatus.rejected).count()
        sold = db.query(Listing).filter(Listing.status == ListingStatus.sold).count()

        text = (
            "📊 <b>Bot statistikasi</b>\n\n"
            f"👤 Jami foydalanuvchilar: <b>{total_users}</b>\n"
            f"📋 Jami e'lonlar: <b>{total_listings}</b>\n\n"
            f"⏳ Ko'rib chiqilmoqda: {pending}\n"
            f"✅ Faol (tasdiqlangan): {approved}\n"
            f"💰 Sotilgan: {sold}\n"
            f"❌ Rad etilgan: {rejected}"
        )
        await message.answer(text, parse_mode="HTML")
    finally:
        db.close()


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

        if action == "approve":
            await post_to_channel(listing)
    finally:
        db.close()
