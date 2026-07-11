"""O'zbekiston hududlari va ularga tegishli shahar/tumanlar ro'yxati.

E'lon yaratish formasidagi "Hudud" va "Shahar yoki tuman" dropdownlari
shu ro'yxatdan to'ldiriladi (frontend GET /api/regions orqali oladi).
"""

from typing import Optional

REGIONS: dict[str, list[str]] = {
    "Andijon viloyati": [
        "Oqoltin", "Oltinko'l", "Andijon", "Asaka", "Oxunboboyev", "Baliqchi",
        "Bo'z", "Buloqboshi", "Qorasuv", "Kuyganyor", "Qo'rg'ontepa", "Marhamat",
        "Poytug'", "Paxtaobod", "Xonobod", "Xo'jaobod", "Shahrixon", "Jalaquduq",
        "Izboskan", "Ulug'nor",
    ],
    "Buxoro viloyati": [
        "Olot", "Buxoro", "Vobkent", "Gazli", "Galaosiyo", "G'ijduvon", "Jondor",
        "Kogon", "Qorako'l", "Qorovulbozor", "Romitan", "Shofirkon", "Peshku",
    ],
    "Farg'ona viloyati": [
        "Oltiariq", "Bog'dod", "Beshariq", "Vodil", "Dang'ara", "Qo'qon", "Quva",
        "Quvasoy", "Langar", "Marg'ilon", "Navbahor", "Ravon", "Rishton",
        "Toshloq", "Uchko'prik", "Farg'ona", "Hamza", "Shohimardon", "Yozyovon",
        "Yaypan", "Yangi Marg'ilon", "Yangiqo'rg'on", "O'zbekiston", "Buvayda",
        "Qo'shtepa", "So'x", "Furqat",
    ],
    "Jizzax viloyati": [
        "Aydarko'l", "Balandchaqir", "Gagarin", "G'allaorol", "G'oliblar",
        "Dashtobod", "Jizzax", "Do'stlik", "Zomin", "Zarbdor", "Zafarobod",
        "Marjonbuloq", "Paxtakor", "O'smat", "Uchtepa", "Yangiqishloq", "Forish",
        "Baxmal", "Sh.Rashidov", "Mirzacho'l", "Arnasoy", "Yangiobod",
    ],
    "Navoiy viloyati": [
        "Beshrabot", "Zarafshon", "Konimex", "Karmana", "Qiziltepa", "Navoiy",
        "Nurota", "Tomdibuloq", "Uchquduq", "Yangirabot", "Xatirchi", "Navbahor",
        "Zafarobod",
    ],
    "Namangan viloyati": [
        "Jomasho'y", "Kosonsoy", "Namangan", "Pop", "Toshbuloq", "To'raqo'rg'on",
        "Uchqo'rg'on", "Xaqqulobod", "Chortoq", "Chust", "Norin", "Mingbuloq",
        "Uychi", "Yangiqo'rg'on", "Davlatobod", "Yangi Namangan",
    ],
    "Qashqadaryo viloyati": [
        "Beshkent", "G'uzor", "Dehqonobod", "Qamashi", "Qorashina", "Qarshi",
        "Koson", "Kasbi", "Kitob", "Muborak", "Mug'lon", "Talimarjon",
        "Chiroqchi", "Shahrisabz", "Yakkabog'", "Mirishkor", "Nishon", "Ko'kdala",
    ],
    "Qoraqalpog'iston Respublikasi": [
        "Oqmang'it", "Beruniy", "Bo'ston", "Qonliko'l", "Qorao'zak", "Kegeyli",
        "Qo'ng'irot", "Mang'it", "Mo'ynoq", "Nukus", "Taxiatosh", "Taxtako'pir",
        "To'rtko'l", "Chimboy", "Shumanay", "Xo'jayli", "Ellikqal'a", "Amudaryo",
        "Bo'zatov",
    ],
    "Samarqand viloyati": [
        "Oqtosh", "Bulung'ur", "Go'zalkent", "Gulobod", "Darband", "Jomboy",
        "Juma", "Ziyadin", "Ishtixon", "Kattaqo'rg'on", "Qo'shrabot", "Loish",
        "Nurobod", "Payariq", "Payshanba", "Samarqand", "Toyloq", "Urgut",
        "Chelak", "Narpay", "Pastdarg'om", "Paxtachi", "Oqdaryo",
    ],
    "Sirdaryo viloyati": [
        "Sirdaryo", "Baxt", "Boyovut", "Guliston", "Navro'z", "Sayxun",
        "Sardoba", "Xovos", "Shirin", "Yangiyer", "Sayxunobod", "Oqoltin",
        "Mirzaobod",
    ],
    "Surxondaryo viloyati": [
        "Angor", "Boysun", "Bandixon", "Denov", "Jarqo'rg'on", "Qorlik",
        "Qiziriq", "Qumqo'rg'on", "Muzrobod", "Sariosiyo", "Sariq", "Termiz",
        "Uzun", "Uchqizil", "Xalqobod", "Sharg'un", "Sherobod", "Sho'rchi",
        "Oltinsoy",
    ],
    "Toshkent viloyati": [
        "Oqqo'rg'on", "Olmaliq", "Angren", "Ohangaron", "Bekobod", "Katta Chimyon",
        "Bo'ka", "G'azalkent", "Gulbahor", "Durmen", "Do'stobod", "Zangiota",
        "Zafar", "Iskandar", "Qorasuv", "Keles", "Qibray", "Ko'ksaroy",
        "Krasnogorsk", "Mirobod", "Nazarbek", "To'ytepa", "Parkent", "Pskent",
        "Salar", "Turkiston", "O'rtaovul", "Xo'jakent", "Chorvoq", "Chinoz",
        "Chirchiq", "Eshonguzar", "Yangiobod", "Yangibozor", "Yangiyo'l",
        "Bo'stonliq", "Toshkent",
    ],
    "Xorazm viloyati": [
        "Bog'ot", "Gurlan", "Qorovul", "Qo'shko'pir", "Pitnak", "Urganch",
        "Xazorasp", "Xonqa", "Xiva", "Cholish", "Shovot", "Yangiariq",
        "Tuproqqal'a", "Yangibozor",
    ],
    "Toshkent shahri": [
        "Olmazor", "Bektemir", "Mirobod", "Mirzo Ulug'bek", "Sirg'ali",
        "Uchtepa", "Chilonzor", "Shayxontohur", "Yunusobod", "Yakkasaroy",
        "Yashnobod", "Yangihayot",
    ],
}


def format_location(region: Optional[str], district: Optional[str]) -> str:
    """"Tuman/shahar, Hudud" ko'rinishidagi manzil satrini qaytaradi — "viloyati"
    so'zisiz (masalan region="Andijon viloyati", district="Asaka" -> "Asaka, Andijon").
    Admin xabari va telegram kanal postida shu ko'rinishda ko'rsatiladi."""
    region_short = region.replace(" viloyati", "").strip() if region else None
    return ", ".join(part for part in (district, region_short) if part)
