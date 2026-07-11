from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.models import ListingStatus

CURRENT_YEAR = datetime.now().year


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

    model_config = ConfigDict(from_attributes=True)


class ListingCreate(BaseModel):
    brand: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=50)
    year: int = Field(..., ge=1970, le=CURRENT_YEAR + 1, description="1970 dan hozirgi yilgacha")
    price: float = Field(..., gt=0, le=10_000_000, description="$ da, 0 dan katta bo'lishi kerak")
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


class ListingUpdate(BaseModel):
    brand: Optional[str] = Field(None, min_length=1, max_length=50)
    model: Optional[str] = Field(None, min_length=1, max_length=50)
    year: Optional[int] = Field(None, ge=1970, le=CURRENT_YEAR + 1)
    price: Optional[float] = Field(None, gt=0, le=10_000_000)
    mileage: Optional[int] = Field(None, ge=0, le=2_000_000)
    transmission: Optional[str] = Field(None, max_length=30)
    fuel_type: Optional[str] = Field(None, max_length=30)
    region: Optional[str] = Field(None, max_length=50)
    district: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=300)
    contact_phone: Optional[str] = Field(None, max_length=20)
    status: Optional[ListingStatus] = None


class ListingOut(BaseModel):
    id: int
    user_id: int
    brand: str
    model: str
    year: int
    price: float
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
