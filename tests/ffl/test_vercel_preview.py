import importlib

import ffl.config as config
from api.index import app as vercel_app
from ffl.app import app as ffl_app


def test_vercel_entrypoint_exports_the_existing_ffl_app():
    assert vercel_app is ffl_app


def test_vercel_uses_ephemeral_database_unless_explicitly_overridden(monkeypatch):
    with monkeypatch.context() as environment:
        environment.delenv("FFL_DATABASE_PATH", raising=False)
        environment.delenv("VERCEL", raising=False)
        reloaded_config = importlib.reload(config)
        assert reloaded_config.FFL_DATABASE_PATH == str(
            reloaded_config.PROJECT_ROOT / "data" / "ffl.db"
        )

        environment.setenv("VERCEL", "1")
        assert importlib.reload(config).FFL_DATABASE_PATH == "/tmp/ffl.db"

        environment.setenv("FFL_DATABASE_PATH", "/tmp/explicit-ffl.db")
        assert importlib.reload(config).FFL_DATABASE_PATH == "/tmp/explicit-ffl.db"

    importlib.reload(config)
