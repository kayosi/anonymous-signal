"""Main API router — aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints.reports import router as reports_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
