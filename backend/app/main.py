import asyncio
import logging
import os
import secrets
from dotenv import load_dotenv
load_dotenv()

# Standart holatda Python'ning root logger darajasi WARNING — bu logger.info(...)
# orqali yozilgan barcha xabarlarni (masalan telegram_bot.py'dagi diagnostika
# loglarini) jimgina yashirib qo'yardi. INFO darajasini yoqib, ular ham
# Render loglarida ko'rinadigan qilamiz.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

logger = logging.getLogger("main")

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from aiogram.types import Update
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import inspect, text

from shared.database import Base, engine
from shared.exchange_rate import daily_refresh_loop
from .rate_limit import limiter
from .routers import auth, listings, meta
from .telegram_bot import bot, dp, setup_menu_button, resolve_bot_username
from .telegram_auth import SKIP_TELEGRAM_VALIDATION

# Render bunday muhit o'zgaruvchisini avtomatik beradi (masalan
# "https://sizning-servis.onrender.com"). Boshqa hostingda buni qo'lda
# PUBLIC_URL sifatida sozlang. Shu o'zgaruvchining borligi "biz haqiqiy
# (production) serverda ishlayapmiz" degani — lokal ishga tushirishda bo'lmaydi.
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")

# SKIP_TELEGRAM_VALIDATION Telegram initData imzosini butunlay o'chirib,
# so'rovchi o'zi aytgan har qanday telegram_id'ni (jumladan ADMIN_CHAT_ID'ni)
# haqiqiy deb qabul qiladi — faqat lokal testda ishlatilishi mumkin. Production
# muhitida yoqilgan bo'lsa, ilova umuman ishga tushmasin (jimgina noto'g'ri
# sozlanib qolib, admin huquqini kimdir o'zlashtirib olmasligi uchun).
if PUBLIC_URL and SKIP_TELEGRAM_VALIDATION:
    raise RuntimeError(
        "SKIP_TELEGRAM_VALIDATION=true production muhitida (PUBLIC_URL/RENDER_EXTERNAL_URL "
        "sozlangan) ishlatib bo'lmaydi — bu Telegram initData imzosini tekshirmay, istalgan "
        "foydalanuvchini (jumladan o'zini admin qilib) qabul qilishga imkon beradi. "
        ".env faylida SKIP_TELEGRAM_VALIDATION=false qiling yoki uni butunlay olib tashlang."
    )

# Jadvallarni yaratish (production'da Alembic migratsiya ishlatish tavsiya etiladi)
Base.metadata.create_all(bind=engine)

# create_all() mavjud jadvalga yangi ustun qo'shmaydi — Alembic yo'qligi sabab,
# eski bazalarda "listings.views_count" ustuni yo'q bo'lib qolmasligi uchun
# shu yerda qo'lda tekshirib qo'shamiz.
_inspector = inspect(engine)
if "listings" in _inspector.get_table_names():
    _existing_columns = {c["name"] for c in _inspector.get_columns("listings")}
    if "views_count" not in _existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE listings ADD COLUMN views_count INTEGER NOT NULL DEFAULT 0"))
    if "district" not in _existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE listings ADD COLUMN district VARCHAR"))
    if "channel_message_ids" not in _existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE listings ADD COLUMN channel_message_ids VARCHAR"))
    if "currency" not in _existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE listings ADD COLUMN currency VARCHAR NOT NULL DEFAULT 'USD'"))

app = FastAPI(title="Avto E'lonlar Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mini App domenini production'da aniq ko'rsating
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Juda ko'p so'rov yuborildi. Birozdan keyin qayta urinib ko'ring."},
    )

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(listings.router)
app.include_router(meta.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ============================================================
# Telegram bot — WEBHOOK rejimi
# ============================================================
# Bepul serverlarda (masalan Render) alohida "background worker" pullik bo'lgani
# uchun, bot alohida jarayon sifatida emas, shu web-service ICHIDA webhook orqali
# ishlaydi. Telegram har bir yangi xabarni shu manzilga POST qiladi.
#
# WEBHOOK_SECRET — tasodifiy maxfiy so'z, faqat siz va Telegram bilishi kerak,
# shunda begona odam shu manzilga soxta so'rov yubora olmaydi.
# DIQQAT: standart qiymat qo'yilmaydi — .env'da sozlanmagan bo'lsa, har safar server
# ishga tushganda tasodifiy so'z generatsiya qilinadi (oldindan taxmin qilib bo'lmaydigan
# "changeme" kabi ma'lum qiymatning production'da qolib ketishining oldini olish uchun).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    WEBHOOK_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "WEBHOOK_SECRET .env'da sozlanmagan — tasodifiy qiymat generatsiya qilindi. "
        "Production'da barqaror ishlashi uchun .env faylida WEBHOOK_SECRET'ni o'zingiz belgilang."
    )
WEBHOOK_PATH = f"/telegram/webhook/{WEBHOOK_SECRET}"


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot sozlanmagan (BOT_TOKEN yo'q)")
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.on_event("startup")
async def start_exchange_rate_loop():
    # Alohida fon vazifasi sifatida ishga tushiriladi — CBU'ga so'rov yuborish
    # (yoki uning muvaffaqiyatsizligi) asosiy so'rovlarni bloklamasligi kerak.
    asyncio.create_task(daily_refresh_loop())


@app.on_event("startup")
async def set_telegram_webhook():
    if bot is None:
        return
    await resolve_bot_username()  # kanal xabaridagi tugma uchun bot @username'ini oladi

    if not PUBLIC_URL:
        return  # lokal test paytida webhook o'rnatilmaydi — bot/bot.py orqali polling ishlating
    await bot.set_webhook(f"{PUBLIC_URL}{WEBHOOK_PATH}")
    await setup_menu_button()


# ============================================================
# Frontend (Mini App) — bitta bepul servisda birga joylashtirish uchun
# ============================================================
# Bu FastAPI ilovasi backend + bot webhook + statik frontend'ni bitta domenda
# xizmat qiladi, shunda Render'ning bitta bepul Web Service'i yetarli bo'ladi.
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
