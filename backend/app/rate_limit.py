"""
So'rovlarni cheklash (rate limiting).

Bitta foydalanuvchidan (yoki bot/skriptdan) haddan tashqari ko'p so'rov kelsa,
serverni (va DB ulanish pulini) band qilib qo'ymasligi uchun har bir endpoint
daqiqasiga necha marta chaqirilishi mumkinligini cheklaymiz. `limiter` shu
modulda alohida turadi — main.py va routerlar orasida aylanma import
(circular import) bo'lmasligi uchun.
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .telegram_auth import validate_init_data


def rate_limit_key(request: Request) -> str:
    """Imkon qadar IP o'rniga Telegram foydalanuvchi ID'sidan foydalanadi.

    Faqat IP bo'yicha cheklasak, bitta tarmoq/qurilmadan (masalan bir xil
    Wi-Fi'dan) kirgan ikki xil Telegram akkaunt bitta "mijoz" sifatida
    ko'rinib, biri limitga tegsa ikkinchisi ham asossiz bloklanib qolardi.
    Himoyalangan so'rovlarda `X-Telegram-Init-Data` sarlavhasi allaqachon
    bor — undan haqiqiy foydalanuvchi ID'sini olib, cheklovni aynan o'sha
    foydalanuvchiga qo'llaymiz. Sarlavha bo'lmagan (ochiq) endpointlarda
    IP'ga qaytiladi.
    """
    init_data = request.headers.get("x-telegram-init-data")
    if init_data:
        try:
            user = validate_init_data(init_data)
            telegram_id = user.get("id")
            if telegram_id is not None:
                return f"tg:{telegram_id}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key)
