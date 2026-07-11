"""Avtomobil markalari ro'yxati.

E'lon yaratish formasidagi "Marka" maydoniga live search (yozganda mos
nomlarni taklif qilish) uchun ishlatiladi (frontend GET /api/car-brands
orqali oladi).
"""

CAR_BRANDS: list[str] = [
    "Acura", "Alfa Romeo", "Alpina", "Aro", "Asia", "Aston Martin", "Audi",
    "Aurus", "BAIC", "Belgee", "Bentley", "BMW", "Brilliance", "Buick", "BYD",
    "Cadillac", "Changan", "Chery", "Chevrolet", "Chrysler", "Citroen",
    "Cupra", "Dacia", "Daewoo", "Daihatsu", "Datsun", "Derways", "Dodge",
    "Dongfeng", "Eagle", "Evolute", "EXEED", "FAW", "Ferrari", "Fiat", "Ford",
    "GAC", "Geely", "Genesis", "Geo", "GMC", "Great Wall", "Hafei", "Haima",
    "Haval", "Honda", "Hongqi", "Hummer", "Hyundai", "Infiniti",
    "Iran Khodro", "Isuzu", "JAC", "Jaecoo", "Jaguar", "Jeep", "Jetour",
    "Kaiyi", "Kia", "Lamborghini", "Lancia", "Land Rover", "Lexus", "Lixiang",
    "Lifan", "Lincoln", "Lotus", "Luxgen", "Maserati", "Maybach", "Mazda",
    "Mercedes-Benz", "Mercury", "MG", "MINI", "Mitsubishi", "Mitsuoka",
    "Nissan", "Oldsmobile", "OMODA", "Opel", "Peugeot", "Plymouth",
    "Pontiac", "Porsche", "Proton", "RAM", "Ravon", "Renault",
    "Renault Samsung", "Rolls-Royce", "Rover", "Saab", "Saturn", "Scion",
    "SEAT", "Skoda", "Smart", "Solaris", "Sollers", "SsangYong", "Subaru",
    "Suzuki", "Tank", "TENET", "Tesla", "Tianye", "Toyota", "Volkswagen",
    "Volvo", "Vortex", "Voyah", "Zeekr", "Zotye", "ZX",
]
