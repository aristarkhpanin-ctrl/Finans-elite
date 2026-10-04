"""Казначейство вне потока проекта (0.9.56, пакет K, K3).

Размещение свободных денег в депозиты и ЦБ (``C8``) и доход по ним (``C9``) — решение о
деньгах, а не вложение в проект, как и автокредит (он в ``C27``). До 0.9.56 ``C8`` стояла
в операционном потоке ``C13``, из которого собран поток проекта, и каждое размещение
читалось как вложение: у флагмана демо-данных включённое «размещение излишков» уводило
NPV с +9,5 млн до −62,6 млн, а тело депозита на конец горизонта не возвращалось вовсе.

Отчёты не меняются: ``C8`` и ``C9`` по-прежнему в ``C13`` (касса та же), меняется только
поток для показателей. Налог с дохода по депозиту остаётся в ``C12`` — налоги в потоке
фактические, как и щит процентов по займам.
"""
from __future__ import annotations

from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Asset,
    AutoFinancing,
    Deposit,
    EquityInjection,
    Financing,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)

d = Decimal
N = 24
#: C8 и C9 сперва входят в C13, потом выходят из потока: в 30-м знаке остаётся шум
#: сложения больших чисел. Деньги сравниваются до тысячной копейки.
EPS = d("0.00001")


def _same(a: list[Decimal], b: list[Decimal]) -> bool:
    return len(a) == len(b) and all(abs(x - y) < EPS for x, y in zip(a, b, strict=True))


def _model(*, tax: str = "0", invest: bool = False,
           deposit: Deposit | None = None) -> ProjectModel:
    """Прибыльная торговля с оборудованием в первом месяце: вложение окупается, свободные
    деньги копятся."""
    return ProjectModel(
        header=ProjectHeader(name="Казначейство", duration_months=N),
        settings=ProjectSettings(profit_tax_rate=d(tax), discount_rate_annual=d("0.20")),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Оборудование", cost=d(600_000), purchase_month=0, life_months=60)]),
        operating_plan=OperatingPlan(
            products=[Product(id="p", name="Товар")],
            sales=[SalesLine(product_id="p", volume=[d(100)] * N, price=[d(1000)] * N)],
        ),
        financing=Financing(
            equity=[EquityInjection(month=0, amount=d(650_000))],
            deposits=[deposit] if deposit else [],
            auto_financing=AutoFinancing(enabled=invest, min_balance=d(20_000),
                                         invest_surplus=invest,
                                         invest_annual_rate=d("0.12")),
        ),
    )


def test_sweeping_the_surplus_into_a_deposit_is_not_an_investment():
    off, on = run(_model()), run(_model(invest=True))
    assert any(v != 0 for v in on.cashflow["C8"])        # размещение действительно идёт
    assert off.metrics.irr_annual is not None
    assert _same(on.project_flow, off.project_flow)
    assert abs(on.metrics.npv - off.metrics.npv) < EPS
    assert abs(on.metrics.irr_annual - off.metrics.irr_annual) < EPS


def test_a_manual_deposit_does_not_lower_npv():
    deposit = Deposit(name="Депозит", amount=d(30_000), start_month=2, term_months=6,
                      annual_rate=d("0.10"))
    plain, placed = run(_model()), run(_model(deposit=deposit))
    assert placed.cashflow["C8"][2] == d(30_000)
    assert _same(placed.project_flow, plain.project_flow)
    assert abs(placed.metrics.npv - plain.metrics.npv) < EPS


def test_the_tax_on_deposit_income_stays_in_the_flow():
    """Доход депозита в потоке нет, а налог с него — есть: налоги фактические. Разница
    потоков — ровно разница уплаченного налога."""
    off, on = run(_model(tax="0.25")), run(_model(tax="0.25", invest=True))
    for t in range(N):
        extra_tax = on.cashflow["C12"][t] - off.cashflow["C12"][t]
        assert abs(on.project_flow[t] - off.project_flow[t] + extra_tax) < EPS


def test_the_statements_keep_the_treasury_lines():
    """Касса не меняется: C8 и C9 по-прежнему в операционном потоке C13."""
    r = run(_model(invest=True))
    cf = r.cashflow
    for t in range(N):
        assert cf["C13"][t] == (cf["C1"][t] - cf["C4"][t] - cf["C7"][t] - cf["C8"][t]
                                + cf["C9"][t] + cf["C10"][t] - cf["C11"][t] - cf["C12"][t])
        assert r.project_flow[t] == cf["C13"][t] + cf["C8"][t] - cf["C9"][t] + cf["C20"][t]
