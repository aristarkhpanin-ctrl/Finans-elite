"""Переоценка ОС (SPEC §9): дооценка → остаточная стоимость и добавочный капитал B31."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Asset,
    EquityInjection,
    Financing,
    InvestmentPlan,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def test_revaluation_lifts_residual_and_additional_capital():
    """Станок 1000 (10 мес → 100/мес), дооценка +500 в t1: B31 = 500, остаточная растёт."""
    n = 3
    m = ProjectModel(
        header=ProjectHeader(name="reval", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        investment_plan=InvestmentPlan(assets=[Asset(
            name="Станок", cost=D(1000), purchase_month=0, life_months=10,
            revaluation_month=1, revaluation_amount=D(500))]),
        financing=Financing(equity=[EquityInjection(amount=D(1000), month=0)], common_shares=D(100)),
        operating_plan=OperatingPlan(),
    )
    r = run(m)
    assert r.balance["B31"] == [D(0), D(500), D(500)]      # добавочный капитал = дооценка
    # остаточная: t0 1000−100=900; t1 +500 дооценка −200 аморт = 1300; t2 −300 = 1200
    assert r.balance["B14"] == [D(900), D(1300), D(1200)]
    assert _balanced(r)
