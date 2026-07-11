import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Text, Boolean,
    DateTime, ForeignKey, Enum
)
from sqlalchemy.orm import relationship

from shared.database import Base


class ListingStatus(str, enum.Enum):
    pending = "pending"      # admin tasdig'ini kutmoqda
    approved = "approved"    # e'lonlar ro'yxatida ko'rinadi
    rejected = "rejected"    # admin rad etgan
    sold = "sold"            # sotuvchi o'zi "sotildi" deb belgilagan


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    listings = relationship("Listing", back_populates="owner", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    brand = Column(String, nullable=False)          # Chevrolet, Nexia...
    model = Column(String, nullable=False)           # Cobalt, Malibu...
    year = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)            # dollarda ($)
    mileage = Column(Integer, nullable=False)         # km
    transmission = Column(String, nullable=True)      # avtomat / mexanika
    fuel_type = Column(String, nullable=True)         # benzin / gaz / dizel / gibrid
    region = Column(String, nullable=True)            # Toshkent, Samarqand...
    district = Column(String, nullable=True)           # Chilonzor, Chust...
    description = Column(Text, nullable=True)
    contact_phone = Column(String, nullable=True)

    status = Column(Enum(ListingStatus), default=ListingStatus.pending, nullable=False)
    views_count = Column(Integer, default=0, nullable=False)
    # Kanalga joylangan post(lar)ning xabar ID'lari, vergul bilan ajratilgan
    # (masalan albom + alohida tugmali xabar bo'lsa bir nechta bo'ladi) —
    # e'lon o'chirilganda kanaldagi postni ham o'chirish uchun kerak.
    channel_message_ids = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="listings")
    photos = relationship("Photo", back_populates="listing", cascade="all, delete-orphan")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    file_path = Column(String, nullable=False)   # /uploads/xxx.jpg
    position = Column(Integer, default=0)         # galereyadagi tartib

    listing = relationship("Listing", back_populates="photos")
