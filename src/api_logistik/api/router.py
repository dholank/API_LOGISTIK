from fastapi import APIRouter

from api_logistik.api.health import router as health_router
from api_logistik.api.karyawan import router as karyawan_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(karyawan_router)
