"""
Main FastAPI application entry point.

Design note: We create the app in a factory function (create_app) rather than
at module level. This makes it easy to override settings in tests without
importing the app and having side effects fire.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import applications, health, reviews
from core.config import settings
from core.database import engine
from core.logging import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    configure_logging()
    logger.info("startup", env=settings.APP_ENV, version="0.1.0")
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Credit Union Loan Onboarding API",
        description=(
            "AI-assisted member onboarding and loan origination pipeline. "
            "ALL DATA IS SYNTHETIC — no real PII is used."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["Health"])
    app.include_router(applications.router, prefix="/applications", tags=["Applications"])
    app.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])

    return app


app = create_app()
