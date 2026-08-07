from contextlib import asynccontextmanager
from pathlib import Path
import os
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from ffl.api.import_routes import router as import_router
from ffl.api.farm_manifest_routes import router as farm_manifest_router
from ffl.api.farm_profile_routes import router as farm_profile_router
from ffl.api.farm_truth_routes import router as farm_truth_router
from ffl.api.farm_candidate_review_routes import router as farm_candidate_review_router
from ffl.api.agent_routes import router as agent_router
from ffl.api.field_information_request_routes import router as field_information_request_router
from ffl.api.field_capture_routes import router as field_capture_router
from ffl.api.context_routes import router as context_router
from ffl.api.data_lanes_routes import router as data_lanes_router
from ffl.api.launch_routes import router as launch_router
from ffl.api.manager_session_routes import router as manager_session_router
from ffl.api.portfolio_routes import router as portfolio_router
from ffl.api.operating_profile_routes import router as operating_profile_router
from ffl.api.procurement_history_routes import router as procurement_history_router
from ffl.api.relationship_routes import router as relationship_router
from ffl.api.routes import router
from ffl.api.season_routes import router as season_router
from ffl.api.source_routes import router as source_router
from ffl.api.trial_routes import router as trial_router
from ffl.api.trackolap_routes import router as trackolap_router
from ffl.api.trackwick_routes import router as trackwick_router
from ffl.api.portal_routes import router as portal_router
from ffl.api.password_identity_routes import router as password_identity_router
from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.persistence import create_communications_schema
from ffl.communications.auth import configured_manager_person_id, configured_manager_token
from ffl.manager_session_auth import configured_manager_session_max_age_seconds, configured_manager_session_secret
from ffl.portal import customer_portal_for_hostname, hostname_from_host_header, normalise_hostname, portal_host_is_under_base
from ffl.portal_auth import (
    SupabasePhoneOtpProvider,
    configured_portal_session_max_age_seconds,
    configured_portal_session_secret,
)
from ffl.pilot_setup_auth import configured_pilot_setup_approval_token
from ffl.services.evidence_store import evidence_store_from_environment
from ffl.services.operating_profile import normalize_operating_profile, operating_profile_from_environment
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
PORTAL_INDEX = STATIC_DIR / "portal" / "index.html"
LAUNCH_INDEX = STATIC_DIR / "launch" / "index.html"
BRAND_DIR = STATIC_DIR / "brand"
MANIFEST = BRAND_DIR / "site.webmanifest"
SOCIAL_CARD = BRAND_DIR / "agro-ceo-social.png"
APPLE_TOUCH_ICON = BRAND_DIR / "apple-touch-icon.png"
FAVICON_PNG = BRAND_DIR / "favicon.png"
WEB_ASSETS = {
    "public.css": STATIC_DIR / "landing" / "styles.css",
    "launch.css": STATIC_DIR / "launch" / "styles.css",
    "launch.js": STATIC_DIR / "launch" / "app.js",
    "manager.css": STATIC_DIR / "manager" / "styles.css",
    "manager.js": STATIC_DIR / "manager" / "app.js",
    "portal.css": STATIC_DIR / "portal" / "styles.css",
    "portal.js": STATIC_DIR / "portal" / "app.js",
    "first-field-manifest.csv": STATIC_DIR / "manager" / "first-field-manifest.csv",
    "field.css": STATIC_DIR / "field" / "styles.css",
    "field.js": STATIC_DIR / "field" / "app.js",
    "field-ledger-paddies.png": STATIC_DIR / "art" / "field-ledger-paddies.png",
    "rice-paper.png": STATIC_DIR / "art" / "rice-paper.png",
    "rice-sheaf-icon.png": STATIC_DIR / "art" / "rice-sheaf-icon.png",
}
FIELD_SERVICE_WORKER = STATIC_DIR / "field" / "sw.js"
VERCEL_ANALYTICS_SNIPPET = '''    <script>
      window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
    </script>
    <script defer src="/_vercel/insights/script.js"></script>'''


def _public_origin() -> str:
    """Return the deliberately configured canonical origin for share previews.

    The host is configuration, never an untrusted request header. This prevents
    hostile Host headers from changing the URLs that social crawlers cache.
    """

    configured = os.environ.get("FFL_PUBLIC_ORIGIN", "https://www.agroceo.co").rstrip("/")
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

    social_image = f"{origin}/brand/agro-ceo-social.png"
    return f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#173b2c">
    <title>AGRO CEO — Fortune Farms</title>
    <meta name="description" content="Know what changed. Know who owns the next move.">
    <link rel="canonical" href="{origin}/">
    <link rel="icon" href="/favicon.png" type="image/png">
    <link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">
    <link rel="manifest" href="/site.webmanifest">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Fortune Farms">
    <meta property="og:title" content="AGRO CEO — Fortune Farms">
    <meta property="og:description" content="Know what changed. Know who owns the next move.">
    <meta property="og:url" content="{origin}/">
    <meta property="og:image" content="{social_image}">
    <meta property="og:image:secure_url" content="{social_image}">
    <meta property="og:image:type" content="image/png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="AGRO CEO — Fortune Farms">
    <meta name="twitter:description" content="Know what changed. Know who owns the next move.">
    <meta name="twitter:image" content="{social_image}">
    <link rel="stylesheet" href="/assets/public.css">
{VERCEL_ANALYTICS_SNIPPET}
  </head>
  <body>
    <main class="shell">
      <p class="wordmark"><img src="/assets/rice-sheaf-icon.png" alt=""> Fortune Farms</p>
      <section class="landing-hero">
        <div class="landing-copy">
          <h1>AGRO CEO</h1>
          <p class="statement">Know what changed. Know who owns the next move.</p>
          <a href="/login">Open AGRO CEO <span aria-hidden="true">→</span></a>
        </div>
        <figure class="landing-field">
          <img src="/assets/field-ledger-paddies.png" alt="Aerial rice paddy fields with irrigation channels">
          <figcaption>Evidence begins in the field.</figcaption>
        </figure>
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


def create_app(database_path: Optional[str] = None, communication_provider=None, manager_api_token=None, manager_person_id=None, communication_receipt_key=None, launch_password=None, pilot_setup_approval_token=None, evidence_store=None, operating_profile=None, private_communications_worker_attested: Optional[bool] = None, manager_session_secret=None, manager_session_max_age_seconds: Optional[int] = None, field_capture_signing_key: Optional[str] = None, portal_auth_provider=None, portal_session_secret=None, portal_session_max_age_seconds: Optional[int] = None, portal_base_domain: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="FFL Operating Kernel", lifespan=_lifespan)
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
    app.state.manager_session_secret = (
        manager_session_secret if manager_session_secret is not None else configured_manager_session_secret()
    )
    app.state.manager_session_max_age_seconds = (
        manager_session_max_age_seconds
        if manager_session_max_age_seconds is not None
        else configured_manager_session_max_age_seconds()
    )
    app.state.portal_auth_provider = portal_auth_provider or SupabasePhoneOtpProvider.from_environment()
    app.state.portal_session_secret = (
        portal_session_secret if portal_session_secret is not None else configured_portal_session_secret()
    )
    app.state.portal_session_max_age_seconds = (
        portal_session_max_age_seconds
        if portal_session_max_age_seconds is not None
        else configured_portal_session_max_age_seconds()
    )
    try:
        app.state.portal_base_domain = normalise_hostname(
            portal_base_domain if portal_base_domain is not None else os.environ.get("FFL_PORTAL_BASE_DOMAIN", "agroceo.com")
        )
    except ValueError as error:
        raise RuntimeError("FFL_PORTAL_BASE_DOMAIN must be a lower-case hostname") from error
    app.state.communication_receipt_key = communication_receipt_key if communication_receipt_key is not None else os.environ.get("FFL_COMMUNICATION_RECEIPT_KEY")
    # A browser, webhook, or Vercel preview can never attest a private recovery
    # worker.  Production composition may set this trusted fact only on the
    # dedicated private worker-hosted deployment after the runbook is complete.
    app.state.private_communications_worker_attested = (
        bool(private_communications_worker_attested)
        if private_communications_worker_attested is not None
        else (
            not bool(os.environ.get("VERCEL"))
            and os.environ.get("FFL_PRIVATE_COMMUNICATIONS_WORKER_ATTESTED") == "true"
        )
    )
    app.state.launch_password = launch_password if launch_password is not None else configured_launch_password()
    # Password identities use the same server-derived cookie authority as the
    # SessionMiddleware, but have a separate purpose/version/binding.  The
    # browser never receives this value or a role/person id it can choose.
    app.state.password_identity_session_key = session_secret(
        app.state.launch_password or "ffl-local-development-only",
        app.state.manager_session_secret,
        app.state.portal_session_secret,
    )
    app.state.pilot_setup_approval_token = (
        pilot_setup_approval_token
        if pilot_setup_approval_token is not None
        else configured_pilot_setup_approval_token()
    )
    app.state.evidence_store = evidence_store if evidence_store is not None else evidence_store_from_environment()
    # This is a separate server-only identity authority for native field
    # capture passes.  It is never a browser-managed person id and is not a
    # LoopMessage/Hermes credential or fallback.
    app.state.field_capture_signing_key = (
        field_capture_signing_key
        if field_capture_signing_key is not None
        else os.environ.get("FFL_FIELD_CAPTURE_SIGNING_KEY")
    )
    app.state.operating_profile = (
        normalize_operating_profile(operating_profile)
        if operating_profile is not None
        else operating_profile_from_environment()
    )

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
        portal_hostname = hostname_from_host_header(request.headers.get("host"))
        portal_host = portal_host_is_under_base(portal_hostname, app.state.portal_base_domain)
        webhook = path == "/api/v1/communications/loopmessage/webhook" and request.method == "POST"
        public_paths = {
            "/",
            "/health",
            "/login",
            "/favicon.svg",
            "/favicon.png",
            "/favicon.ico",
            "/site.webmanifest",
            "/api/v1/launch/login",
            "/api/v1/launch/logout",
            "/api/v1/trackwick/cron-refresh",
            "/api/v1/identity/login",
            "/api/v1/identity/logout",
            "/api/v1/identity/session",
            "/api/v1/identity/password",
            "/api/v1/my/overview",
        }
        portal_public_paths = {
            "/", "/portal", "/login",
            "/api/v1/portal/bootstrap", "/api/v1/portal/session",
            "/api/v1/portal/auth/request-code", "/api/v1/portal/auth/verify-code",
            "/api/v1/portal/auth/logout",
        }
        if portal_host:
            # Customer subdomains are phone-first.  The shared pilot password
            # is never a fallback login there; every protected request still
            # passes its own membership/manager check after this shell gate.
            if path.startswith("/api/v1/launch/"):
                return JSONResponse({"detail": "customer portal sign-in is required"}, status_code=404)
            if path in portal_public_paths or path.startswith("/assets/") or path.startswith("/brand/") or path in {
                "/favicon.svg", "/favicon.png", "/favicon.ico", "/site.webmanifest",
            }:
                return await call_next(request)
            if request.session.get(SESSION_FLAG) is True:
                return await call_next(request)
            if path.startswith("/api/"):
                return JSONResponse({"detail": "phone sign-in is required"}, status_code=401)
            return RedirectResponse(url="/", status_code=303)
        if not password:
            # A local disposable preview may intentionally omit access setup.
            # A Vercel URL must never turn that omission into an open operating
            # surface: leave only the data-free share shell and static branding
            # available until its encrypted launch secret is configured.
            if os.environ.get("VERCEL") and not (
                path in public_paths or path.startswith("/assets/") or path.startswith("/brand/")
                or path.startswith("/_vercel/insights/") or path == "/field-service-worker.js"
            ):
                return JSONResponse(
                    {"detail": "Fortune pilot access is not configured"},
                    status_code=503,
                )
            return await call_next(request)
        if (
            path in public_paths or path.startswith("/assets/") or path.startswith("/brand/")
            or path.startswith("/_vercel/insights/") or path == "/field-service-worker.js" or webhook
        ):
            return await call_next(request)
        if request.session.get(SESSION_FLAG) is True:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "launch login is required"}, status_code=401)
        return RedirectResponse(url="/login?next=" + (path if path in {"/manager", "/field"} else "/manager"), status_code=303)

    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(
            app.state.launch_password or "ffl-local-development-only", app.state.manager_session_secret,
            app.state.portal_session_secret,
        ),
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        # A hosted Vercel production/preview URL is HTTPS; a manager session
        # must never silently downgrade to a non-Secure cookie there.
        https_only=os.environ.get("FFL_LAUNCH_COOKIE_SECURE") == "true" or bool(os.environ.get("VERCEL")),
    )

    @app.get("/health")
    def health() -> dict:
        return {"service": "ffl-operating-kernel", "status": "ok"}

    @app.get("/", include_in_schema=False)
    def public_landing(request: Request):
        hostname = hostname_from_host_header(request.headers.get("host"))
        if portal_host_is_under_base(hostname, app.state.portal_base_domain) and customer_portal_for_hostname(
            getattr(request.state, "conn", app.state.conn), hostname,
        ) is not None:
            return FileResponse(PORTAL_INDEX)
        return HTMLResponse(_public_landing(_public_origin()))

    @app.get("/favicon.png", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(FAVICON_PNG, media_type="image/png")

    @app.get("/favicon.svg", include_in_schema=False)
    def legacy_svg_favicon() -> RedirectResponse:
        return RedirectResponse("/favicon.png", status_code=307)

    @app.get("/favicon.ico", include_in_schema=False)
    def legacy_favicon() -> RedirectResponse:
        # Keep legacy crawlers and browser probes on the single canonical mark.
        return RedirectResponse("/favicon.png", status_code=307)

    @app.get("/site.webmanifest", include_in_schema=False)
    def web_manifest() -> FileResponse:
        return FileResponse(MANIFEST, media_type="application/manifest+json")

    @app.get("/brand/agro-ceo-social.png", include_in_schema=False)
    def social_card() -> FileResponse:
        return FileResponse(SOCIAL_CARD, media_type="image/png")

    @app.get("/brand/apple-touch-icon.png", include_in_schema=False)
    def apple_touch_icon() -> FileResponse:
        return FileResponse(APPLE_TOUCH_ICON, media_type="image/png")

    @app.get("/assets/{asset_name}", include_in_schema=False)
    def web_asset(asset_name: str) -> FileResponse:
        """Serve only the explicitly approved browser assets through the app.

        Vercel reserves ``/static`` for its own file handling.  Routing the
        small allowlist here keeps the same FastAPI app responsible for assets
        in preview and production, without exposing a filesystem reader.
        """

        asset_path = WEB_ASSETS.get(asset_name)
        if asset_path is None:
            raise HTTPException(status_code=404, detail="asset not found")
        media_type = (
            "text/css" if asset_name.endswith(".css") else
            "application/javascript" if asset_name.endswith(".js") else
            "text/csv; charset=utf-8" if asset_name.endswith(".csv") else
            "image/png"
        )
        return FileResponse(asset_path, media_type=media_type)

    @app.get("/field-service-worker.js", include_in_schema=False)
    def field_service_worker() -> FileResponse:
        return FileResponse(
            FIELD_SERVICE_WORKER,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/field", include_in_schema=False)
    def field_surface() -> FileResponse:
        return FileResponse(FIELD_INDEX)

    @app.get("/login", include_in_schema=False)
    def launch_login(request: Request) -> FileResponse:
        hostname = hostname_from_host_header(request.headers.get("host"))
        if portal_host_is_under_base(hostname, app.state.portal_base_domain) and customer_portal_for_hostname(
            getattr(request.state, "conn", app.state.conn), hostname,
        ) is not None:
            return FileResponse(PORTAL_INDEX)
        return FileResponse(LAUNCH_INDEX)

    @app.get("/portal", include_in_schema=False)
    def customer_portal_surface(request: Request) -> FileResponse:
        hostname = hostname_from_host_header(request.headers.get("host"))
        if not portal_host_is_under_base(hostname, app.state.portal_base_domain) or customer_portal_for_hostname(
            getattr(request.state, "conn", app.state.conn), hostname,
        ) is None:
            raise HTTPException(status_code=404, detail="customer portal was not found")
        return FileResponse(PORTAL_INDEX)

    @app.get("/manager", include_in_schema=False)
    def manager_surface() -> FileResponse:
        return FileResponse(MANAGER_INDEX)

    app.include_router(router)
    app.include_router(launch_router)
    app.include_router(manager_session_router)
    app.include_router(season_router)
    app.include_router(import_router)
    app.include_router(farm_manifest_router)
    app.include_router(field_information_request_router)
    app.include_router(field_capture_router)
    app.include_router(procurement_history_router)
    app.include_router(relationship_router)
    app.include_router(context_router)
    app.include_router(data_lanes_router)
    app.include_router(trial_router)
    app.include_router(source_router)
    app.include_router(portfolio_router)
    app.include_router(operating_profile_router)
    app.include_router(trackolap_router)
    app.include_router(trackwick_router)
    app.include_router(farm_truth_router)
    app.include_router(farm_candidate_review_router)
    app.include_router(agent_router)
    app.include_router(farm_profile_router)
    app.include_router(portal_router)
    app.include_router(password_identity_router)
    return app


app = create_app()
