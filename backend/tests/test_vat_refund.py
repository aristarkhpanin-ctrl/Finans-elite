"""Возмещение излишка входного НДС (0.9.55, пакет K, K2).

Излишек вычетов над начисленным налогом по итогам квартала — налогового периода НДС
(ст. 163 НК РФ) — возмещается (п. 1 ст. 176) после камеральной проверки: деньги приходят
через ``vat_refund_lag_months`` после квартала. До 0.9.55 излишек только переносился в
зачёт будущих периодов — у проекта с крупной закупкой оборудования входной НДС лежал в
B7 полтора года вместо четырёх месяцев. Прежнее поведение — режим «в зачёт».

Сальдо — **за период уплаты**, а не помесячно: при квартальной уплате помесячный зачёт
платил налог первого месяца квартала и копил излишек третьего.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.vat import settle_vat
from calc_core.models import (
    Asset,
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
from calc_core.money import quantize

d = Decimal


# --- Сальдо по периоду и заявление к возмещению: сама функция ---

def test_the_balance_is_struck_for_the_period_not_month_by_month():
    """Налог первого месяца и излишек третьего в одном квартале гасят друг друга: по
    декларации к уплате ноль, излишек 50. Помесячный зачёт заплатил бы 100."""
    s = settle_vat([d(100), d(0), d(0)], [d(0), d(0), d(150)], 3, period_months=3)
    assert s.to_budget == [d(100), d(0), d(-100)]       # приросты позиции квартала
    assert sum(s.to_budget, d(0)) == d(0)
    assert s.credit == [d(0), d(0), d(50)]               # перенесён в зачёт


def test_the_quarter_excess_is_claimed_and_refunded_after_the_lag():
    s = settle_vat([d(100), d(0), d(0), d(0), d(0), d(0)],
                   [d(0), d(0), d(150), d(0), d(0), d(0)], 6,
                   period_months=3, refund_lag=2)
    assert s.credit == [d(0)] * 6                        # заявлено — уже не зачёт
    assert s.receivable == [d(0), d(0), d(50), d(50), d(0), d(0)]
    assert s.refund == [d(0), d(0), d(0), d(0), d(50), d(0)]


def test_a_monthly_excess_offsets_the_rest_of_its_quarter_first():
    """«Ежемесячно» — упрощение уплаты, а не период декларации: январский излишек гасит
    налог февраля и марта, к возмещению уходит только остаток на конец квартала."""
    s = settle_vat([d(0), d(10), d(10), d(0)], [d(30), d(0), d(0), d(0)], 4,
                   period_months=1, refund_lag=1)
    assert s.to_budget == [d(0)] * 4
    assert s.credit == [d(30), d(20), d(0), d(0)]
    assert s.receivable == [d(0), d(0), d(10), d(0)]
    assert s.refund == [d(0), d(0), d(0), d(10)]


def test_the_quarter_ends_by_the_calendar_not_by_the_start():
    """Старт в феврале: первый квартал неполный и кончается в марте (второй месяц)."""
    s = settle_vat([d(0), d(0), d(0)], [d(30), d(0), d(0)], 3,
                   period_months=1, offset=1, refund_lag=1)
    assert s.receivable == [d(0), d(30), d(0)]
    assert s.refund == [d(0), d(0), d(30)]


def test_without_a_refund_the_excess_carries_as_before():
    s = settle_vat([d(0), d(10), d(10), d(100)], [d(30), d(0), d(0), d(0)], 4)
    assert s.to_budget == [d(0), d(0), d(0), d(90)]
    assert s.credit == [d(30), d(20), d(10), d(0)]
    assert s.refund == [d(0)] * 4 and s.receivable == [d(0)] * 4


# --- Расчёт целиком ---

def _model(n: int = 12, **settings) -> ProjectModel:
    """Оборудование 1 млн в январе (входной НДС 220 000), продажи 100 000 в месяц с
    февраля (исходящий 22 000). Излишек на конец I квартала: 220 000 − 2 × 22 000."""
    return ProjectModel(
        header=ProjectHeader(name="Возмещение", start_date=date(2026, 1, 1),
                             duration_months=n),
        settings=ProjectSettings(vat_rate=d("0.22"), profit_tax_rate=d(0),
                                 property_tax_rate=d(0), **settings),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Линия", cost=d(1_000_000), purchase_month=0, life_months=120)]),
        operating_plan=OperatingPlan(
            products=[Product(id="p", name="Изделие")],
            sales=[SalesLine(product_id="p", volume=[d(0)] + [d(100)] * (n - 1),
                             price=[d(1000)] * n)],
        ),
        financing=Financing(equity=[EquityInjection(month=0, amount=d(1_300_000))]),
    )


def _c12(r, name: str) -> list[Decimal]:
    """Слагаемое C12; нулевые слагаемые (и пустая C12) детализацией не сохраняются."""
    detail = next((x for x in r.details if x.code == "C12"), None)
    item = next((i for i in detail.items if i.name == name), None) if detail else None
    return [quantize(v) for v in item.values] if item else [d(0)] * r.n


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def test_the_excess_left_at_the_quarter_end_comes_back_four_months_later():
    r = run(_model())
    refund = _c12(r, "Возмещение НДС")
    assert refund[6] == d(-176_000)                       # июль: 4 мес. после марта
    assert sum(refund, d(0)) == d(-176_000)
    b7 = [quantize(v) for v in r.balance["B7"]]
    assert b7[:7] == [d(220_000), d(198_000), d(176_000), d(176_000), d(176_000),
                      d(176_000), d(0)]
    # С апреля излишка нет — налог апреля уплачен в мае, как обычно.
    assert _c12(r, "НДС к уплате")[3:5] == [d(0), d(22_000)]
    assert _balanced(r)


def test_carrying_the_excess_forward_is_the_previous_behaviour():
    r = run(_model(vat_refund=False))
    assert _c12(r, "Возмещение НДС") == [d(0)] * 12
    b7 = [quantize(v) for v in r.balance["B7"]]
    assert b7[:4] == [d(220_000), d(198_000), d(176_000), d(154_000)]
    # Зачёт гасит налог февраля–ноября (220 000 / 22 000 = 10 месяцев продаж); налог
    # декабря уплачивается в январе — за горизонтом, поэтому НДС в кассе нет вовсе.
    assert _c12(r, "НДС к уплате") == [d(0)] * 12
    assert quantize(r.balance["B21"][-1]) == d(22_000)
    assert _balanced(r)


def test_the_lag_is_the_models_assumption():
    r = run(_model(vat_refund_lag_months=2))
    assert _c12(r, "Возмещение НДС")[4] == d(-176_000)    # май


def test_a_refund_due_after_the_horizon_stays_receivable():
    r = run(_model(n=5))
    assert _c12(r, "Возмещение НДС") == [d(0)] * 5
    assert quantize(r.balance["B7"][-1]) == d(176_000)
    assert _balanced(r)


def test_the_refund_moves_money_forward_and_raises_npv():
    """Тот же входной НДС, возвращённый в июле, а не гасящий налог десять месяцев, —
    деньги раньше: NPV выше."""
    assert run(_model()).metrics.npv > run(_model(vat_refund=False)).metrics.npv
