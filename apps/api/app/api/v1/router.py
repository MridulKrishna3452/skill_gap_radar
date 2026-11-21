from fastapi import APIRouter, Depends

from app.api.deps import public_rate_limit
from app.api.v1 import admin, analytics, auth, curriculum, health, ingestion, jobs, me, skills

api_router = APIRouter()
# Health checks are polled by orchestrators and are not rate-limited.
api_router.include_router(health.router)
# Every other route counts against the per-IP public limit (RATE_LIMIT_PUBLIC). Auth and
# expensive routes add their own, tighter limits. Who may call what: docs/security.md.
_limited = [Depends(public_rate_limit)]
for module in (auth, me, admin, jobs, skills, curriculum, analytics, ingestion):
    api_router.include_router(module.router, dependencies=_limited)
