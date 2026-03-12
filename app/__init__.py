# app/__init__.py
from app.webhook_server import create_app

__all__ = ["create_app"]