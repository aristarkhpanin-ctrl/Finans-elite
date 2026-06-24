"""FastAPI-приложение вокруг расчётного ядра (этап 5.3).

Первый вертикальный срез бэкенда: расчёт проекта по REST. Аутентификация,
мультиарендность и биллинг (ARCHITECTURE-SaaS.md) — следующие этапы.

Запуск: ``uvicorn app.main:app --reload``  (документация: ``/docs``).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from calc_core import ENGINE_VERSION, ProjectModel, run
from calc_core.engine import ModelError
from calc_core.samples import TEMPLATES, build_sample_project

from .database import init_db
from .routers import auth, billing, holdings, integrator, organizations, projects
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

app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(holdings.router)
app.include_router(integrator.router)
app.include_router(organizations.router)
app.include_router(projects.router)


@app.get("/health", tags=["service"])
def health() -> dict:
    """Проверка живости и версия методики расчёта."""
    return {"status": "ok", "engine_version": ENGINE_VERSION}


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
