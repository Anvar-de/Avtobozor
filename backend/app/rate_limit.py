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

from .telegram_auth import validate_init_data


def get_client_ip(request: Request) -> str:
    """Haqiqiy mijoz IP'sini topadi.

    Render oldida Cloudflare ham turadi (client -> Cloudflare -> Render ->
    ilova) — ya'ni bir nechta proksi bosqichi bor. `CF-Connecting-IP`
    Cloudflare tomonidan qo'yiladigan va o'zgartirib bo'lmaydigan sarlavha
    bo'lib, har doim haqiqiy mijoz IP'sini ko'rsatadi — shuning uchun eng
    ishonchli manba. Uni topa olmasak, `X-Forwarded-For`dagi birinchi
    (eng chapdagi) manzilga qaytamiz — bu ham odatiy holatda asl mijoz
    bo'ladi (keyingi bosqichlar o'z manzilini o'ngga qo'shib boradi).
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
    return get_client_ip(request)


limiter = Limiter(key_func=rate_limit_key)
