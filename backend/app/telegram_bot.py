"""
Bot dispatcher va handlerlar — bu modul HAM webhook rejimida (backend ichida,
production/Render'da), HAM polling rejimida (bot/bot.py orqali, lokal test uchun)
ishlatiladi. Shu sababli Bot/Dispatcher shu yerda bir marta e'lon qilinadi.
"""
import asyncio
import html
import io
import logging
import os

import httpx
from PIL import Image, ImageOps
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MenuButtonWebApp, InputMediaPhoto, BufferedInputFile,
)

from shared.currency import format_price
from shared.database import SessionLocal
from shared.models import Listing, ListingStatus, User
from shared.regions import format_location
from shared.storage import resolve_url

logger = logging.getLogger("telegram_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
# Tasdiqlangan e'lonlar avtomatik joylanadigan kanal: @kanal_username yoki -100... ko'rinishidagi ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
# BotFather'da /newapp orqali yaratilgan Mini App short name (masalan "Autosavdo") —
# kanal tugmasidan bitta bosishda to'g'ridan-to'g'ri Mini App ochilishi uchun kerak.
MINI_APP_SHORT_NAME = os.getenv("MINI_APP_SHORT_NAME", "Autosavdo").strip()
# /start xabarida foydalanuvchini taklif qilinadigan kanal linki.
CHANNEL_LINK = "https://t.me/idealavtosavdo"

# Kanal posti uchun bir nechta e'lon rasmidan yasaladigan kollaj sozlamalari.
# Cheklovlar xotira/CPU'ni yeb ketadigan yoki osilib qoladigan holatlarning oldini olish uchun.
COLLAGE_MAX_PHOTOS = 9  # kollajga kiritiladigan rasmlar soni (3x3 grid)
COLLAGE_SIZE = 1600  # kollaj doim shu o'lchamda (kvadrat, piksel) chiqadi
COLLAGE_MAX_PHOTO_BYTES = 15 * 1024 * 1024  # bitta rasm uchun xavfsizlik chegarasi

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

BOT_USERNAME: str | None = None  # startup vaqtida to'ldiriladi


def _e(value) -> str:
    """HTML-maxsus belgilarni escape qiladi — foydalanuvchi kiritgan matn
    (marka, tavsif, telefon va h.k.) parse_mode="HTML" bilan yuborilganda
    Telegram tomonidan teg/havola sifatida talqin qilinib qolmasligi uchun."""
    return html.escape(str(value)) if value else ""


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
    for idx, data in enumerate(images_bytes):
        try:
            img = Image.open(io.BytesIO(data))
            img.load()  # to'liq dekodlaydi — buzuq fayl bo'lsa shu yerda xato chiqadi
            # Pillow'ning standart Image.MAX_IMAGE_PIXELS chegarasi shu yerda ham
            # ishlaydi va haddan tashqari katta ("decompression bomb") rasmlarni
            # DecompressionBombError bilan rad etadi — atayin o'chirilmagan.
            images.append(img.convert("RGB"))
        except Exception:
            logger.warning("Kollaj uchun %d-rasmni dekodlab bo'lmadi, o'tkazib yuborildi", idx, exc_info=True)

    if not images:
        return None

    n = len(images)
    # Har doim maksimal 2 ustun: 1 ta rasm — yakka; 2 ta rasm — tepa-pastga
    # (1 ustun, 2 qavat); 3 tadan ko'p bo'lsa — 2 ustunli qavatlarga bo'linadi,
    # oxirgi qavatda 1 yoki 2 rasm qoladi (masalan 5 ta = 2+2+1, 7 ta = 2+2+2+1).
    cols = 1 if n <= 2 else 2
    rows = (n + cols - 1) // cols

    gap = 6  # katakchalar orasidagi bo'shliq (piksel)
    # Kollaj hajmi doim COLLAGE_SIZE x COLLAGE_SIZE bo'lishi uchun, katakcha
    # o'lchamini ustun/qator soniga qarab hisoblaymiz (grid holatiga qarab
    # katakcha kvadrat bo'lmasligi ham mumkin — masalan 3 ustunli 2 qatorda).
    cell_w = (COLLAGE_SIZE - gap * (cols + 1)) // cols
    cell_h = (COLLAGE_SIZE - gap * (rows + 1)) // rows
    canvas = Image.new("RGB", (COLLAGE_SIZE, COLLAGE_SIZE), "white")

    last_row_count = n - cols * (rows - 1)  # oxirgi qatordagi rasmlar soni
    for i, img in enumerate(images):
        row, col = divmod(i, cols)
        row_items = last_row_count if row == rows - 1 else cols
        # Oxirgi qator to'liq emas bo'lsa (masalan 3 ustunga 2 ta rasm qolsa),
        # bo'sh joy chetda emas, qator markazida bo'linadi — tekis ko'rinadi.
        row_offset = ((cols - row_items) * (cell_w + gap)) // 2
        # thumbnail+pad o'rniga "cover" crop qilamiz — katakcha to'liq to'ladi,
        # atrofida oq chiziqlar qolmaydi.
        thumb = ImageOps.fit(img, (cell_w, cell_h), method=Image.LANCZOS)
        x = gap + col * (cell_w + gap) + row_offset
        y = gap + row * (cell_h + gap)
        canvas.paste(thumb, (x, y))

    # JPEG'ga qayta kodlash asl fayldagi metadata/EXIF va boshqa "payload"larni
    # ham tashlab yuboradi — kanalga faqat piksellar boradi, xom fayl emas.
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def _fetch_photo(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
    except Exception:
        logger.warning("Kollaj uchun rasmni yuklab bo'lmadi: %s", url, exc_info=True)
        return None
    if len(data) > COLLAGE_MAX_PHOTO_BYTES:
        logger.warning("Kollaj uchun rasm hajmi chegaradan katta, o'tkazib yuborildi: %s", url)
        return None
    return data


async def _read_photo_urls(urls: list[str]) -> list[bytes]:
    """Rasm baytlarini URL orqali (R2/CDN) parallel yuklab oladi (ketma-ket
    emas) — shunda bir nechta rasmli e'londa adminga/kanalga xabar yuborish
    rasmlar sonicha sekinlashib ketmaydi. Rasmlar soni COLLAGE_MAX_PHOTOS
    bilan cheklangani uchun parallel ulanishlar soni ham cheklangan."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await asyncio.gather(*(_fetch_photo(client, url) for url in urls))
    return [data for data in results if data is not None]


async def _build_collage(photo_urls: list[str]) -> bytes | None:
    """E'lon rasmlaridan (R2/CDN'dan yuklab olib) bitta kollaj yasaydi.
    Har qanday xatolikda None qaytaradi — chaqiruvchi tomon eski albom
    usuliga qaytishi kerak, shuning uchun bu yerda hech narsa ko'tarilmaydi."""
    urls = photo_urls[:COLLAGE_MAX_PHOTOS]
    images_bytes = await _read_photo_urls(urls)

    if len(images_bytes) < len(urls):
        logger.warning(
            "Kollaj uchun %d/%d rasm muvaffaqiyatli yuklandi", len(images_bytes), len(urls)
        )

    if not images_bytes:
        return None

    return await asyncio.to_thread(_assemble_collage, images_bytes)


async def post_to_channel(listing: Listing) -> list[int] | None:
    """Tasdiqlangan e'lonni kanalga joylaydi (agar CHANNEL_ID sozlangan bo'lsa).
    Muvaffaqiyatli bo'lsa, yuborilgan xabar(lar)ning ID ro'yxatini qaytaradi —
    chaqiruvchi buni listing.channel_message_ids'ga saqlashi kerak, shunda
    e'lon keyinchalik o'chirilganda kanaldagi post ham o'chirilishi mumkin."""
    if bot is None or not CHANNEL_ID:
        return None

    brand_tag = "".join(listing.brand.split())
    caption_lines = [
        f"🚗 <b>#{_e(brand_tag)} #{_e(listing.model)}</b>",
        "",
        f"📅 {listing.year}",
        f"🛣 {listing.mileage:,} km".replace(",", " "),
    ]
    if listing.transmission:
        caption_lines.append(f"⚙️ {_e(listing.transmission)}")
    if listing.fuel_type:
        caption_lines.append(f"⛽ {_e(listing.fuel_type)}")
    location = format_location(listing.region, listing.district)
    if location:
        caption_lines.append(f"📍 {_e(location)}")
    caption_lines.append(f"💰 <b>{format_price(listing.price, listing.currency)}</b>")
    if listing.description:
        desc = listing.description.strip()
        caption_lines.append("")
        caption_lines.append(_e(desc[:300] + ("…" if len(desc) > 300 else "")))
    if listing.contact_phone:
        caption_lines.append("")
        caption_lines.append(f"📞 {_e(listing.contact_phone)}")
    caption_lines.append("")
    caption_lines.append("Barcha e'lonlarni ko'rish uchun pastdagi tugmani bosing 👇👇👇")
    caption = "\n".join(caption_lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🚗 E'lon berish va qidirish ilovasi",
            url=(
                f"https://t.me/{BOT_USERNAME}/{MINI_APP_SHORT_NAME}?startapp=channel"
                if BOT_USERNAME else MINI_APP_URL
            ),
        )
    ]])

    try:
        photo_urls = [resolve_url(p.file_path, MINI_APP_URL) for p in listing.photos]

        if len(photo_urls) == 1:
            msg = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_urls[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return [msg.message_id]
        elif len(photo_urls) > 1:
            # Bir nechta rasmni bitta kollajga birlashtiramiz — shunda caption
            # va tugma bitta xabarda ("yopishgan" holda) yuboriladi. Telegram
            # sendMediaGroup'ga tugma qo'shishga ruxsat bermaydi, shu sababli
            # bu usul o'sha cheklovni butunlay chetlab o'tadi.
            collage_bytes = await _build_collage(photo_urls)
            if collage_bytes is not None:
                msg = await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=BufferedInputFile(collage_bytes, filename="collage.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return [msg.message_id]
            else:
                # Kollaj yasab bo'lmadi (masalan rasmlarni yuklab olishda
                # xatolik) — eski albom + alohida tugmali xabar usuliga qaytamiz.
                media = [
                    InputMediaPhoto(media=url, caption=caption if i == 0 else None, parse_mode="HTML")
                    for i, url in enumerate(photo_urls[:10])  # Telegram albomda maksimal 10 ta rasm
                ]
                album_messages = await bot.send_media_group(chat_id=CHANNEL_ID, media=media)
                btn_message = await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text="Avtosavdocom",
                    reply_markup=keyboard,
                )
                return [m.message_id for m in album_messages] + [btn_message.message_id]
        else:
            msg = await bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return [msg.message_id]
    except Exception:
        # Kanalga joylash ishlamay qolsa ham (masalan bot hali admin qilinmagan
        # bo'lsa), asosiy oqim (tasdiqlash) buzilmasligi kerak — shuning uchun
        # xatoni yutib, faqat logga yozamiz.
        logger.exception("Kanalga joylashda xatolik (CHANNEL_ID=%s)", CHANNEL_ID)
        return None


async def delete_channel_post(listing: Listing) -> None:
    """E'lon o'chirilganda, agar u avval kanalga joylangan bo'lsa, o'sha
    post(lar)ni kanaldan ham o'chiradi. Har bir xabar alohida o'chiriladi —
    ba'zilari (masalan qo'lda allaqachon o'chirilgan bo'lsa) muvaffaqiyatsiz
    bo'lsa ham, qolganlari o'chirilishga harakat qilinadi."""
    if bot is None or not CHANNEL_ID or not listing.channel_message_ids:
        logger.info(
            "Kanal posti o'chirilmadi — saqlangan message_id yo'q (listing_id=%s, "
            "bot=%s, CHANNEL_ID=%s, channel_message_ids=%r)",
            listing.id, bot is not None, bool(CHANNEL_ID), listing.channel_message_ids,
        )
        return
    for id_str in listing.channel_message_ids.split(","):
        try:
            await bot.delete_message(chat_id=CHANNEL_ID, message_id=int(id_str))
            logger.info("Kanal posti o'chirildi (listing_id=%s, message_id=%s)", listing.id, id_str)
        except Exception:
            logger.warning(
                "Kanaldan postni o'chirib bo'lmadi (listing_id=%s, message_id=%s)",
                listing.id, id_str, exc_info=True,
            )


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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚗 E'lonlarni ko'rish / joylash",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )],
        [InlineKeyboardButton(text="📢 Kanalimizga qo'shilish", url=CHANNEL_LINK)],
    ])
    await message.answer(
        "Assalomu alaykum! Bu yerda avtomobil sotuvi e'lonlarini ko'rishingiz "
        "va o'zingiz e'lon joylashingiz mumkin.\n\n"
        f"Yangiliklardan xabardor bo'lish uchun kanalimizga qo'shiling: {CHANNEL_LINK}",
        reply_markup=keyboard,
    )


@dp.message(Command("stats"))
async def stats_handler(message: Message):
    """Faqat admin ishlata oladi: umumiy statistika."""
    from .routers.auth import is_admin_user
    if not is_admin_user(message.from_user.id):
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


@dp.message(Command("reklama"))
async def reklama_handler(message: Message):
    """Faqat admin ishlata oladi: boshqa kanal/gruppalarda tarqatish uchun tayyor
    reklama xabari (matn + mini appni ochuvchi tugma) yuboradi — buni keyin kerakli
    joyga qo'lda forward qilish mumkin."""
    from .routers.auth import is_admin_user
    if not is_admin_user(message.from_user.id):
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚗 Ilovani ochish",
            url=(
                f"https://t.me/{BOT_USERNAME}/{MINI_APP_SHORT_NAME}?startapp=ad"
                if BOT_USERNAME else MINI_APP_URL
            ),
        )],
        [InlineKeyboardButton(text="📢 Kanalimizga qo'shilish", url=CHANNEL_LINK)],
    ])
    await message.answer(
        "🚗 Avtomobil sotib olish yoki sotish osonlashdi!\n\n"
        "Idealavtosavdo — minglab avtomobil e'lonlari bir joyda: qidiring, "
        "solishtiring, narxini taqqoslang yoki o'zingiznikini bepul joylang.\n\n"
        "👇 Pastdagi tugmani bosing",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("approve:") | F.data.startswith("reject:"))
async def moderation_handler(callback: CallbackQuery):
    from .routers.auth import is_admin_user
    if not is_admin_user(callback.from_user.id):
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
        # Admin xabari rasmli/kollajli bo'lishi mumkin (caption) yoki oddiy matn
        # (rasm bo'lmasa) — ikkisi turlicha tahrirlanadi. callback.message.text/
        # .caption Telegram tomonidan formatlashsiz (entity'lar olib tashlangan)
        # qaytariladi, shu sabab qayta yuborishda parse_mode berilmaydi — aks
        # holda ichidagi "<"/">" belgilari xato HTML sifatida talqin qilinib,
        # Telegram API xatolik qaytarishi mumkin edi.
        if callback.message.photo:
            await callback.message.edit_caption(caption=f"{callback.message.caption}\n\nHolat: {status_text}")
        else:
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
            message_ids = await post_to_channel(listing)
            if message_ids:
                listing.channel_message_ids = ",".join(str(i) for i in message_ids)
                db.commit()
                logger.info(
                    "Kanal post ID saqlandi (listing_id=%s, message_ids=%s)",
                    listing.id, listing.channel_message_ids,
                )
            else:
                logger.warning(
                    "post_to_channel hech qanday message_id qaytarmadi (listing_id=%s) — "
                    "kanalga joylash muvaffaqiyatsiz bo'lgan bo'lishi mumkin",
                    listing.id,
                )
    finally:
        db.close()
