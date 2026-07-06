import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# PostgreSQL uchun: postgresql://user:password@localhost:5432/car_marketplace
# Tez boshlash uchun SQLite ham ishlaydi (DATABASE_URL ni o'zgartirmasangiz)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./car_marketplace.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
