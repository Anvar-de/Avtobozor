"""Narxni valyutasiga qarab odam o'qiydigan matnga aylantiradi.

Bot/kanal xabarlarida ishlatiladi — narx hech qachon boshqa valyutaga
o'girilmaydi, faqat sotuvchi kiritgan asl qiymat va valyuta ko'rsatiladi."""


def format_price(price: float, currency: str) -> str:
    if currency == "UZS":
        return f"{price:,.0f}".replace(",", " ") + " so'm"
    return f"${price:,.0f}"
