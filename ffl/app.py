from typing import Optional

from fastapi import FastAPI

from ffl.config import FFL_DATABASE_PATH


def create_app(database_path: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="FFL Operating Kernel")
    app.state.database_path = database_path or FFL_DATABASE_PATH

    @app.get("/health")
    def health() -> dict:
        return {"service": "ffl-operating-kernel", "status": "ok"}

    return app


app = create_app()
