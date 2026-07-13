from fastapi import APIRouter, Request

from shared.car_brands import CAR_BRANDS
from shared.regions import REGIONS
from ..rate_limit import limiter

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/regions")
@limiter.limit("30/minute")
def get_regions(request: Request):
    """Hudud -> shahar/tuman ro'yxati (e'lon formasidagi dropdownlarni to'ldirish uchun)."""
    return REGIONS


@router.get("/car-brands")
@limiter.limit("30/minute")
def get_car_brands(request: Request):
    """Avtomobil markalari ro'yxati (Marka maydonidagi live search uchun)."""
    return CAR_BRANDS
