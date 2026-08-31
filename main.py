"""Railpack entrypoint so Railway can start `uvicorn main:app` without extra config."""

from app.main import app

__all__ = ["app"]
