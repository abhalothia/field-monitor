"""Expose the existing FFL ASGI app to Vercel."""

from ffl.app import app

__all__ = ["app"]
