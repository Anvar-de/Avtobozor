from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from shared.models import ListingStatus


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
    brand: str
    model: str
    year: int
    price: float
    mileage: int
    transmission: Optional[str] = None
    fuel_type: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None
    contact_phone: Optional[str] = None


class ListingUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    price: Optional[float] = None
    mileage: Optional[int] = None
    transmission: Optional[str] = None
    fuel_type: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None
    contact_phone: Optional[str] = None
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
    description: Optional[str] = None
    contact_phone: Optional[str] = None
    status: ListingStatus
    created_at: datetime
    photos: list[PhotoOut] = []

    model_config = ConfigDict(from_attributes=True)
