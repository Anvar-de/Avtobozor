from fastapi import APIRouter

from shared.car_brands import CAR_BRANDS
from shared.regions import REGIONS

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/regions")
def get_regions():
    """Hudud -> shahar/tuman ro'yxati (e'lon formasidagi dropdownlarni to'ldirish uchun)."""
    return REGIONS


@router.get("/car-brands")
def get_car_brands():
    """Avtomobil markalari ro'yxati (Marka maydonidagi live search uchun)."""
    return CAR_BRANDS
