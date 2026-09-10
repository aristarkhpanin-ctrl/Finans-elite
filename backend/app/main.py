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
from sqlalchemy import text
from sqlalchemy.orm import Session

from calc_core import ENGINE_VERSION, ProjectModel, run
from calc_core.engine import ModelError
from calc_core.samples import TEMPLATES, build_sample_project
from calc_core.templates import INDUSTRY_TEMPLATES, NOT_A_BENCHMARK

from .database import get_db, init_db
from .observability import setup_observability
from .routers import (
    admin,
    apikeys,
    audit,
    auth,
    billing,
    comments,
    holdings,
    integrator,
    jobs,
    organizations,
    projects,
)
from .schemas import CalcResponse, TemplateOut, to_response


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

app.include_router(admin.router)
app.include_router(apikeys.router)
app.include_router(audit.router)
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(comments.router)
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


#: Каталог шаблонов: демонстрационные (были с первых версий) и отраслевые (D4).
#: Ключи не пересекаются — проверяется тестом: совпавший ключ молча спрятал бы один
#: шаблон за другим.
def _catalog() -> dict[str, TemplateOut]:
    out = {
        k: TemplateOut(id=k, name=v[0], description=v[1], industry="Демонстрация",
                       shows="Базовый разбор: как устроена модель целиком.",
                       assumptions=[NOT_A_BENCHMARK])
        for k, v in TEMPLATES.items()
    }
    out.update({
        t.id: TemplateOut(id=t.id, name=t.name, industry=t.industry,
                          description=t.description, shows=t.shows,
                          assumptions=list(t.assumptions))
        for t in INDUSTRY_TEMPLATES.values()
    })
    return out


@app.get("/api/v1/templates", response_model=list[TemplateOut], tags=["calc"])
def templates() -> list[TemplateOut]:
    """Шаблоны быстрого старта: демонстрационные и отраслевые (D4).

    Каждый несёт **список допущений**: числа в шаблоне выдуманы автором и годятся ровно
    на то, чтобы модель считалась. Базы отраслевых данных у платформы нет, и выдать
    пример за статистику значило бы соврать самым дорогим способом — цифрой.
    """
    return list(_catalog().values())


@app.get("/api/v1/templates/{template_id}", response_model=ProjectModel, tags=["calc"])
def template(template_id: str) -> ProjectModel:
    """Готовая модель шаблона (для создания проекта на её основе)."""
    if template_id in INDUSTRY_TEMPLATES:
        return INDUSTRY_TEMPLATES[template_id].build()
    if template_id not in TEMPLATES:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return TEMPLATES[template_id][2]()
