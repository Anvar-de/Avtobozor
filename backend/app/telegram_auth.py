"""
Telegram Mini App foydalanuvchini tasdiqlash.

Mini App ochilganda Telegram frontendga `initData` degan qatorni beradi.
Backend shu qatorni bot tokeni yordamida HMAC orqali tekshiradi —
shunda foydalanuvchi haqiqatan ham Telegram orqali kirganiga ishonch hosil qilamiz.
Batafsil: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Lokal test paytida frontendni haqiqiy Telegramsiz tekshirish uchun (productionda albatta False qiling!)
SKIP_TELEGRAM_VALIDATION = os.getenv("SKIP_TELEGRAM_VALIDATION", "false").lower() == "true"


def validate_init_data(init_data: str) -> dict:
    """initData satrini tekshiradi va ichidagi `user` obyektini qaytaradi."""
    if SKIP_TELEGRAM_VALIDATION:
        # Dev rejimida frontend soxta ma'lumot yuborishi mumkin: {"user": {"id": 123, ...}}
        parsed = dict(parse_qsl(init_data))
        user_raw = parsed.get("user")
        return json.loads(user_raw) if user_raw else {"id": 111111, "first_name": "Test"}

    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN sozlanmagan")

    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="initData noto'g'ri: hash topilmadi")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData tasdiqlanmadi")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="initData ichida foydalanuvchi topilmadi")

    return json.loads(user_raw)


async def get_telegram_user(x_telegram_init_data: str = Header(...)) -> dict:
    """FastAPI dependency: har bir himoyalangan so'rovda Telegram foydalanuvchisini qaytaradi."""
    return validate_init_data(x_telegram_init_data)
