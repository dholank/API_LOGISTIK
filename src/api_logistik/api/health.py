from fastapi import APIRouter

from api_logistik.schemas.responses import HealthResponse, envelope

router = APIRouter()


@router.get("/health/live", tags=["health"], response_model=HealthResponse)
def live() -> dict[str, object]:
    return envelope(True, "SUCCESS", "Proses API berjalan", {"status": "alive"})
