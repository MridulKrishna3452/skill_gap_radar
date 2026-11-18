from fastapi import APIRouter

from app.api.v1 import analytics, curriculum, health, ingestion, jobs, skills

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(skills.router)
api_router.include_router(curriculum.router)
api_router.include_router(analytics.router)
api_router.include_router(ingestion.router)
