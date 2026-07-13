"""E'lon rasmlarini saqlash.

Production'da Cloudflare R2'ga (S3-mos bulut ombori) yuklanadi — Render kabi
hostinglarning bepul diski vaqtinchalik bo'lgani uchun (qayta ishga tushganda
yuklangan fayllar o'chib ketadi), rasmlar doimiy joyda saqlanishi SHART.

R2 muhit o'zgaruvchilari (R2_*) sozlanmagan bo'lsa, faqat lokal test qulayligi
uchun diskka (UPLOAD_DIR) yozadi.
"""
import os
from urllib.parse import urljoin

import boto3
from botocore.config import Config

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "").strip()
# Bucket'ni ochiq ko'rish uchun manzil: yo Cloudflare bergan "r2.dev" test manzili,
# yoki bucket'ga ulangan o'zingizning domeningiz.
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").strip().rstrip("/")

R2_ENABLED = bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and R2_PUBLIC_URL)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_CONTENT_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

_client = None
if R2_ENABLED:
    _client = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
        # Standart boto3 timeout (~60s) R2 sekinlashsa yoki javob bermasa,
        # butun (sinxron) so'rovni shuncha vaqtga bloklab qo'yishi mumkin edi —
        # chegarani qisqartirib, muammo tezroq xato sifatida qaytishini ta'minlaymiz.
        config=Config(connect_timeout=5, read_timeout=15),
    )


def save_photo(contents: bytes, filename: str) -> str:
    """Rasmni saqlaydi va uni ko'rsatish uchun ishlatiladigan yo'l/URL'ni qaytaradi.

    R2 sozlangan bo'lsa — to'liq ochiq URL (masalan "https://pub-xxx.r2.dev/abc.jpg"),
    aks holda (faqat lokal test) — nisbiy yo'l ("/uploads/abc.jpg")."""
    if R2_ENABLED:
        content_type = _CONTENT_TYPES.get(os.path.splitext(filename)[1], "application/octet-stream")
        _client.put_object(Bucket=R2_BUCKET_NAME, Key=filename, Body=contents, ContentType=content_type)
        return f"{R2_PUBLIC_URL}/{filename}"

    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)
    return f"/uploads/{filename}"


def resolve_url(file_path: str, base_url: str) -> str:
    """`file_path` allaqachon to'liq URL bo'lsa (R2 rejimi) o'zini, aks holda
    (eski/lokal nisbiy `/uploads/...` yo'l) uni `base_url` bilan birlashtirib
    to'liq URL qaytaradi — Telegram'ga rasm URL sifatida yuborish uchun kerak."""
    if file_path.startswith("http://") or file_path.startswith("https://"):
        return file_path
    return urljoin(base_url.rstrip("/") + "/", file_path.lstrip("/"))
