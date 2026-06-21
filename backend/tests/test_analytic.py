"""Аналитические (ручные) проверки ядра на замкнутых примерах.

В отличие от golden-master (снимок «как считает ядро сейчас»), здесь ожидаемые числа
выведены **вручную** из условий задачи. Это прямая проверка методики: если ядро и
ручной расчёт расходятся — виновато ядро. Примеры намеренно тривиальны (нет НДС, налогов,
отсрочек), чтобы каждую цифру можно было перепроверить на бумаге.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Asset,
    Company,
    Financing,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)

D = Decimal


def build_simple_cash() -> ProjectModel:
    """3 месяца, продажа 10 ед × 100 ₽/мес, оплата сразу, без НДС/налогов/издержек.

    Ожидаемо: выручка 1000 ₽/мес, она же чистая прибыль и денежный поток; деньги и
    нераспределённая прибыль растут 1000 → 2000 → 3000.
    """
    n = 3
    return ProjectModel(
        header=ProjectHeader(
            name="Аналитический: чистый кэш",
            start_date=date(2026, 1, 1),
            duration_months=n,
        ),
        settings=ProjectSettings(
            discount_rate_annual=D("0"),
            profit_tax_rate=D("0"),
            property_tax_rate=D("0"),
            vat_rate=D("0"),
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)],
        ),
        financing=Financing(common_shares=D(100)),
    )


def test_simple_cash_income_statement():
    r = run(build_simple_cash())
    assert r.income["I1"] == [D(1000), D(1000), D(1000)]   # валовый объём продаж
    assert r.income["I4"] == [D(1000), D(1000), D(1000)]   # чистый объём (нет потерь/налогов с продаж)
    assert r.income["I7"] == [D(0), D(0), D(0)]            # нет прямых издержек
    assert r.income["I8"] == [D(1000), D(1000), D(1000)]   # валовая прибыль
    assert r.income["I27"] == [D(0), D(0), D(0)]           # налог на прибыль выключен
    assert r.income["I28"] == [D(1000), D(1000), D(1000)]  # чистая прибыль


def test_simple_cash_cashflow():
    r = run(build_simple_cash())
    assert r.cashflow["C1"] == [D(1000), D(1000), D(1000)]    # поступления (без НДС)
    assert r.cashflow["C13"] == [D(1000), D(1000), D(1000)]   # операционный поток
    assert r.cashflow["C29"] == [D(1000), D(2000), D(3000)]   # сальдо нарастающим итогом


def test_simple_cash_balance_holds_and_grows():
    r = run(build_simple_cash())
    assert r.balance["B1"] == [D(1000), D(2000), D(3000)]     # деньги
    assert r.balance["B32"] == [D(1000), D(2000), D(3000)]    # нераспределённая прибыль
    # Главный инвариант: актив = пассив в каждом периоде.
    assert r.balance["B20"] == r.balance["B34"]
    assert r.balance["B20"] == [D(1000), D(2000), D(3000)]


def test_simple_cash_profit_use():
    r = run(build_simple_cash())
    assert r.profit_use["P1"] == [D(1000), D(1000), D(1000)]  # = I28
    assert r.profit_use["P7"] == [D(1000), D(2000), D(3000)]  # накопленная нераспределённая


def test_simple_cash_metrics():
    r = run(build_simple_cash())
    m = r.metrics
    # Ставка 0 → NPV = сумма потоков = 3 × 1000.
    assert m.npv == D(3000)
    # Поток весь положительный: окупаемость в 1-м периоде, IRR/PI не определены.
    assert m.pb_months == 1
    assert m.dpb_months == 1
    assert m.irr_annual is None
    assert m.pi is None
    # Капитал не требовался → потребность в финансировании нулевая.
    assert m.pv_investments == D(0)
    assert m.peak_financing_need == D(0)


def build_upfront_capex() -> ProjectModel:
    """3 месяца; станок 1500 ₽ (срок 3 мес) куплен в t0; продажи 1000 ₽/мес сразу.

    Поток до финансирования: t0 = 1000 − 1500 = −500, далее +1000, +1000.
    Накопленно: −500 → +500 → +1500. Капитал нужен только в t0 = 500 (пик финансирования).
    """
    n = 3
    return ProjectModel(
        header=ProjectHeader(
            name="Аналитический: капвложение в t0",
            start_date=date(2026, 1, 1),
            duration_months=n,
        ),
        settings=ProjectSettings(
            discount_rate_annual=D("0"),
            profit_tax_rate=D("0"),
            property_tax_rate=D("0"),
            vat_rate=D("0"),
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)],
        ),
        investment_plan=InvestmentPlan(
            assets=[Asset(name="Станок", cost=D(1500), purchase_month=0, life_months=3)],
        ),
        financing=Financing(common_shares=D(100)),
    )


def test_upfront_capex_cashflow_and_balance():
    r = run(build_upfront_capex())
    assert r.cashflow["C13"] == [D(1000), D(1000), D(1000)]   # амортизация — не деньги
    assert r.cashflow["C20"] == [D(-1500), D(0), D(0)]        # капвложение в t0
    assert r.cashflow["C29"] == [D(-500), D(500), D(1500)]    # сальдо (дефицит в t0)
    # Балансовый инвариант держится даже при отрицательных деньгах.
    assert r.balance["B20"] == r.balance["B34"]


def test_upfront_capex_metrics():
    m = run(build_upfront_capex()).metrics
    # Ставка 0: NPV = −500 + 1000 + 1000 = 1500.
    assert m.npv == D(1500)
    # Капитал нужен только в t0 = 500 → PV(инв) = 500, пик финансирования = 500.
    assert m.pv_investments == D(500)
    assert m.peak_financing_need == D(500)
    # PI = 1 + 1500/500 = 4.
    assert m.pi == D(4)
    # Окупаемость во 2-м периоде; IRR определена (поток меняет знак).
    assert m.pb_months == 2
    assert m.irr_annual is not None
