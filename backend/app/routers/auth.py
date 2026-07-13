from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import User
from ..rate_limit import limiter
from ..telegram_auth import get_telegram_user
from ..telegram_bot import ADMIN_CHAT_ID
from ..schemas import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def is_admin_user(telegram_id: int) -> bool:
    return bool(ADMIN_CHAT_ID) and str(telegram_id) == str(ADMIN_CHAT_ID)


def get_or_create_user(db: Session, tg_user: dict) -> User:
    user = db.query(User).filter(User.telegram_id == tg_user["id"]).first()
    if user:
        return user

    full_name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")]))
    user = User(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        full_name=full_name or None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me", response_model=UserOut)
@limiter.limit("20/minute")
def get_me(request: Request, db: Session = Depends(get_db), tg_user: dict = Depends(get_telegram_user)):
    """Mini App ochilganda chaqiriladi: foydalanuvchini topadi yoki yaratadi."""
    user = get_or_create_user(db, tg_user)
    return UserOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        full_name=user.full_name,
        phone_number=user.phone_number,
        is_admin=is_admin_user(user.telegram_id),
    )
