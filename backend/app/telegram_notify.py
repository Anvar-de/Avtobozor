import html
import logging
import os

from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from shared.regions import format_location
from shared.storage import resolve_url

from .telegram_bot import MINI_APP_URL, _build_collage, bot

logger = logging.getLogger("telegram_notify")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")


def _e(value) -> str:
    """HTML-maxsus belgilarni escape qiladi — foydalanuvchi kiritgan matn
    (marka, tavsif, ism) xabar formatini buzib qo'ymasligi uchun."""
    return html.escape(str(value)) if value else ""


async def notify_admin_new_listing(listing) -> None:
    """Yangi e'lon kelganda adminga rasm(lar) (bittadan ko'p bo'lsa — kollaj holida),
    yuboruvchi profiliga havola hamda tasdiqlash/rad etish tugmalari bilan xabar yuboradi.
    Rasmlar bilan to'liq ko'rsatish uchun bu funksiya e'lon yaratilganda emas, barcha
    rasmlar yuklab bo'lingandan keyin (POST /api/listings/{id}/submit) chaqiriladi."""
    if bot is None or not ADMIN_CHAT_ID:
        return  # sozlanmagan bo'lsa, jim o'tkazib yuboramiz (dev muhitida qulay)

    owner = listing.owner
    if owner:
        owner_label = _e(owner.full_name or owner.username or owner.telegram_id)
        owner_line = f'👤 Yuboruvchi: <a href="tg://user?id={owner.telegram_id}">{owner_label}</a>'
        if owner.username:
            owner_line += f" (@{_e(owner.username)})"
    else:
        owner_line = "👤 Yuboruvchi: noma'lum"

    lines = [
        f"🚗 Yangi e'lon: #{listing.id}",
        f"{_e(listing.brand)} {_e(listing.model)}, {listing.year}",
        f"Narxi: ${listing.price:,.0f}",
        f"Probeg: {listing.mileage:,} km",
        f"Manzil: {_e(format_location(listing.region, listing.district)) or '-'}",
        owner_line,
    ]
    if listing.description:
        lines.append(f"Tavsif: {_e(listing.description.strip())}")
    text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{listing.id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{listing.id}"),
    ]])

    photo_urls = [resolve_url(p.file_path, MINI_APP_URL) for p in listing.photos]

    try:
        if len(photo_urls) == 1:
            await bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=photo_urls[0],
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        elif len(photo_urls) > 1:
            collage_bytes = await _build_collage(photo_urls)
            if collage_bytes is not None:
                await bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=BufferedInputFile(collage_bytes, filename="collage.jpg"),
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                # Kollaj yasab bo'lmadi — matnli xabarga qaytamiz, hech bo'lmasa
                # tasdiqlash/rad etish va yuboruvchi havolasi yetib borsin.
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        # Adminga xabar yuborish muvaffaqiyatsiz bo'lsa ham (masalan fayl
        # topilmadi), e'lonni yaratish oqimi buzilmasligi kerak.
        logger.exception("Adminga yangi e'lon xabarini yuborishda xatolik (listing_id=%s)", listing.id)
