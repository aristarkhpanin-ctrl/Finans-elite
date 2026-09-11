"""Тесты нормирования процентов по ставке ЦБ (SPEC §11/§22.6, gap 2.2).

Вычитаемы проценты в пределах ставка_ЦБ × коэффициент → I18; сверхнорматив → I24.
Норматив выключен (cb=0) → текущее поведение. Сумма процентов (C24) не меняется.
"""
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Financing,
    Loan,
    OperatingPlan,
    Product,
    ProjectModel,
    SalesLine,
)
from calc_core.money import almost_equal


def _model(loan_rate="0.30", cb="0", mult="1", on_profit=False, foreign=False, n=12) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.settings.cb_refinancing_rate = Decimal(cb)
    model.settings.interest_norm_multiple = Decimal(mult)
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(20)] * n, price=[Decimal(1000)] * n)],
    )
    model.financing = Financing(loans=[Loan(
        name="Заём", amount=Decimal(500_000), start_month=0, term_months=n,
        annual_rate=Decimal(loan_rate), interest_on_profit=on_profit, foreign=foreign)])
    return model


def test_norm_disabled_matches_current_behaviour():
    """cb=0 → весь процент вычитаем (I18), I24 от процентов = 0 (как раньше)."""
    r = run(_model(cb="0"))
    assert sum(r.income["I18"], Decimal(0)) > 0
    # I24 не содержит процентов (только прочие невычитаемые, которых тут нет)
    assert sum(r.income["I24"], Decimal(0)) == 0


def test_excess_over_norm_goes_to_profit():
    """Ставка займа 30%, норма 20% → 1/3 процента сверхнорматив (I24), 2/3 вычитаемо (I18)."""
    disabled = run(_model(loan_rate="0.30", cb="0"))
    normed = run(_model(loan_rate="0.30", cb="0.20", mult="1"))
    # сумма процентов (касса C24) не изменилась — меняется только распределение I18/I24
    assert normed.cashflow["C24"] == disabled.cashflow["C24"]
    i18 = sum(normed.income["I18"], Decimal(0))
    i24 = sum(normed.income["I24"], Decimal(0))
    total = i18 + i24
    assert total > 0
    # доля вычитаемого = min(1, norm_m/loan_m); проверяем, что сверхнорматив положителен
    assert i24 > 0 and i18 > 0
    # налоговая база уменьшилась только на вычитаемую часть → I18 меньше полного процента
    assert almost_equal(total, sum(disabled.income["I18"], Decimal(0)))


def test_norm_above_loan_rate_all_deductible():
    """Норма (25%×2=50%) выше ставки займа (30%) → весь процент вычитаем, I24=0."""
    r = run(_model(loan_rate="0.30", cb="0.25", mult="2"))
    assert sum(r.income["I24"], Decimal(0)) == 0
    assert sum(r.income["I18"], Decimal(0)) > 0


def test_multiple_scales_norm():
    """Коэффициент множит норму: 10%×1 даёт больше сверхнорматива, чем 10%×2."""
    tight = run(_model(loan_rate="0.30", cb="0.10", mult="1"))
    loose = run(_model(loan_rate="0.30", cb="0.10", mult="2"))
    assert sum(tight.income["I24"], Decimal(0)) > sum(loose.income["I24"], Decimal(0))


def test_interest_on_profit_ignores_norm():
    """Заём «на прибыль»: весь процент в I24 независимо от норматива."""
    r = run(_model(loan_rate="0.30", cb="0.20", on_profit=True))
    assert sum(r.income["I18"], Decimal(0)) == 0             # ничего не вычитается
    assert sum(r.income["I24"], Decimal(0)) > 0


def test_invariant_holds_with_norm():
    r = run(_model(loan_rate="0.35", cb="0.15", mult="1"))
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_foreign_loan_norm_split():
    """Валютный заём: норматив применяется в валюте займа, инвариант держится."""
    model = _model(loan_rate="0.10", cb="0.05", foreign=True)
    model.environment.fx_open = Decimal("90")
    model.environment.fx_rate = [Decimal(90) + Decimal(t) for t in range(model.n)]
    r = run(model)
    assert sum(r.income["I24"], Decimal(0)) > 0             # сверхнорматив есть
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
