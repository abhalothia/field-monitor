from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ffl.api.import_routes import router as import_router
from ffl.api.portfolio_routes import router as portfolio_router
from ffl.api.routes import router
from ffl.api.season_routes import router as season_router
from ffl.api.source_routes import router as source_router
from ffl.api.trial_routes import router as trial_router
from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.persistence import create_communications_schema
from ffl.communications.auth import configured_manager_person_id, configured_manager_token
from ffl.config import FFL_DATABASE_PATH
from ffl.persistence.schema import create_schema


STATIC_DIR = Path(__file__).resolve().parent / "static"
FIELD_INDEX = STATIC_DIR / "field" / "index.html"
MANAGER_INDEX = STATIC_DIR / "manager" / "index.html"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        app.state.conn.close()


def create_app(database_path: Optional[str] = None, communication_provider=None, manager_api_token=None, manager_person_id=None) -> FastAPI:
    app = FastAPI(title="FFL Operating Kernel", lifespan=_lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.database_path = database_path or FFL_DATABASE_PATH
    Path(app.state.database_path).parent.mkdir(parents=True, exist_ok=True)
    app.state.conn = sqlite3.connect(app.state.database_path, check_same_thread=False)
    app.state.conn.row_factory = sqlite3.Row
    app.state.conn.execute("PRAGMA foreign_keys = ON")
    create_schema(app.state.conn)
    create_communications_schema(app.state.conn)
    app.state.communication_provider = communication_provider or LoopMessageProvider.from_environment()
    app.state.manager_api_token = manager_api_token if manager_api_token is not None else configured_manager_token()
    app.state.manager_person_id = manager_person_id if manager_person_id is not None else configured_manager_person_id()

    @app.get("/health")
    def health() -> dict:
        return {"service": "ffl-operating-kernel", "status": "ok"}

    @app.get("/field", include_in_schema=False)
    def field_surface() -> FileResponse:
        return FileResponse(FIELD_INDEX)

    @app.get("/manager", include_in_schema=False)
    def manager_surface() -> FileResponse:
        return FileResponse(MANAGER_INDEX)

    app.include_router(router)
    app.include_router(season_router)
    app.include_router(import_router)
    app.include_router(trial_router)
    app.include_router(source_router)
    app.include_router(portfolio_router)
    return app


app = create_app()
