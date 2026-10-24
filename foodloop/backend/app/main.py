"""FoodLoop API entry point.

Run in development:  uvicorn app.main:app --reload   (from the backend folder)
Interactive API docs: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, listings, meta, provider, public, reservations
from app.config import get_settings
from app.db import SessionLocal
from app.errors import install_error_handlers
from app.services.samples import start_sample_refresher

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# A strict Content Security Policy for the website pages: only our own scripts, styles, images and fonts.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    stop = None
    if settings.app_env == "development" and settings.sample_auto_refresh:
        stop = start_sample_refresher(SessionLocal)
    yield
    if stop:
        stop.set()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="FoodLoop API",
        version="0.1.0",
        description="Good food. Less waste. Surplus meals from approved kitchens, reserved and collected safely.",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def block_cross_site_writes(request: Request, call_next):
        """CSRF protection. Browsers always send an Origin header on POST/PUT/DELETE. If it names a
        website we don't trust, refuse, even though the login cookie came along with the request."""
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin != "null":
                same_host = urlsplit(origin).netloc == request.headers.get("host")
                if not same_host and origin.rstrip("/") not in settings.allowed_origins:
                    return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked."})
            elif origin == "null":
                return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked."})
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif not request.url.path.startswith("/docs"):
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        return response

    for module in (meta, auth, listings, public, reservations, provider, admin):
        app.include_router(module.router)

    settings.media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    if settings.frontend_dist:
        _serve_frontend(app, Path(settings.frontend_dist))
    return app


def _serve_frontend(app: FastAPI, dist: Path) -> None:
    """Production: serve the built React app from the same domain (no CORS, cookies just work)."""
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"FRONTEND_DIST is set but {index} does not exist. Run `npm run build` first.")
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found."})
        candidate = (dist / path).resolve()
        if path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)  # React Router handles the URL in the browser


app = create_app()
