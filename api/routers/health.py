"""Health-check router — the simplest possible endpoint, always implement first."""

# pyrefly: ignore [missing-import]
from fastapi import APIRouter
# pyrefly: ignore [missing-import]
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Liveness probe. Returns 200 when the API process is running.
    Kubernetes / Docker health-checks hit this endpoint.
    """
    return HealthResponse(status="ok", version="0.1.0")
