"""Налог на прибыль: перенос убытков и льготы (SPEC §11, §22.7).

Перенос убытков: убыток периода накапливается и уменьшает налоговую базу будущих
прибыльных периодов (I22). Льгота: доля налогооблагаемой прибыли освобождается от налога.
Числа выведены вручную.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    CostFunction,
    Financing,
    FixedCostLine,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _model(volume, admin_cost, *, n, benefit=D("0")) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="tax", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=D("0"), profit_tax_rate=D("0.20"),
            property_tax_rate=D("0"), vat_rate=D("0"),
            profit_tax_benefit_share=benefit,
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=volume, price=[D(100)] * n)],
            fixed_costs=[FixedCostLine(
                name="Администрация", function=CostFunction.ADMIN, amount=admin_cost,
            )],
        ),
        financing=Financing(common_shares=D(100)),
    )


def test_loss_carryforward_reduces_later_tax():
    """t0 убыток 500, t1 прибыль 2000: убыток уменьшает базу t1 (налог 300 вместо 400)."""
    r = run(_model(volume=[D(0), D(20)], admin_cost=[D(500), D(0)], n=2))
    assert r.income["I23"] == [D(-500), D(2000)]
    assert r.income["I22"] == [D(0), D(500)]      # перенесённый убыток применён в t1
    assert r.income["I26"] == [D(-500), D(1500)]  # база t1 уменьшена на 500
    assert r.income["I27"] == [D(0), D(300)]      # налог 20% от 1500 (а не от 2000)
    assert r.income["I28"] == [D(-500), D(1700)]
    assert _balanced(r)


def test_loss_carryforward_consumed_across_multiple_periods():
    """Убыток 1000 (t0) гасится прибылью t1 (600) и частично t2 (400 из 600)."""
    r = run(_model(volume=[D(0), D(6), D(6)], admin_cost=[D(1000), D(0), D(0)], n=3))
    assert r.income["I23"] == [D(-1000), D(600), D(600)]
    assert r.income["I22"] == [D(0), D(600), D(400)]   # пул 1000 → 600 + 400
    assert r.income["I26"] == [D(-1000), D(0), D(200)]
    assert r.income["I27"] == [D(0), D(0), D(40)]      # налог только с остатка 200
    assert _balanced(r)


def test_no_carryforward_when_profit_only():
    """Без убытков перенос не срабатывает — поведение прежнее (backward-compatible)."""
    r = run(_model(volume=[D(10), D(10)], admin_cost=[D(0), D(0)], n=2))
    assert r.income["I22"] == [D(0), D(0)]
    assert r.income["I27"] == [D(200), D(200)]   # 20% от 1000 каждый период
    assert _balanced(r)


def test_profit_tax_benefit_exempts_share_of_base():
    """Льгота 50%: освобождает половину базы — налог 100 вместо 200; чистая прибыль 900."""
    r = run(_model(volume=[D(10)], admin_cost=[D(0)], n=1, benefit=D("0.5")))
    assert r.income["I23"] == [D(1000)]
    assert r.income["I26"] == [D(500)]   # половина базы освобождена
    assert r.income["I27"] == [D(100)]   # налог 20% от 500
    assert r.income["I28"] == [D(900)]
    assert _balanced(r)
