from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from typing import AsyncIterator, Optional

from fastapi import FastAPI

from ffl.api.routes import router
from ffl.config import FFL_DATABASE_PATH
from ffl.persistence.schema import create_schema


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        app.state.conn.close()


def create_app(database_path: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="FFL Operating Kernel", lifespan=_lifespan)
    app.state.database_path = database_path or FFL_DATABASE_PATH
    Path(app.state.database_path).parent.mkdir(parents=True, exist_ok=True)
    app.state.conn = sqlite3.connect(app.state.database_path, check_same_thread=False)
    app.state.conn.row_factory = sqlite3.Row
    app.state.conn.execute("PRAGMA foreign_keys = ON")
    create_schema(app.state.conn)

    @app.get("/health")
    def health() -> dict:
        return {"service": "ffl-operating-kernel", "status": "ok"}

    app.include_router(router)
    return app


app = create_app()
