"""
入口：在 backend 目录执行
  uvicorn main:app --reload --port 8000
  docker compose up -d

分层代码在 app/ 包内，见 app/__init__.py。
"""

from app.main import app

__all__ = ["app"]
