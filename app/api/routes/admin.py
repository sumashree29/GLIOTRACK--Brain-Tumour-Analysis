"""
Admin routes — all endpoints require role=admin JWT.
Fix #7  — /health is now behind require_admin, not public.
Fix #10 — rate limiter applied.
"""
import time
from fastapi import APIRouter, Depends, Request
from app.core.auth import require_admin
from app.core.rate_limit import api_limiter, get_client_ip

router = APIRouter(prefix="/admin", tags=["admin"])
_start_time = time.time()


@router.get("/health")
def health(request: Request, admin=Depends(require_admin)):
    # FIX #7 — admin-only, not public
    api_limiter.check(get_client_ip(request))
    uptime_s = int(time.time() - _start_time)
    hours, rem = divmod(uptime_s, 3600)
    minutes, seconds = divmod(rem, 60)
    return {
        "status":          "ok",
        "service":         "brain-tumour-assessment",
        "version":         "1.0.0",
        "uptime":          f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        "uptime_seconds":  uptime_s,
    }
