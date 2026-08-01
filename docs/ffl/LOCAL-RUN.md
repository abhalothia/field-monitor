# Run the FFL operating kernel locally

From the repository root, create the FFL runtime environment and start the
API:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn ffl.app:app --reload
```

For FFL development and tests, install the development extras instead:

```bash
pip install -r requirements-dev.txt
pytest tests/ffl -v
```

`requirements.txt` intentionally contains only the FFL deployment runtime.
The satellite/dashboard prototype is archived; install
`requirements-legacy.txt` explicitly only when working on that prototype.

Open the [field reporting surface](http://127.0.0.1:8000/field), the
[manager action centre](http://127.0.0.1:8000/manager), or the interactive
[API documentation](http://127.0.0.1:8000/docs).

By default, the runtime writes SQLite data to `data/ffl.db`. Set
`FFL_DATABASE_PATH` to override that location.
