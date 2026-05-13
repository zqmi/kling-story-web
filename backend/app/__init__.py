"""
kling-story 后端（在 backend 目录执行 uvicorn main:app）。

目录说明：
  app/main.py          FastAPI 应用、CORS、生命周期、挂载路由
  app/core/config.py   环境变量与默认配置
  app/core/database.py 异步引擎、Session、Base
  app/models/          SQLAlchemy 表
  app/schemas/         Pydantic 请求/响应
  app/services/        业务逻辑
  app/api/routes.py    HTTP 路由
"""
