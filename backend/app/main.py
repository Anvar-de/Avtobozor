import logging
import os
import secrets
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("main")

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram.types import Update
from sqlalchemy import inspect, text

from shared.database import Base, engine
from .routers import auth, listings
from .telegram_bot import bot, dp, setup_menu_button, resolve_bot_username

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

app = FastAPI(title="Avto E'lonlar Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mini App domenini production'da aniq ko'rsating
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(listings.router)


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
async def set_telegram_webhook():
    if bot is None:
        return
    await resolve_bot_username()  # kanal xabaridagi tugma uchun bot @username'ini oladi

    # Render bunday muhit o'zgaruvchisini avtomatik beradi (masalan
    # "https://sizning-servis.onrender.com"). Boshqa hostingda buni qo'lda
    # PUBLIC_URL sifatida sozlang.
    public_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")
    if not public_url:
        return  # lokal test paytida webhook o'rnatilmaydi — bot/bot.py orqali polling ishlating
    await bot.set_webhook(f"{public_url}{WEBHOOK_PATH}")
    await setup_menu_button()


# ============================================================
# Frontend (Mini App) — bitta bepul servisda birga joylashtirish uchun
# ============================================================
# Bu FastAPI ilovasi backend + bot webhook + statik frontend'ni bitta domenda
# xizmat qiladi, shunda Render'ning bitta bepul Web Service'i yetarli bo'ladi.
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
