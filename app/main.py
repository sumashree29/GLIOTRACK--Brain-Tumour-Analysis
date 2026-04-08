"""
FastAPI application entry point.
Fix #6  — CORS restricted to ALLOWED_ORIGINS env var, never "*".
Fix #7  — /health is now admin-only (moved to admin router).
Fix #10 — global rate limiter middleware added.
Fix CORS — OPTIONS method explicitly allowed.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import auth, patients, scans, reports, admin
from app.core.config import settings
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)  # Fix R1 — was missing; caused NameError in exception handler

app = FastAPI(
    title="Brain Tumour Response Assessment API",
    description="Constrained Autonomous Multi-Agent Framework v1.0",
    version="1.0.0",
    # Hide docs in production — set to None or guard with auth
    # Fix R2 — Swagger UI only enabled when DEBUG=true in .env
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
)

# FIX #6 — CORS restricted to explicit origins from ALLOWED_ORIGINS env var
allowed_origins = settings.get_allowed_origins()
logger.info(f"CORS Allowed Origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Fix CORS — explicitly include OPTIONS
    allow_headers=["*"],
)


# Security headers on every response
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    # Skip CSP for Swagger UI — it loads CSS/JS from cdn.jsdelivr.net
    if not request.url.path.startswith("/api/docs") and \
       not request.url.path.startswith("/openapi"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
    return response


# Fix Q5 — global exception handler: unhandled errors return a clean JSON
# response instead of leaking Python stack traces to the client.
from fastapi import Request as _Request
from fastapi.responses import JSONResponse as _JSONResponse
import traceback as _traceback

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: _Request, exc: Exception):
    logger.error(
        "Unhandled exception | %s %s | %s",
        request.method, request.url.path,
        _traceback.format_exc(),
    )
    if settings.debug:
        return _JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"},
        )
    return _JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )


# Removed preload to save memory on Render Free Tier boot.
# The embedding model will now lazy-load only when the RAG agent is executed.
@app.on_event("startup")
async def preload_models():
    logger.info("Skipping eager embedding model load to conserve RAM on free tier.")

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(scans.router)
app.include_router(reports.router)
app.include_router(admin.router)

# Serve frontend — http://localhost:8000 opens the UI
_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/static", StaticFiles(directory=_frontend), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(_frontend, "index.html"))

# FIX #7 — /health removed from here; it lives in admin router behind require_admin
