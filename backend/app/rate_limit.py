"""
So'rovlarni cheklash (rate limiting).

Bitta IP'dan haddan tashqari ko'p so'rov (masalan spam bot yoki xato tushib
qolgan skript) kelsa, serverni (va DB ulanish pulini) band qilib qo'ymasligi
uchun har bir endpoint daqiqasiga necha marta chaqirilishi mumkinligini
cheklaymiz. `limiter` shu modulda alohida turadi — main.py va routerlar
orasida aylanma import (circular import) bo'lmasligi uchun.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
