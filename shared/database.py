import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# PostgreSQL uchun: postgresql://user:password@localhost:5432/car_marketplace
# Tez boshlash uchun SQLite ham ishlaydi (DATABASE_URL ni o'zgartirmasangiz)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./car_marketplace.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping: har bir ulanishni pool'dan berishdan oldin engil "SELECT 1" bilan
# tekshiradi. Neon kabi bazalar harakatsizlikdan keyin avtomatik uxlab qoladi
# (auto-suspend) — shunda pool'da saqlangan eski ulanish "o'lik" bo'lib qoladi va
# birinchi so'rov "SSL connection has been closed unexpectedly" bilan qulaydi.
# pre_ping shu o'lik ulanishni avtomatik aniqlab, jim qayta ulaydi.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
