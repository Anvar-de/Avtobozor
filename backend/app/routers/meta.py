from fastapi import APIRouter

from shared.regions import REGIONS

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/regions")
def get_regions():
    """Hudud -> shahar/tuman ro'yxati (e'lon formasidagi dropdownlarni to'ldirish uchun)."""
    return REGIONS
