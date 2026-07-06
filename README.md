# Avto E'lonlar — Telegram Mini App

Foydalanuvchilar o'zlari avtomobil sotuv e'lonlarini joylaydigan Telegram Mini App.

## Tuzilma

```
car_marketplace/
├── shared/            # Backend va bot uchun umumiy DB modellari
│   ├── database.py
│   └── models.py
├── backend/            # FastAPI server
│   ├── app/
│   │   ├── main.py
│   │   ├── schemas.py
│   │   ├── telegram_auth.py     # initData tekshirish (HMAC)
│   │   ├── telegram_notify.py   # Adminga xabar yuborish
│   │   └── routers/
│   │       ├── auth.py
│   │       └── listings.py
│   └── requirements.txt
├── bot/                # aiogram bot (/start va moderatsiya tugmalari)
│   ├── bot.py
│   └── requirements.txt
├── frontend/           # Mini App (Telegram WebApp SDK)
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
└── .env.example
```

## Qanday ishlaydi

1. Foydalanuvchi botga `/start` yozadi → bot Mini App tugmasini ko'rsatadi.
2. Mini App ochilganda Telegram avtomatik `initData` beradi — bu orqali backend foydalanuvchini tasdiqlaydi (parol shart emas).
3. Foydalanuvchi "+" tugmasi orqali yangi e'lon joylaydi → status avtomatik **"pending"** bo'ladi.
4. Backend adminga (sizga) tasdiqlash/rad etish tugmali xabar yuboradi.
5. Admin botda tugmani bosishi bilan e'lon holati yangilanadi — tasdiqlangan e'lonlar ochiq ro'yxatda ko'rinadi.

## Ishga tushirish (lokal test)

### 1. Muhit o'zgaruvchilari

```bash
cp .env.example .env
# .env faylni oching va BOT_TOKEN, ADMIN_CHAT_ID ni to'ldiring
```

BotFather orqali token oling: Telegram'da `@BotFather` → `/newbot`.
O'z Telegram ID'ingizni bilish uchun: `@userinfobot`.

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
cd ..
uvicorn backend.app.main:app --reload --port 8000
```

Tekshirish: http://localhost:8000/api/health → `{"status": "ok"}`
API hujjatlari: http://localhost:8000/docs

### 3. Bot

```bash
cd bot
pip install -r requirements.txt
cd ..
python bot/bot.py
```

### 4. Frontend

Eng oson yo'l — lokal statik server:

```bash
cd frontend
python3 -m http.server 5500
```

`frontend/js/app.js` faylida `API_BASE_URL` ni backend manzilingizga moslang (masalan `window.API_BASE_URL = "http://localhost:8000"` — buni `index.html` ichiga `<script>` orqali app.js dan OLDIN qo'shing).

**Diqqat:** Telegram Mini App faqat **HTTPS** manzillarda ishlaydi. Lokal test uchun [ngrok](https://ngrok.com) yoki shunga o'xshash tunnel xizmatidan foydalaning:

```bash
ngrok http 5500
```

Chiqqan HTTPS manzilni `.env` faylidagi `MINI_APP_URL` ga qo'ying va botni qayta ishga tushiring.

## Bepul serverga joylashtirish (kartasiz, pulsiz)

Loyiha shunday qurilganki, **bitta bepul Render Web Service** backend + bot + frontend'ni birga
ko'taradi (bot alohida "background worker" talab qilmaydi — u webhook orqali shu servis ichida ishlaydi).

### 1-qadam: Ma'lumotlar bazasi — Neon (bepul, kartasiz, muddatsiz)

1. https://neon.tech ga GitHub orqali kiring (karta so'ralmaydi)
2. Yangi loyiha yarating, PostgreSQL connection string'ni nusxalab oling
   (`postgresql://user:pass@ep-xxxx.neon.tech/dbname?sslmode=require` ko'rinishida)
3. Buni keyingi qadamda `DATABASE_URL` sifatida ishlatasiz

> Neon'ning bepul rejasi doimiy (30 kunlik sinov emas): loyiha boshida yetarli
> bo'ladigan hajm va resurs beradi, karta talab qilmaydi.

### 2-qadam: Kodni GitHub'ga yuklash

```bash
cd car_marketplace
git init
git add .
git commit -m "Avto e'lonlar mini app"
```

GitHub'da yangi (public yoki private) repo yarating va push qiling.

### 3-qadam: Render'da Web Service yaratish (bepul, kartasiz)

1. https://render.com ga GitHub orqali kiring
2. **New → Web Service** → GitHub repongizni tanlang
3. Sozlamalar:
   - **Root Directory**: bo'sh qoldiring (loyihaning ildizi)
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
4. **Environment Variables** bo'limiga quyidagilarni qo'shing:
   - `BOT_TOKEN` — BotFather'dan olingan token
   - `ADMIN_CHAT_ID` — sizning Telegram ID'ingiz (`@userinfobot` orqali biling)
   - `DATABASE_URL` — Neon'dan olgan connection string
   - `WEBHOOK_SECRET` — o'zingiz o'ylab topgan tasodifiy so'z
   - `SKIP_TELEGRAM_VALIDATION` — `false`
5. **Create Web Service** tugmasini bosing

Bir necha daqiqadan so'ng sizga `https://sizning-servis.onrender.com` ko'rinishidagi
manzil beriladi. Backend ishga tushganda bot webhook'ni **o'zi avtomatik** o'rnatadi
(`RENDER_EXTERNAL_URL` orqali) — qo'shimcha sozlash shart emas.

### 4-qadam: Tekshirish

- `https://sizning-servis.onrender.com/api/health` → `{"status": "ok"}` ko'rinishi kerak
- Telegram botingizga `/start` yozing → Mini App tugmasi chiqishi kerak

### Bepul tarifning muhim cheklovlari

- **Uyquga ketish**: 15 daqiqa faoliyatsizlikdan so'ng servis "uxlab qoladi", keyingi
  so'rov 30-60 soniya kutishi mumkin. Oddiy shaxsiy loyiha uchun bu me'yorda.
- **Rasmlar vaqtinchalik**: bepul tarifda disk doimiy emas — har safar qayta deploy
  qilganingizda `uploads/` papkasidagi rasmlar o'chib ketadi (ma'lumotlar bazasi
  Neon'da alohida saqlangani uchun **yo'qolmaydi**, faqat rasm fayllari). Loyiha
  kattalashsa, rasmlarni Cloudflare R2 kabi bepul bulut xotiraga ko'chirish tavsiya etiladi.
- **750 soat/oy**: bitta servis uchun bu doimiy ishlashga yetarli.

### Frontendni alohida joylashtirmoqchi bo'lsangiz

Agar xohlasangiz, `frontend/` papkasini alohida GitHub Pages yoki Render Static Site'da
ham joylashtirish mumkin (ular umuman uxlamaydi). Bunday holda `frontend/index.html`
ichiga `app.js`dan oldin quyidagini qo'shing:

```html
<script>window.API_BASE_URL = "https://sizning-backend.onrender.com";</script>
```

Lekin oddiy boshlash uchun hozirgi "hammasi bitta servisda" usuli tavsiya etiladi —
bitta joyni kuzatib, bitta joyga deploy qilasiz.

## Boshqa umumiy tavsiyalar

- CORS'da `allow_origins=["*"]` o'rniga productionda faqat o'z domeningizni qo'shsangiz xavfsizroq bo'ladi
- `WEBHOOK_SECRET`ni hech kimga oshkor qilmang — bu begonalarning botingizga soxta xabar yuborishining oldini oladi
- Loyiha jiddiy o'sib, foydalanuvchilar ko'paysa, Render'ning pullik "Starter" tarifiga ($7/oy) o'tish uyquga ketish muammosini butunlay yo'qotadi
