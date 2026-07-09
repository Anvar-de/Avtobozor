import io
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from PIL import Image
from sqlalchemy.orm import Session, joinedload

from shared.database import get_db
from shared.models import Listing, Photo, ListingStatus
from ..telegram_auth import get_telegram_user
from ..telegram_notify import notify_admin_new_listing
from ..schemas import ListingCreate, ListingUpdate, ListingOut
from .auth import get_or_create_user

router = APIRouter(prefix="/api/listings", tags=["listings"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
# Kengaytma shu xaritadan olinadi (foydalanuvchi yuborgan fayl nomidan emas) —
# aks holda hujumchi ".jpg" rasm sifatida ".svg"/".html" fayl yuklab, XSS qilishi mumkin edi.
# Kengaytma brauzer yuborgan Content-Type'dan emas, Pillow aniqlagan HAQIQIY
# formatdan olinadi — ba'zi brauzer/WebView'lar PNG/WEBP fayllar uchun noaniq
# yoki boshqacha Content-Type yuborishi mumkin, bu esa haqiqiy rasmni asossiz rad etardi.
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_PHOTOS_PER_LISTING = 8


@router.get("", response_model=list[ListingOut])
def list_listings(
    db: Session = Depends(get_db),
    brand: Optional[str] = None,
    region: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    limit: int = Query(30, le=100),
    offset: int = 0,
):
    """Faqat tasdiqlangan e'lonlarni, filtrlar bilan qaytaradi (ochiq ro'yxat sahifasi)."""
    q = db.query(Listing).options(joinedload(Listing.photos)).filter(
        Listing.status == ListingStatus.approved
    )
    if brand:
        q = q.filter(Listing.brand.ilike(f"%{brand}%"))
    if region:
        q = q.filter(Listing.region.ilike(f"%{region}%"))
    if min_price is not None:
        q = q.filter(Listing.price >= min_price)
    if max_price is not None:
        q = q.filter(Listing.price <= max_price)
    if min_year is not None:
        q = q.filter(Listing.year >= min_year)
    if max_year is not None:
        q = q.filter(Listing.year <= max_year)

    return q.order_by(Listing.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/my", response_model=list[ListingOut])
def my_listings(
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
def get_listing(
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

    return listing


@router.post("", response_model=ListingOut)
async def create_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """Yangi e'lon yaratadi — status avtomatik 'pending' bo'ladi va admin xabar oladi."""
    user = get_or_create_user(db, tg_user)
    listing = Listing(user_id=user.id, **payload.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)

    await notify_admin_new_listing(listing)
    return listing


@router.post("/{listing_id}/photos", response_model=ListingOut)
async def upload_photo(
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

    contents = await file.read()
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
    except Exception:
        raise HTTPException(status_code=400, detail="Fayl haqiqiy rasm emas")

    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(status_code=400, detail="Faqat JPEG, PNG yoki WEBP rasm qabul qilinadi")

    ext = ALLOWED_IMAGE_FORMATS[fmt]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(contents)

    position = len(listing.photos)
    photo = Photo(listing_id=listing.id, file_path=f"/uploads/{filename}", position=position)
    db.add(photo)
    db.commit()
    db.refresh(listing)
    return listing


@router.patch("/{listing_id}", response_model=ListingOut)
def update_listing(
    listing_id: int,
    payload: ListingUpdate,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    """E'lonni tahrirlash. Foydalanuvchi faqat o'z e'lonini va statusni (masalan 'sold') o'zgartira oladi."""
    user = get_or_create_user(db, tg_user)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu sizning e'loningiz emas")

    update_data = payload.model_dump(exclude_unset=True)
    # Oddiy foydalanuvchi statusni faqat "sold" ga o'zgartira oladi, boshqacha yo'l admin bot orqali
    if "status" in update_data and update_data["status"] != ListingStatus.sold:
        update_data.pop("status")

    for field, value in update_data.items():
        setattr(listing, field, value)

    db.commit()
    db.refresh(listing)
    return listing


@router.delete("/{listing_id}")
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    tg_user: dict = Depends(get_telegram_user),
):
    user = get_or_create_user(db, tg_user)
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    if listing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu sizning e'loningiz emas")

    db.delete(listing)
    db.commit()
    return {"ok": True}
