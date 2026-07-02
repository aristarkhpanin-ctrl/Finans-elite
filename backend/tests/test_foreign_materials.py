"""Валютное сырьё (SPEC §3, §22.3): импортный материал во 2-й валюте.

Конвенция (выведена и сверена вручную ниже):
- запас сырья B3 и себестоимость — по **курсу закупки** (немонетарный актив, историческая
  стоимость, без переоценки);
- кредиторка за материал — **монетарная**, переоценивается по FX[t] → курсовая разница I25
  (рост курса → убыток), оплата — по курсу периода оплаты;
- НДС на валютный материал в v0 не начисляется.
Баланс сходится во всех сценариях. При FX≡1 поведение тождественно рублёвому материалу.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    DirectCostLine,
    Environment,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)
from calc_core.models.common import DirectCostKind

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _model(material: DirectCostLine, fx_open: str, fx_rate, *, inflation_direct: str = "0",
           vat: str = "0"):
    """Один материал; без продаж/производства → себестоимость признаётся сразу.

    Пустой стартовый баланс (отрицательная касса допустима — это разрыв финансирования).
    """
    n = len(fx_rate)
    return ProjectModel(
        header=ProjectHeader(name="mat", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D(vat),
                                 inflation_direct=D(inflation_direct)),
        environment=Environment(fx_open=D(fx_open), fx_rate=[D(x) for x in fx_rate]),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(direct_costs=[material]),
    )


def test_foreign_material_import_vat():
    """Импортный НДС 20%: начисляется на таможенную стоимость, к вычету (B7), уплата на таможне.

    Закупка 100 валюты × курс 50 = 5000 таможенной стоимости → импортный НДС 1000.
    C2 = 5000 (поставщик) + 1000 (таможня) = 6000; НДС-кредит 1000 в B7; себестоимость 5000
    (НДС не входит в себестоимость).
    """
    mat = DirectCostLine(name="imp", kind=DirectCostKind.MATERIALS, foreign=True,
                         amount=[D(100), D(0)], stock_lead_months=0, payment_delay_months=0)
    r = run(_model(mat, "50", ["50", "50"], vat="0.20"))
    assert [quantize(v) for v in r.cashflow["C2"]] == [D("6000.00"), D("0.00")]
    assert [quantize(v) for v in r.balance["B7"]] == [D("1000.00"), D("1000.00")]
    assert [quantize(v) for v in r.income["I5"]] == [D("5000.00"), D("0.00")]
    assert _balanced(r)


def test_foreign_material_payable_revalued():
    """lead=0, оплата через 1 мес, курс 50→60: потребление 100 валюты в t0.

    Себестоимость по курсу закупки = 100·50 = 5000; кредиторка переоценивается
    (100·(60−50) = убыток 1000 в t1); оплата 100·60 = 6000 в t1.
    Итог: 5000 (материал) + 1000 (курс) = 6000 = фактический отток.
    """
    mat = DirectCostLine(name="imp", kind=DirectCostKind.MATERIALS, foreign=True,
                         amount=[D(100), D(0)], stock_lead_months=0, payment_delay_months=1)
    r = run(_model(mat, "50", ["50", "60"]))
    assert [quantize(v) for v in r.income["I5"]] == [D("5000.00"), D("0.00")]
    assert [quantize(v) for v in r.income["I25"]] == [D("0.00"), D("-1000.00")]
    assert [quantize(v) for v in r.cashflow["C2"]] == [D("0.00"), D("6000.00")]
    assert [quantize(v) for v in r.balance["B23"]] == [D("5000.00"), D("0.00")]
    assert [quantize(v) for v in r.balance["B3"]] == [D("0.00"), D("0.00")]
    assert _balanced(r)


def test_foreign_material_stock_at_historical_rate():
    """lead=1, оплата сразу, курс 50→60: закупка/оплата в t0, потребление в t1.

    Сырьё лежит в B3 по курсу закупки 50 (немонетарный актив, не переоценивается):
    B3[0]=5000; курсовой разницы нет (кредиторки нет); себестоимость в t1 = 5000.
    """
    mat = DirectCostLine(name="imp", kind=DirectCostKind.MATERIALS, foreign=True,
                         amount=[D(0), D(100)], stock_lead_months=1, payment_delay_months=0)
    r = run(_model(mat, "50", ["50", "60"]))
    assert [quantize(v) for v in r.balance["B3"]] == [D("5000.00"), D("0.00")]
    assert [quantize(v) for v in r.income["I5"]] == [D("0.00"), D("5000.00")]
    assert [quantize(v) for v in r.income["I25"]] == [D("0.00"), D("0.00")]
    assert [quantize(v) for v in r.cashflow["C2"]] == [D("5000.00"), D("0.00")]
    assert _balanced(r)


def test_foreign_material_equivalent_to_domestic_at_unit_rate():
    """FX≡1 и без инфляции: валютный материал тождествен рублёвому (без НДС)."""
    amount = [D(100), D(200), D(150)]
    common = dict(kind=DirectCostKind.MATERIALS, amount=amount,
                  stock_lead_months=1, payment_delay_months=1)
    rf = run(_model(DirectCostLine(name="imp", foreign=True, **common), "1", ["1", "1", "1"]))
    rd = run(_model(DirectCostLine(name="dom", foreign=False, **common), "1", ["1", "1", "1"]))
    for code in ("I5", "I25"):
        assert [quantize(v) for v in rf.income[code]] == [quantize(v) for v in rd.income[code]]
    for code in ("B3", "B23", "B1"):
        assert [quantize(v) for v in rf.balance[code]] == [quantize(v) for v in rd.balance[code]]
    assert [quantize(v) for v in rf.cashflow["C2"]] == [quantize(v) for v in rd.cashflow["C2"]]
    assert _balanced(rf) and _balanced(rd)
