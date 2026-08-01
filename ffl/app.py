from contextlib import asynccontextmanager
from pathlib import Path
import os
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ffl.api.import_routes import router as import_router
from ffl.api.launch_routes import router as launch_router
from ffl.api.portfolio_routes import router as portfolio_router
from ffl.api.routes import router
from ffl.api.season_routes import router as season_router
from ffl.api.source_routes import router as source_router
from ffl.api.trial_routes import router as trial_router
from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.persistence import create_communications_schema
from ffl.communications.auth import configured_manager_person_id, configured_manager_token
from ffl.config import FFL_DATABASE_PATH
from ffl.launch_auth import (
    SESSION_FLAG,
    SESSION_MAX_AGE_SECONDS,
    configured_launch_password,
    session_secret,
)
from ffl.persistence.database import database_target, open_connection
from ffl.persistence.schema import create_schema


STATIC_DIR = Path(__file__).resolve().parent / "static"
FIELD_INDEX = STATIC_DIR / "field" / "index.html"
MANAGER_INDEX = STATIC_DIR / "manager" / "index.html"
LAUNCH_INDEX = STATIC_DIR / "launch" / "index.html"
BRAND_DIR = STATIC_DIR / "brand"
FAVICON_SVG = BRAND_DIR / "favicon.svg"
MANIFEST = BRAND_DIR / "site.webmanifest"


def _public_origin() -> str:
    """Return the deliberately configured canonical origin for share previews.

    The host is configuration, never an untrusted request header. This prevents
    hostile Host headers from changing the URLs that social crawlers cache.
    """

    configured = os.environ.get("FFL_PUBLIC_ORIGIN", "https://agroceo.co").rstrip("/")
    parsed = urlparse(configured)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError("FFL_PUBLIC_ORIGIN must be an absolute origin without a path")
    return configured


def _public_landing(origin: str) -> str:
    """A deliberately public, data-free link-preview surface for the pilot."""

    social_image = f"{origin}/static/brand/agro-ceo-social.png"
    return f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#101716">
    <title>AGRO CEO — Fortune Farms</title>
    <meta name="description" content="The private operating system for real-time farm steering.">
    <link rel="canonical" href="{origin}/">
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/brand/apple-touch-icon.png">
    <link rel="manifest" href="/site.webmanifest">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Fortune Farms">
    <meta property="og:title" content="AGRO CEO — Fortune Farms">
    <meta property="og:description" content="The private operating system for real-time farm steering.">
    <meta property="og:url" content="{origin}/">
    <meta property="og:image" content="{social_image}">
    <meta property="og:image:secure_url" content="{social_image}">
    <meta property="og:image:type" content="image/png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="AGRO CEO — Fortune Farms">
    <meta name="twitter:description" content="The private operating system for real-time farm steering.">
    <meta name="twitter:image" content="{social_image}">
    <link rel="stylesheet" href="/static/public/styles.css">
  </head>
  <body>
    <main class="shell">
      <p class="wordmark"><span aria-hidden="true">F</span> Fortune Farms</p>
      <section>
        <p class="eyebrow">Private operating system</p>
        <h1>AGRO CEO</h1>
        <p class="statement">Real-time farm steering, held to real evidence.</p>
        <a href="/login">Enter pilot <span aria-hidden="true">→</span></a>
      </section>
    </main>
  </body>
</html>'''


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        app.state.conn.close()


def create_app(database_path: Optional[str] = None, communication_provider=None, manager_api_token=None, manager_person_id=None, communication_receipt_key=None, launch_password=None) -> FastAPI:
    app = FastAPI(title="FFL Operating Kernel", lifespan=_lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.database_path = database_path or FFL_DATABASE_PATH
    app.state.database_target = database_target(sqlite_path=app.state.database_path)
    if app.state.database_target.dialect == "sqlite" and app.state.database_target.sqlite_path != ":memory:":
        Path(app.state.database_target.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    app.state.conn = open_connection(app.state.database_target, check_same_thread=False)
    if app.state.database_target.dialect == "sqlite":
        create_schema(app.state.conn)
        create_communications_schema(app.state.conn)
    app.state.communication_provider = communication_provider or LoopMessageProvider.from_environment()
    app.state.manager_api_token = manager_api_token if manager_api_token is not None else configured_manager_token()
    app.state.manager_person_id = manager_person_id if manager_person_id is not None else configured_manager_person_id()
    app.state.communication_receipt_key = communication_receipt_key if communication_receipt_key is not None else os.environ.get("FFL_COMMUNICATION_RECEIPT_KEY")
    app.state.launch_password = launch_password if launch_password is not None else configured_launch_password()

    @app.middleware("http")
    async def private_postgres_request_connection(request: Request, call_next):
        """Never share one PostgreSQL transaction between concurrent requests."""
        if app.state.database_target.dialect != "postgres":
            return await call_next(request)
        connection = open_connection(app.state.database_target, check_same_thread=False)
        request.state.conn = connection
        try:
            return await call_next(request)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @app.middleware("http")
    async def launch_access_gate(request: Request, call_next):
        password = app.state.launch_password
        path = request.url.path
        webhook = path == "/api/v1/communications/loopmessage/webhook" and request.method == "POST"
        public_paths = {
            "/",
            "/health",
            "/login",
            "/favicon.svg",
            "/favicon.ico",
            "/site.webmanifest",
            "/api/v1/launch/login",
            "/api/v1/launch/logout",
        }
        if not password:
            # A local disposable preview may intentionally omit access setup.
            # A Vercel URL must never turn that omission into an open operating
            # surface: leave only the data-free share shell and static branding
            # available until its encrypted launch secret is configured.
            if os.environ.get("VERCEL") and not (path in public_paths or path.startswith("/static/")):
                return JSONResponse(
                    {"detail": "Fortune pilot access is not configured"},
                    status_code=503,
                )
            return await call_next(request)
        if path in public_paths or path.startswith("/static/") or webhook:
            return await call_next(request)
        if request.session.get(SESSION_FLAG) is True:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "launch login is required"}, status_code=401)
        return RedirectResponse(url="/login?next=" + (path if path in {"/manager", "/field"} else "/manager"), status_code=303)

    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(app.state.launch_password or "ffl-local-development-only"),
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=os.environ.get("FFL_LAUNCH_COOKIE_SECURE") == "true",
    )

    @app.get("/health")
    def health() -> dict:
        return {"service": "ffl-operating-kernel", "status": "ok"}

    @app.get("/", include_in_schema=False)
    def public_landing() -> HTMLResponse:
        return HTMLResponse(_public_landing(_public_origin()))

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(FAVICON_SVG, media_type="image/svg+xml")

    @app.get("/favicon.ico", include_in_schema=False)
    def legacy_favicon() -> RedirectResponse:
        # Keep legacy crawlers and browser probes on the single canonical mark.
        return RedirectResponse("/favicon.svg", status_code=307)

    @app.get("/site.webmanifest", include_in_schema=False)
    def web_manifest() -> FileResponse:
        return FileResponse(MANIFEST, media_type="application/manifest+json")

    @app.get("/field", include_in_schema=False)
    def field_surface() -> FileResponse:
        return FileResponse(FIELD_INDEX)

    @app.get("/login", include_in_schema=False)
    def launch_login() -> FileResponse:
        return FileResponse(LAUNCH_INDEX)

    @app.get("/manager", include_in_schema=False)
    def manager_surface() -> FileResponse:
        return FileResponse(MANAGER_INDEX)

    app.include_router(router)
    app.include_router(launch_router)
    app.include_router(season_router)
    app.include_router(import_router)
    app.include_router(trial_router)
    app.include_router(source_router)
    app.include_router(portfolio_router)
    return app


app = create_app()
