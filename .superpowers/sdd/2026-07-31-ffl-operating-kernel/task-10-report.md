# Task 10: Slim FFL Vercel preview dependencies

## Problem

The Vercel preview build failed with `LAMBDA_SIZE_EXCEEDED` at 517.07 MB.
The root dependency file installed the archived satellite/dashboard stack,
including large numerical and visualization packages, even though the FFL
runtime only requires FastAPI, Uvicorn, and HTTPX.

## Change

- Reduced `requirements.txt` to the three FFL runtime dependencies.
- Added `requirements-legacy.txt` for explicit archived prototype installs.
- Added `requirements-dev.txt` for FFL runtime plus test tooling.
- Documented FFL runtime, development, and archived prototype install paths.
- Added dependency-boundary assertions under `tests/ffl`.

## Verification

- `pytest tests/ffl/test_requirements.py -v`
- `pytest tests/ffl -v`

## Commit

`fix: slim FFL Vercel preview dependencies`
