import asyncio
import io
import math
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Query
from PIL import Image
from pillow_heif import register_heif_opener
from sqlalchemy import String, and_, cast, or_
from sqlalchemy.orm import Session, joinedload

from shared.database import SessionLocal, get_db
from shared.models import ExchangeRate, Listing, Photo, ListingStatus
from shared.storage import save_photo, delete_photo
from ..rate_limit import limiter
from ..search_utils import expand_search_word
from ..telegram_auth import get_telegram_user
from ..telegram_bot import delete_channel_post
from ..telegram_notify import notify_admin_new_listing
from ..schemas import ListingCreate, ListingUpdate, ListingOut
from .auth import get_or_create_user, is_admin_user

register_heif_opener()

router = APIRouter(prefix="/api/listings", tags=["listings"])

# Kengaytma shu xaritadan olinadi (foydalanuvchi yuborgan fayl nomidan emas) —
# aks holda hujumchi ".jpg" rasm sifatida ".svg"/".html" fayl yuklab, XSS qilishi mumkin edi.
# Kengaytma brauzer yuborgan Content-Type'dan emas, Pillow aniqlagan HAQIQIY
# formatdan olinadi — ba'zi brauzer/WebView'lar PNG/WEBP fayllar uchun noaniq
# yoki boshqacha Content-Type yuborishi mumkin, bu esa haqiqiy rasmni asossiz rad etardi.
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_PHOTOS_PER_LISTING = 4
# Bitta rasm uchun maksimal hajm. Avvalgi kodda `file.read()` hajm chegarasisiz
# butun faylni xotiraga o'qirdi — foydalanuvchi juda katta fayl yuborib, worker
# xotirasini band qilishi (DoS) mumkin edi. Zamonaviy telefon suratlari odatda
# bir necha MB bo'lgani uchun 15MB amaliyotda yetarli zaxira bilan.
MAX_PHOTO_SIZE_BYTES = 15 * 1024 * 1024


async def _read_upload_within_limit(file: UploadFile, max_size: int) -> bytes:
    """Faylni bo'lak-bo'lak o'qib, `max_size`dan oshsa darhol to'xtaydi — shu
    tufayli hajm limitidan oshib ketgan fayl to'liq xotiraga yuklanib bo'lmaydi."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Fayl hajmi {max_size // (1024 * 1024)}MB dan katta bo'lmasligi kerak",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_and_normalize_photo(contents: bytes) -> tuple[bytes, str]:
    """Rasmni dekodlaydi (soxta/buzuq faylni rad etish uchun), HEIC/HEIF bo'lsa
    JPEG'ga konvertatsiya qiladi va EXIF metadatani (masalan GPS koordinatalari)
    tozalash uchun har doim qayta kodlaydi. Pillow'ning dekodlash/konvertatsiya
    ishi CPU-bog'liq bo'lgani uchun bu funksiya asyncio.to_thread orqali
    alohida oqimda chaqiriladi — aks holda katta rasm butun event loop'ni
    (shu jumladan Telegram webhook so'rovlarini ham) bloklab qo'yardi."""
    try:
        Image.open(io.BytesIO(contents)).verify()
        # verify() faqat fayl strukturasini tekshiradi, piksellarni to'liq
        # dekodlamaydi — ba'zi buzuq fayllar shu tekshiruvdan o'tib ketib,
        # keyinroq (masalan kanal kollajida) dekodlashda muvaffaqiyatsiz bo'lishi
        # mumkin edi. Shuning uchun bu yerda to'liq dekodlab ko'ramiz (verify()
        # dan keyin obyektni qayta ishlatib bo'lmaydi, shu sabab qayta ochamiz).
        img = Image.open(io.BytesIO(contents))
        img.load()
        fmt = img.format
    except Exception as exc:
        raise ValueError("Fayl haqiqiy rasm emas") from exc

    if fmt in ("HEIF", "HEIC"):
        # iPhone'lar odatda HEIC formatida suratga oladi — brauzerlar buni
        # ko'rsata olmaydi, shu sabab JPEG'ga konvertatsiya qilib saqlaymiz.
        fmt = "JPEG"

    if fmt not in ALLOWED_IMAGE_FORMATS:
        return contents, fmt  # chaqiruvchi buni rad etadi (400) — qayta kodlashning hojati yo'q

    # EXIF (GPS, qurilma modeli va h.k.) hamda rasm ma'lumotidan keyin
    # qo'shib yuborilishi mumkin bo'lgan har qanday yashirin baytlarni olib
    # tashlash uchun rasmni PIL orqali qayta kodlaymiz — `exif=` parametri
    # berilmagani sababli Pillow uni natijaga ko'chirmaydi. Avval bu faqat
    # HEIC uchun bajarilardi, JPEG/PNG/WEBP esa asl baytlari bilan (EXIF'i
    # saqlangan holda) yozilardi.
    if fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        # JPEG shaffoflikni (alpha kanalni) qo'llab-quvvatlamaydi.
        img = img.convert("RGB")
    buffer = io.BytesIO()
    save_kwargs = {"quality": 92} if fmt == "JPEG" else {}
    img.save(buffer, format=fmt, **save_kwargs)
    contents = buffer.getvalue()

    return contents, fmt


def _price_filter(db: Session, currency: str, min_price: Optional[float], max_price: Optional[float]):
    """Narx filtrini quradi — foydalanuvchi qidirgan valyutadagi e'lonlar ANIQ
    oraliqda, boshqa valyutadagi e'lonlar esa CBU'dan kunlik olingan kursga
    asoslanib o'girilgan (tashqariga qarab yaxlitilangan) oraliqda qidiriladi.
    Narxning o'zi hech qachon o'zgartirilmaydi/ko'rsatilmaydi — bu faqat
    qidiruv uchun ichkarida ishlatiladi.

    Agar hali birorta kurs saqlanmagan bo'lsa (cold-start), faqat qidirilgan
    valyutadagi e'lonlar bilan cheklanadi — konvertatsiya qilib bo'lmaydi."""
    same_currency_conditions = [Listing.currency == currency]
    if min_price is not None:
        same_currency_conditions.append(Listing.price >= min_price)
    if max_price is not None:
        same_currency_conditions.append(Listing.price <= max_price)

    latest_rate = (
        db.query(ExchangeRate).order_by(ExchangeRate.fetched_at.desc()).first()
    )
    if latest_rate is None:
        return and_(*same_currency_conditions)

    rate = float(latest_rate.usd_to_uzs)
    other_currency = "UZS" if currency == "USD" else "USD"
    to_other = (lambda x: x * rate) if currency == "USD" else (lambda x: x / rate)

    other_currency_conditions = [Listing.currency == other_currency]
    if min_price is not None:
        other_currency_conditions.append(Listing.price >= math.floor(to_other(min_price)))
    if max_price is not None:
        other_currency_conditions.append(Listing.price <= math.ceil(to_other(max_price)))

    return or_(and_(*same_currency_conditions), and_(*other_currency_conditions))


@router.get("", response_model=list[ListingOut])
@limiter.limit("60/minute")
def list_listings(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    brand: Optional[str] = None,
    region: Optional[str] = None,
    district: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    price_currency: str = Query("USD", pattern="^(USD|UZS)$"),
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_mileage: Optional[int] = None,
    max_mileage: Optional[int] = None,
    limit: int = Query(30, le=100),
    offset: int = 0,
):
    """Faqat tasdiqlangan e'lonlarni, filtrlar bilan qaytaradi (ochiq ro'yxat sahifasi)."""
    q = db.query(Listing).options(joinedload(Listing.photos)).filter(
        Listing.status == ListingStatus.approved
    )
    if search:
        # Bitta qidiruv maydoni, bir nechta so'z bilan: har bir so'z e'londagi
        # to'ldirilgan istalgan maydonda (matnli yoki raqamli) topilishi kerak
        # (so'zlar orasida AND, bitta so'z uchun maydonlar orasida OR) —
        # masalan "Cobalt Toshkent" ikkala so'z ham mos kelgan e'lonlarni topadi.
        text_columns = [
            Listing.brand, Listing.model, Listing.transmission,
            Listing.fuel_type, Listing.region, Listing.district,
            Listing.description, Listing.contact_phone,
        ]
        numeric_columns = [Listing.year, Listing.price, Listing.mileage]
        for word in search.split():
            # Raqamsiz so'z (masalan "Cobalt") hech qachon raqamli ustunga mos
            # kelmaydi — shunday so'zlar uchun cast(...)+ilike qo'shimcha
            # ishlashni (har bir qatorda CAST hisoblashni) tashlab yuboramiz.
            if any(ch.isdigit() for ch in word):
                like = f"%{word}%"
                conditions = [col.ilike(like) for col in text_columns]
                conditions += [cast(col, String).ilike(like) for col in numeric_columns]
            else:
                # Imlo xatolari, kirill yozuvi va model taxalluslariga (masalan
                # "kobilt" -> Cobalt, "jentra"/"жентра" -> Gentra) chidamli
                # bo'lish uchun so'z bir nechta variantga kengaytiriladi.
                conditions = [
                    col.ilike(f"%{term}%")
                    for term in expand_search_word(word)
                    for col in text_columns
                ]
            q = q.filter(or_(*conditions))
    if brand:
        q = q.filter(Listing.brand.ilike(f"%{brand}%"))
    if region:
        q = q.filter(Listing.region.ilike(f"%{region}%"))
    if district:
        q = q.filter(Listing.district.ilike(f"%{district}%"))
    if min_price is not None or max_price is not None:
        q = q.filter(_price_filter(db, price_currency, min_price, max_price))
    if min_year is not None:
        q = q.filter(Listing.year >= min_year)
    if max_year is not None:
        q = q.filter(Listing.year <= max_year)
    if min_mileage is not None:
        q = q.filter(Listing.mileage >= min_mileage)
    if max_mileage is not None:
        q = q.filter(Listing.mileage <= max_mileage)

    return q.order_by(Listing.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/my", response_model=list[ListingOut])
@limiter.limit("30/minute")
def my_listings(
    request: Request,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """Foydalanuvchining o'z e'lonlari — statusidan qat'iy nazar (pending/approved/rejected/sold)."""
    user = get_or_create_user(db, tg_user)
    return (
        db.query(Listing)
        .options(joinedload(Listing.photos))
        .filter(Listing.user_id == user.id)
        .order_by(Listing.created_at.desc())
        .all()
    )


@router.get("/{listing_id}", response_model=ListingOut)
@limiter.limit("60/minute")
def get_listing(
    request: Request,
    listing_id: int,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """Tasdiqlangan e'lonni istalgan kishi, tasdiqlanmagan/rad etilganini esa faqat egasi ko'ra oladi."""
    listing = (
        db.query(Listing)
        .options(joinedload(Listing.photos))
        .filter(Listing.id == listing_id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")

    if listing.status != ListingStatus.approved:
        user = get_or_create_user(db, tg_user)
        if listing.user_id != user.id:
            raise HTTPException(status_code=404, detail="E'lon topilmadi")

    listing.views_count += 1
    db.commit()
    db.refresh(listing)

    return listing


@router.post("", response_model=ListingOut)
@limiter.limit("10/minute")
async def create_listing(
    request: Request,
    payload: ListingCreate,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """Yangi e'lon yaratadi — status avtomatik 'pending' bo'ladi. Admin xabari
    bu yerda emas, /submit chaqirilganda yuboriladi (shu vaqtga kelib rasmlar
    ham yuklab bo'lingan bo'ladi, xabarda ular ham ko'rinadi)."""
    user = get_or_create_user(db, tg_user)
    listing = Listing(user_id=user.id, **payload.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)

    return listing


@router.post("/{listing_id}/photos", response_model=ListingOut)
@limiter.limit("20/minute")
async def upload_photo(
    request: Request,
    listing_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """E'longa rasm qo'shadi. Faqat e'lon egasi rasm yuklay oladi."""
    user = get_or_create_user(db, tg_user)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu sizning e'loningiz emas")
    if len(listing.photos) >= MAX_PHOTOS_PER_LISTING:
        raise HTTPException(status_code=400, detail=f"Ko'pi bilan {MAX_PHOTOS_PER_LISTING} ta rasm yuklash mumkin")

    contents = await _read_upload_within_limit(file, MAX_PHOTO_SIZE_BYTES)
    try:
        contents, fmt = await asyncio.to_thread(_decode_and_normalize_photo, contents)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fayl haqiqiy rasm emas")

    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(status_code=400, detail="Faqat JPEG, PNG yoki WEBP rasm qabul qilinadi")

    ext = ALLOWED_IMAGE_FORMATS[fmt]
    filename = f"{uuid.uuid4().hex}{ext}"
    # save_photo (R2 rejimida) sinxron/blocking tarmoq chaqiruvi (boto3
    # put_object) — asyncio.to_thread orqali chaqirmasak, fayl R2'ga to'liq
    # yuklanib bo'lguncha butun event loop (va shu bilan Telegram webhook
    # so'rovlari ham) bloklanib qolardi.
    file_path = await asyncio.to_thread(save_photo, contents, filename)

    position = len(listing.photos)
    photo = Photo(listing_id=listing.id, file_path=file_path, position=position)
    db.add(photo)
    db.commit()
    db.refresh(listing)
    return listing


async def _notify_admin_background(listing_id: int) -> None:
    """submit_listing javob qaytargandan KEYIN, orqa fonda chaqiriladi —
    so'rovning DB session'i shu payt allaqachon yopilgan bo'lishi mumkinligi
    uchun (BackgroundTasks alohida ishga tushirilishiga tayanmasdan) o'zi
    yangi session ochib e'lonni qayta o'qiydi. Xatolik (masalan Telegram/R2
    sekinlik yoki xato) endi foydalanuvchini kutdirmaydi — u allaqachon
    javobni olib bo'lgan; xato faqat logga tushadi (notify_admin_new_listing
    ichida allaqachon shunday ishlaydi)."""
    db = SessionLocal()
    try:
        listing = (
            db.query(Listing)
            .options(joinedload(Listing.photos), joinedload(Listing.owner))
            .filter(Listing.id == listing_id)
            .first()
        )
        if listing:
            await notify_admin_new_listing(listing)
    finally:
        db.close()


@router.post("/{listing_id}/submit", response_model=ListingOut)
@limiter.limit("10/minute")
async def submit_listing(
    request: Request,
    listing_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """Rasmlarni yuklab bo'lgach chaqiriladi — shu payt admin (rasmlari va
    yuboruvchi havolasi bilan) xabar oladi. Xabar yuborish orqa fonda
    (javob qaytgandan keyin) bajariladi — shunda foydalanuvchi Telegram/R2
    sekinligini kutib turmaydi."""
    user = get_or_create_user(db, tg_user)
    listing = (
        db.query(Listing)
        .options(joinedload(Listing.photos))
        .filter(Listing.id == listing_id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu sizning e'loningiz emas")
    if not listing.photos:
        raise HTTPException(status_code=400, detail="Kamida 1 ta rasm yuklashingiz kerak")

    background_tasks.add_task(_notify_admin_background, listing.id)
    return listing


@router.patch("/{listing_id}", response_model=ListingOut)
@limiter.limit("20/minute")
def update_listing(
    request: Request,
    listing_id: int,
    payload: ListingUpdate,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """E'lonni tahrirlash. E'lon mazmunini (marka, narx, tavsif va h.k.) faqat
    ADMIN o'zgartira oladi. Oddiy foydalanuvchi — hatto egasi bo'lsa ham —
    faqat statusni "sold" ga o'zgartira oladi. Shu tufayli tasdiqlangan
    e'lon mazmunini egasi tasdiqdan keyin o'zgartirib, moderatsiyani
    chetlab o'tishi mumkin emas."""
    user = get_or_create_user(db, tg_user)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")

    is_owner = listing.user_id == user.id
    is_admin = is_admin_user(user.telegram_id)
    if not is_owner and not is_admin:
        raise HTTPException(status_code=403, detail="Bu sizning e'loningiz emas")

    update_data = payload.model_dump(exclude_unset=True)
    if not is_admin:
        # Oddiy foydalanuvchi (egasi bo'lsa ham) faqat statusni "sold"ga
        # o'zgartira oladi — boshqa hech qanday maydonni tahrirlay olmaydi.
        update_data = {"status": ListingStatus.sold} if update_data.get("status") == ListingStatus.sold else {}

    for field, value in update_data.items():
        setattr(listing, field, value)

    db.commit()
    db.refresh(listing)
    return listing


@router.delete("/{listing_id}")
@limiter.limit("10/minute")
async def delete_listing(
    request: Request,
    listing_id: int,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    user = get_or_create_user(db, tg_user)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    # Egasi o'zining e'lonini, admin esa kim joylashidan qat'iy nazar istalgan e'lonni o'chira oladi.
    if listing.user_id != user.id and not is_admin_user(user.telegram_id):
        raise HTTPException(status_code=403, detail="Bu sizning e'loningiz emas")

    photo_paths = [p.file_path for p in listing.photos]

    await delete_channel_post(listing)
    db.delete(listing)
    db.commit()

    # DB yozuvi o'chgandan keyin saqlash joyidagi (R2/disk) haqiqiy fayllarni
    # ham tozalaymiz — aks holda ular abadiy "etim" bo'lib qolib, bepul disk/R2
    # sig'imini asossiz to'ldirib boradi.
    for path in photo_paths:
        await asyncio.to_thread(delete_photo, path)

    return {"ok": True}
