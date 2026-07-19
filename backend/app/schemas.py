from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.models import ListingStatus

CURRENT_YEAR = datetime.now().year

# Narxning yuqori sanity-chegarasi — valyutaga qarab boshqacha, chunki 10 million
# so'm mashinaning narxi bo'la olmaydi, lekin 10 million dollar (o'ta keng
# zaxira bilan) bo'lishi mumkin. Bu qattiq biznes qoidasi emas, faqat
# nomuvofiq/xato kiritilgan qiymatlarni ushlab qolish uchun keng chegara.
MAX_PRICE_BY_CURRENCY = {"USD": 10_000_000, "UZS": 150_000_000_000}


class PhotoOut(BaseModel):
    id: int
    file_path: str
    position: int

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_admin: bool = False

    model_config = ConfigDict(from_attributes=True)


class ListingCreate(BaseModel):
    brand: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=50)
    year: int = Field(..., ge=1970, le=CURRENT_YEAR + 1, description="1970 dan hozirgi yilgacha")
    currency: Literal["USD", "UZS"] = "USD"
    price: float = Field(..., gt=0, description="Narx, `currency` maydonidagi valyutada")
    mileage: int = Field(..., ge=0, le=2_000_000, description="km, manfiy bo'lmasligi kerak")
    transmission: Optional[str] = Field(None, max_length=30)
    fuel_type: Optional[str] = Field(None, max_length=30)
    region: str = Field(..., min_length=1, max_length=50)
    district: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=300)
    contact_phone: str = Field(..., min_length=1, max_length=20)

    @field_validator("brand", "model", "region", "contact_phone")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Bo'sh bo'lishi mumkin emas")
        return v.strip()

    @field_validator("price")
    @classmethod
    def price_within_currency_range(cls, v: float, info) -> float:
        currency = info.data.get("currency", "USD")
        max_allowed = MAX_PRICE_BY_CURRENCY[currency]
        if v > max_allowed:
            raise ValueError(f"Narx {max_allowed:,} {currency} dan katta bo'lmasligi kerak")
        return v


class ListingUpdate(BaseModel):
    brand: Optional[str] = Field(None, min_length=1, max_length=50)
    model: Optional[str] = Field(None, min_length=1, max_length=50)
    year: Optional[int] = Field(None, ge=1970, le=CURRENT_YEAR + 1)
    currency: Optional[Literal["USD", "UZS"]] = None
    price: Optional[float] = Field(None, gt=0)
    mileage: Optional[int] = Field(None, ge=0, le=2_000_000)
    transmission: Optional[str] = Field(None, max_length=30)
    fuel_type: Optional[str] = Field(None, max_length=30)
    region: Optional[str] = Field(None, max_length=50)
    district: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=300)
    contact_phone: Optional[str] = Field(None, max_length=20)
    status: Optional[ListingStatus] = None

    @field_validator("price")
    @classmethod
    def price_within_currency_range(cls, v: Optional[float], info) -> Optional[float]:
        # `currency` shu so'rovda kelmagan bo'lishi mumkin (masalan faqat status
        # o'zgartirilsa) — bu holda mavjud yozuvning qaysi valyutada ekanini bu
        # yerda bilib bo'lmaydi, shuning uchun eng keng chegara bilan tekshiramiz.
        if v is None:
            return v
        currency = info.data.get("currency") or "UZS"
        max_allowed = MAX_PRICE_BY_CURRENCY[currency]
        if v > max_allowed:
            raise ValueError(f"Narx {max_allowed:,} {currency} dan katta bo'lmasligi kerak")
        return v


class ListingOut(BaseModel):
    id: int
    user_id: int
    brand: str
    model: str
    year: int
    price: float
    currency: str
    mileage: int
    transmission: Optional[str] = None
    fuel_type: Optional[str] = None
    region: Optional[str] = None
    district: Optional[str] = None
    description: Optional[str] = None
    contact_phone: Optional[str] = None
    status: ListingStatus
    views_count: int = 0
    created_at: datetime
    photos: list[PhotoOut] = []

    model_config = ConfigDict(from_attributes=True)
