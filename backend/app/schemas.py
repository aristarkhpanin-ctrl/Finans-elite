"""Pydantic-схемы ответа API и преобразование из ``CalcResult``.

Decimal сериализуется в JSON как строка (точность сохраняется), ``None`` → ``null``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from calc_core import ProjectModel
from calc_core.reports.result import CalcResult
from calc_core.reports.statements import Statement


class LineOut(BaseModel):
    code: str
    label: str
    values: list[Decimal]


class StatementOut(BaseModel):
    lines: list[LineOut]


class MetricsOut(BaseModel):
    npv: Decimal
    irr_annual: Optional[Decimal] = None
    pi: Optional[Decimal] = None
    pb_months: Optional[int] = None
    dpb_months: Optional[int] = None


class RatiosOut(BaseModel):
    liquidity: dict[str, list[Optional[Decimal]]]
    activity: dict[str, list[Optional[Decimal]]]
    gearing: dict[str, list[Optional[Decimal]]]
    profitability: dict[str, list[Optional[Decimal]]]
    investment: dict[str, list[Optional[Decimal]]]


class BreakEvenOut(BaseModel):
    break_even_revenue: list[Optional[Decimal]]
    margin_of_safety: list[Optional[Decimal]]


class CalcResponse(BaseModel):
    engine_version: str
    n: int
    income: StatementOut
    cashflow: StatementOut
    balance: StatementOut
    profit_use: StatementOut
    metrics: MetricsOut
    ratios: RatiosOut
    break_even: BreakEvenOut
    warnings: list[str]


# --- Проекты (персистентность, 6.1) ---

class ProjectCreate(BaseModel):
    name: str
    model: ProjectModel


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[ProjectModel] = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectOut(ProjectSummary):
    model: ProjectModel


# --- Организации, пользователи, членство (мультиарендность, 6.2) ---

class OrganizationCreate(BaseModel):
    name: str


class OrganizationOut(BaseModel):
    id: str
    name: str
    created_at: datetime


class OrganizationMembershipOut(BaseModel):
    id: str
    name: str
    role: str
    created_at: datetime


class MemberCreate(BaseModel):
    email: str
    full_name: str = ""
    role: str = "viewer"


class MemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str


# --- Аутентификация (6.3) ---

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    organization_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str


# --- Тарифы и подписка (биллинг, 6.5) ---

class PlanOut(BaseModel):
    code: str
    name: str
    price_rub: int
    max_projects: Optional[int] = None
    max_members: Optional[int] = None


class SubscriptionOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    current_period_end: Optional[datetime] = None
    max_projects: Optional[int] = None
    max_members: Optional[int] = None
    used_projects: int
    used_members: int


class SubscriptionUpdate(BaseModel):
    plan_code: str


class CheckoutRequest(BaseModel):
    plan_code: str
    return_url: str = "https://example.com/billing/return"


class CheckoutResponse(BaseModel):
    activated: bool
    payment_id: Optional[str] = None
    confirmation_url: Optional[str] = None


# --- Анализ чувствительности (7.3) ---

class SensitivityRequest(BaseModel):
    param: str
    factors: list[Decimal] = [Decimal("0.8"), Decimal("0.9"), Decimal("1.0"),
                              Decimal("1.1"), Decimal("1.2")]


class SensitivityPointOut(BaseModel):
    factor: Decimal
    npv: Decimal
    irr_annual: Optional[Decimal] = None


class SensitivityResponse(BaseModel):
    param: str
    points: list[SensitivityPointOut]


def _statement_out(s: Statement) -> StatementOut:
    return StatementOut(
        lines=[LineOut(code=code, label=s.labels[code], values=s[code]) for code in s.order]
    )


def to_response(r: CalcResult) -> CalcResponse:
    """Преобразовать результат ядра в схему ответа API."""
    return CalcResponse(
        engine_version=r.engine_version,
        n=r.n,
        income=_statement_out(r.income),
        cashflow=_statement_out(r.cashflow),
        balance=_statement_out(r.balance),
        profit_use=_statement_out(r.profit_use),
        metrics=MetricsOut(
            npv=r.metrics.npv,
            irr_annual=r.metrics.irr_annual,
            pi=r.metrics.pi,
            pb_months=r.metrics.pb_months,
            dpb_months=r.metrics.dpb_months,
        ),
        ratios=RatiosOut(
            liquidity=r.ratios.liquidity,
            activity=r.ratios.activity,
            gearing=r.ratios.gearing,
            profitability=r.ratios.profitability,
            investment=r.ratios.investment,
        ),
        break_even=BreakEvenOut(
            break_even_revenue=r.break_even.break_even_revenue,
            margin_of_safety=r.break_even.margin_of_safety,
        ),
        warnings=r.warnings,
    )
