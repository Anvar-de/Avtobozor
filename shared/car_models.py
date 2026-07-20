"""Avtomobil modellari va ularning taxalluslari/yozilish variantlari.

Bir xil real model turli sotuvchilar tomonidan turlicha yozilishi yoki
O'zbekiston bozorida boshqa nom bilan qayta belgilanishi (rebadge) mumkin
(masalan Chevrolet Lacetti -> Gentra). Bu lug'at qidiruv so'zini kanonik
model nomiga bog'lash uchun ishlatiladi (backend/app/search_utils.py da).

Har bir alias PASTKI REGISTRDA va LOTIN alifbosida yozilgan bo'lishi kerak
(qidiruv so'zi solishtirilishdan oldin shu ko'rinishga normalizatsiya
qilinadi) — Kirill varianti kerak emas, transliteratsiya avtomatik ishlaydi.

Faqat imlosi chindan ham ko'p xilma-xil bo'ladigan yoki qayta nomlangan
modellar uchun yozuv qo'shing — har bir alias fuzzy-moslik yuzasi bo'lgani
uchun keraksiz yozuvlar soxta moslikni oshiradi.
"""

CAR_MODEL_ALIASES: dict[str, list[str]] = {
    "Gentra": ["gentra", "jentra", "lacetti", "lasetti"],
    "Cobalt": ["cobalt", "kobalt", "kobilt"],
    "Nexia": ["nexia", "neksiya", "neksia", "nexiya"],
    "Malibu": ["malibu", "malibu2", "malibu 2"],
    "Spark": ["spark", "matiz"],
    "Damas": ["damas"],
    "Labo": ["labo"],
    "Onix": ["onix", "onyx"],
    "Tracker": ["tracker"],
    "Captiva": ["captiva"],
    "Equinox": ["equinox"],
    "Traverse": ["traverse"],
    "Orlando": ["orlando"],
}
