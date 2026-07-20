"""Qidiruv so'zlarini kanonik model nomlariga bog'lash: kirill->lotin
transliteratsiya va imlo xatolariga chidamli (fuzzy) moslik.

Taqqoslash faqat shared/car_models.py dagi kichik lug'at ustida bo'ladi —
bazadagi qatorlar soniga bog'liq emas, shuning uchun e'lonlar soni
ko'paysa ham qidiruv tezligiga ta'sir qilmaydi.
"""

from rapidfuzz import fuzz, process

from shared.car_models import CAR_MODEL_ALIASES

# O'zbek kirill alifbosi (rus kirillisi emas) — ў/қ/ғ/ҳ harflariga alohida
# e'tibor bering, chunki umumiy rus jadvali ularni noto'g'ri beradi.
_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}

FUZZY_THRESHOLD = 80
MIN_WORD_LEN_FOR_FUZZY = 4


def transliterate(text: str) -> str:
    return "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in text)


def normalize_word(word: str) -> str:
    return transliterate(word.lower().strip())


def _build_alias_index() -> tuple[dict[str, str], list[str]]:
    alias_to_canonical: dict[str, str] = {}
    all_aliases: list[str] = []
    for canonical, aliases in CAR_MODEL_ALIASES.items():
        for alias in [canonical.lower(), *aliases]:
            alias_to_canonical[alias] = canonical
            all_aliases.append(alias)
    return alias_to_canonical, all_aliases


_ALIAS_TO_CANONICAL, _ALL_ALIASES = _build_alias_index()


def expand_search_word(word: str) -> list[str]:
    """Bitta qidiruv so'zini normalizatsiya qiladi va qidiruv uchun mumkin
    bo'lgan variantlar to'plamini qaytaradi. Asl so'z HAR DOIM natijada
    qoladi (regressiyasiz). Baza (brend, model, hudud va h.k.) faqat lotin
    alifbosida saqlangani uchun normalizatsiya qilingan (kirill->lotin,
    kichik registr) shakl ham HAR DOIM qo'shiladi — shunday qilib "киа"
    kabi lug'atda yo'q so'zlar ham tegishli lotincha yozuvni (masalan "Kia"
    brendini) topa oladi, faqat model taxalluslariga cheklanmaydi. Bundan
    tashqari, agar so'z ma'lum model nomiga (aniq, alias yoki taxminiy/fuzzy)
    mos kelsa, o'sha kanonik model nomi va uning barcha taxalluslari ham
    qo'shiladi.
    """
    norm = normalize_word(word)
    result = {word, norm}

    canonical = _ALIAS_TO_CANONICAL.get(norm)
    if canonical is None and len(norm) >= MIN_WORD_LEN_FOR_FUZZY:
        match = process.extractOne(norm, _ALL_ALIASES, scorer=fuzz.ratio)
        if match and match[1] >= FUZZY_THRESHOLD:
            canonical = _ALIAS_TO_CANONICAL[match[0]]

    if canonical is not None:
        result.add(canonical)
        result.update(CAR_MODEL_ALIASES[canonical])

    return list(result)
