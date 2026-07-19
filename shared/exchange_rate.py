"""CBU'dan (O'zbekiston Markaziy banki) USD/UZS kursini kunlik olib, bazaga
saqlaydi. Bu kurs e'lon narxini ko'rsatishda HECH QACHON ishlatilmaydi (narx
doim o'z asl valyutasida ko'rsatiladi) — faqat valyutalararo qidiruv/filtrda
ichkarida ishlatiladi (backend/app/routers/listings.py)."""
import asyncio
import logging
from decimal import Decimal

import httpx

from shared.database import SessionLocal
from shared.models import ExchangeRate

logger = logging.getLogger("exchange_rate")

CBU_USD_RATE_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
FETCH_RETRIES = 3
FETCH_TIMEOUT_SECONDS = 10.0
REFRESH_INTERVAL_SECONDS = 24 * 60 * 60


async def _fetch_usd_rate_once() -> Decimal:
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
        resp = await client.get(CBU_USD_RATE_URL)
        resp.raise_for_status()
        data = resp.json()
    return Decimal(str(data[0]["Rate"]))


def _store_rate(rate: Decimal) -> None:
    db = SessionLocal()
    try:
        db.add(ExchangeRate(usd_to_uzs=rate))
        db.commit()
    finally:
        db.close()


def _has_any_rate() -> bool:
    db = SessionLocal()
    try:
        return db.query(ExchangeRate).first() is not None
    finally:
        db.close()


async def refresh_usd_rate() -> None:
    """CBU'dan USD kursini olib, `exchange_rates`ga yangi qator sifatida yozadi.
    Tarmoq/CBU vaqtincha ishlamasligi mumkinligi uchun bir necha marta (orasida
    kutib) urinadi. Barcha urinishlar muvaffaqiyatsiz bo'lsa, bazadagi eski
    kurs (bo'lsa) o'zgarishsiz qoladi — qidiruv o'sha eski kurs bilan davom
    etadi. Hech qachon xato ko'tarmaydi, shuning uchun chaqiruvchi (startup
    yoki fon tsikli) doim davom etaveradi.

    Baza chaqiruvlari (SQLAlchemy) sinxron/blocking bo'lgani uchun, bu funksiya
    yagona asosiy event loop'da ishlaydigan fon vazifasi sifatida chaqirilsa
    ham, ular asyncio.to_thread orqali alohida oqimda bajariladi — aks holda
    baza sekinlashgan/uyg'onayotgan paytda (masalan Neon auto-suspend'dan
    keyin) BUTUN ilova barcha foydalanuvchilar uchun bir necha soniyaga
    bloklanib qolar edi."""
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            rate = await _fetch_usd_rate_once()
            await asyncio.to_thread(_store_rate, rate)
            logger.info("USD/UZS kursi yangilandi: %s (urinish %d/%d)", rate, attempt, FETCH_RETRIES)
            return
        except Exception as exc:
            last_error = exc
            logger.warning("CBU'dan kurs olishda xatolik (urinish %d/%d): %s", attempt, FETCH_RETRIES, exc)
            if attempt < FETCH_RETRIES:
                await asyncio.sleep(2 ** attempt)  # 2s, keyin 4s

    has_any_rate = await asyncio.to_thread(_has_any_rate)
    if not has_any_rate:
        # Bazada birorta ham kurs yo'q — bu oddiy "bir kunlik xato"dan jiddiyroq,
        # chunki valyutalararo qidiruv butunlay ishlamay qoladi (cold-start).
        logger.error(
            "CBU'dan kurs olib bo'lmadi va bazada birorta ham kurs yo'q — "
            "valyutalararo qidiruv butunlay ishlamaydi. Oxirgi xatolik: %s", last_error,
        )
    else:
        logger.warning(
            "CBU'dan kurs olib bo'lmadi, bazadagi eski kurs bilan davom etiladi. Oxirgi xatolik: %s",
            last_error,
        )


async def daily_refresh_loop() -> None:
    """Ilova ishga tushganda bir marta, keyin har 24 soatda kursni yangilaydi.
    Bepul Render xizmati 15 daqiqa faoliyatsizlikdan keyin uxlab qolgani uchun,
    servis uxlab yotgan vaqtda bu tsikl ham to'xtab turadi — servis keyingi
    so'rov bilan uyg'onganda davom etadi. Bu holatda ham bazadagi eski kurs
    ishlatilaveradi, hech narsa buzilmaydi."""
    while True:
        await refresh_usd_rate()
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
