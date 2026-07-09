"""
Bot dispatcher va handlerlar — bu modul HAM webhook rejimida (backend ichida,
production/Render'da), HAM polling rejimida (bot/bot.py orqali, lokal test uchun)
ishlatiladi. Shu sababli Bot/Dispatcher shu yerda bir marta e'lon qilinadi.
"""
import asyncio
import io
import logging
import os
from urllib.parse import urljoin

import httpx
from PIL import Image
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MenuButtonWebApp, InputMediaPhoto, BufferedInputFile,
)

from shared.database import SessionLocal
from shared.models import Listing, ListingStatus, User

logger = logging.getLogger("telegram_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
# Tasdiqlangan e'lonlar avtomatik joylanadigan kanal: @kanal_username yoki -100... ko'rinishidagi ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
# BotFather'da /newapp orqali yaratilgan Mini App short name (masalan "Autosavdo") —
# kanal tugmasidan bitta bosishda to'g'ridan-to'g'ri Mini App ochilishi uchun kerak.
MINI_APP_SHORT_NAME = os.getenv("MINI_APP_SHORT_NAME", "Autosavdo").strip()

# Kanal posti uchun bir nechta e'lon rasmidan yasaladigan kollaj sozlamalari.
# Cheklovlar xotira/CPU'ni yeb ketadigan yoki osilib qoladigan holatlarning oldini olish uchun.
COLLAGE_MAX_PHOTOS = 9  # kollajga kiritiladigan rasmlar soni (3x3 grid)
COLLAGE_CELL_SIZE = 500  # har bir katakcha o'lchami (piksel)
COLLAGE_FETCH_TIMEOUT = 10.0  # har bir rasmni yuklab olish uchun maksimal soniya
COLLAGE_MAX_PHOTO_BYTES = 15 * 1024 * 1024  # bitta rasm uchun xavfsizlik chegarasi

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


def _assemble_collage(images_bytes: list[bytes]) -> bytes | None:
    """Yuklab olingan rasm baytlaridan bitta grid-kollaj yasaydi. Pillow'ning
    dekodlash/qayta o'lchash ishi CPU-bog'liq bo'lgani uchun bu funksiya
    asyncio.to_thread orqali alohida oqimda chaqiriladi — shunda noto'g'ri yoki
    og'ir rasm bot event loop'ini to'xtatib qo'ymaydi."""
    images: list[Image.Image] = []
    for data in images_bytes:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()  # to'liq dekodlaydi — buzuq fayl bo'lsa shu yerda xato chiqadi
            # Pillow'ning standart Image.MAX_IMAGE_PIXELS chegarasi shu yerda ham
            # ishlaydi va haddan tashqari katta ("decompression bomb") rasmlarni
            # DecompressionBombError bilan rad etadi — atayin o'chirilmagan.
            images.append(img.convert("RGB"))
        except Exception:
            logger.warning("Kollaj uchun bitta rasmni dekodlab bo'lmadi, o'tkazib yuborildi")

    if not images:
        return None

    cols = 2 if len(images) > 1 else 1
    rows = (len(images) + cols - 1) // cols
    canvas = Image.new("RGB", (COLLAGE_CELL_SIZE * cols, COLLAGE_CELL_SIZE * rows), "white")

    for i, img in enumerate(images):
        img.thumbnail((COLLAGE_CELL_SIZE, COLLAGE_CELL_SIZE))
        x = (i % cols) * COLLAGE_CELL_SIZE + (COLLAGE_CELL_SIZE - img.width) // 2
        y = (i // cols) * COLLAGE_CELL_SIZE + (COLLAGE_CELL_SIZE - img.height) // 2
        canvas.paste(img, (x, y))

    # JPEG'ga qayta kodlash asl fayldagi metadata/EXIF va boshqa "payload"larni
    # ham tashlab yuboradi — kanalga faqat piksellar boradi, xom fayl emas.
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def _build_collage(photo_urls: list[str]) -> bytes | None:
    """Bizning o'zimiz saqlagan (avval yuklashda tekshirilgan) e'lon rasmlaridan
    kollaj yasaydi. Har qanday xatolikda None qaytaradi — chaqiruvchi tomon
    eski albom usuliga qaytishi kerak, shuning uchun bu yerda hech narsa
    ko'tarilmaydi (raise qilinmaydi)."""
    urls = photo_urls[:COLLAGE_MAX_PHOTOS]
    images_bytes: list[bytes] = []
    try:
        async with httpx.AsyncClient(timeout=COLLAGE_FETCH_TIMEOUT) as client:
            for url in urls:
                resp = await client.get(url)
                resp.raise_for_status()
                if len(resp.content) > COLLAGE_MAX_PHOTO_BYTES:
                    logger.warning("Kollaj uchun rasm hajmi chegaradan katta, o'tkazib yuborildi: %s", url)
                    continue
                images_bytes.append(resp.content)
    except Exception:
        logger.exception("Kollaj uchun rasmlarni yuklab olishda xatolik")
        return None

    if not images_bytes:
        return None

    return await asyncio.to_thread(_assemble_collage, images_bytes)


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
            text="🚗 Avtosavdocom mini app",
            url=(
                f"https://t.me/{BOT_USERNAME}/{MINI_APP_SHORT_NAME}?startapp=channel"
                if BOT_USERNAME else MINI_APP_URL
            ),
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
            # Bir nechta rasmni bitta kollajga birlashtiramiz — shunda caption
            # va tugma bitta xabarda ("yopishgan" holda) yuboriladi. Telegram
            # sendMediaGroup'ga tugma qo'shishga ruxsat bermaydi, shu sababli
            # bu usul o'sha cheklovni butunlay chetlab o'tadi.
            collage_bytes = await _build_collage(photo_urls)
            if collage_bytes is not None:
                await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=BufferedInputFile(collage_bytes, filename="collage.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                # Kollaj yasab bo'lmadi (masalan rasmlarni yuklab olishda
                # xatolik) — eski albom + alohida tugmali xabar usuliga qaytamiz.
                media = [
                    InputMediaPhoto(media=url, caption=caption if i == 0 else None, parse_mode="HTML")
                    for i, url in enumerate(photo_urls[:10])  # Telegram albomda maksimal 10 ta rasm
                ]
                await bot.send_media_group(chat_id=CHANNEL_ID, media=media)
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text="Avtosavdocom",
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
