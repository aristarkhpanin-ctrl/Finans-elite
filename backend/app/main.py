"""FastAPI-приложение вокруг расчётного ядра.

REST-бэкенд SaaS: расчёт и хранение проектов, аутентификация (JWT), мультиарендность
(организации/RBAC) и биллинг — роутеры ``auth``/``organizations``/``billing``/``projects``/
``holdings``/``integrator`` (ARCHITECTURE-SaaS.md). Расчётные эндпоинты — ниже в этом модуле.

Запуск: ``uvicorn app.main:app --reload``  (документация: ``/docs``).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from calc_core import ENGINE_VERSION, ProjectModel, run
from calc_core.engine import ModelError
from calc_core.samples import TEMPLATES, build_sample_project

from .database import get_db, init_db
from .observability import setup_observability
from .routers import (
    audit,
    auth,
    billing,
    holdings,
    integrator,
    jobs,
    organizations,
    projects,
)
from .schemas import CalcResponse, to_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # dev/test: создать таблицы (в продакшене — Alembic)
    yield


app = FastAPI(
    title="Финансовая модель — API",
    version=ENGINE_VERSION,
    description="Расчёт финансовой модели предприятия (отчёты, показатели, коэффициенты).",
    lifespan=lifespan,
)

# Логи с request-id + громкий сигнал о расхождении балансового инварианта.
setup_observability(app)

# CORS: по умолчанию выключен (фронт и API — на одном origin за nginx). При
# раздельном деплое задать CORS_ORIGINS (список через запятую). Токен передаётся
# в заголовке Authorization, не в cookie, поэтому credentials не нужны.
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(audit.router)
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(holdings.router)
app.include_router(integrator.router)
app.include_router(jobs.router)
app.include_router(organizations.router)
app.include_router(projects.router)


@app.get("/health", tags=["service"])
def health() -> dict:
    """Проверка живости и версия методики расчёта (liveness)."""
    return {"status": "ok", "engine_version": ENGINE_VERSION}


@app.get("/health/ready", tags=["service"])
def ready(db: Session = Depends(get_db)) -> dict:
    """Готовность к трафику (readiness): доступность БД. 503, если БД недоступна."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # любая ошибка соединения с БД = не готовы к трафику
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc
    return {"status": "ready"}


@app.post("/api/v1/calculate", response_model=CalcResponse, tags=["calc"])
def calculate(model: ProjectModel) -> CalcResponse:
    """Рассчитать проект: вернуть отчёты, показатели эффективности и коэффициенты."""
    try:
        result = run(model)
    except (ModelError, ValueError) as exc:
        # Некорректные входные данные (несходящийся стартовый баланс, ошибка актуализации).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_response(result)


@app.get("/api/v1/sample", response_model=ProjectModel, tags=["calc"])
def sample() -> ProjectModel:
    """Демонстрационная модель проекта (готова к отправке в /calculate)."""
    return build_sample_project()


class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str


@app.get("/api/v1/templates", response_model=list[TemplateInfo], tags=["calc"])
def templates() -> list[TemplateInfo]:
    """Список шаблонов проектов для быстрого старта (по типам бизнеса)."""
    return [TemplateInfo(id=k, name=v[0], description=v[1]) for k, v in TEMPLATES.items()]


@app.get("/api/v1/templates/{template_id}", response_model=ProjectModel, tags=["calc"])
def template(template_id: str) -> ProjectModel:
    """Готовая модель шаблона (для создания проекта на её основе)."""
    if template_id not in TEMPLATES:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return TEMPLATES[template_id][2]()
