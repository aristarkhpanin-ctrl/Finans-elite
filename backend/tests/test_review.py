"""Тесты ревью бизнес-плана (R0 каркас, R1 viability)."""
from decimal import Decimal

from calc_core import run
from calc_core.models.operating import (
    DirectCostLine,
    FixedCostLine,
    Product,
    SalesLine,
)
from calc_core.reports.lines import (
    BALANCE_LINES,
    CASHFLOW_LINES,
    INCOME_LINES,
    PROFIT_USE_LINES,
)
from calc_core.reports.result import CalcResult, InvestmentMetrics
from calc_core.reports.statements import Statement
from calc_core.review import ReviewContext, run_review
from calc_core.review.aggregates import (
    gross_margin,
    per_product_revenue,
    total_net_revenue,
)
from calc_core.review.config import DEFAULT_CONFIG
from calc_core.review.rules import liquidity, structure
from calc_core.samples import build_sample_project


def _result(n=12, npv="1", irr="0.30", pi="1.5", pb=1, cashflow=None) -> CalcResult:
    return CalcResult(
        engine_version="t", n=n,
        income=Statement(INCOME_LINES, n),
        cashflow=cashflow if cashflow is not None else Statement(CASHFLOW_LINES, n),
        balance=Statement(BALANCE_LINES, n),
        profit_use=Statement(PROFIT_USE_LINES, n),
        metrics=InvestmentMetrics(
            npv=Decimal(npv),
            irr_annual=Decimal(irr) if irr is not None else None,
            pi=Decimal(pi) if pi is not None else None,
            pb_months=pb,
        ),
    )


def _ctx(**kw) -> ReviewContext:
    model = build_sample_project()
    model.settings.discount_rate_annual = Decimal("0.15")
    return ReviewContext(model=model, result=_result(**kw))


def _ids(ctx) -> set[str]:
    return {f.id for f in run_review(ctx).findings}


def test_review_result_structure():
    model = build_sample_project()
    review = run_review(ReviewContext(model=model, result=run(model)))
    assert review.light in {"ok", "info", "warning", "risk"}
    assert sum(review.counts.values()) == len(review.findings)
    order = {"risk": 0, "warning": 1, "info": 2}
    sev = [order[f.severity] for f in review.findings]
    assert sev == sorted(sev)                          # находки отсортированы risk→warning→info


def test_aggregates_on_sample():
    model = build_sample_project()
    result = run(model)
    assert total_net_revenue(result) > 0              # у демо есть продажи
    gm = gross_margin(result)
    assert gm is not None and -1 <= gm <= 1           # доля в разумных границах
    rev_by_product = per_product_revenue(model)
    assert rev_by_product and all(v >= 0 for v in rev_by_product.values())


# --- R1: viability ---

def test_npv_negative_fires_and_severity():
    review = run_review(_ctx(npv="-500000"))
    assert "viability.npv_negative" in {f.id for f in review.findings}
    assert review.light == "risk"
    assert "viability.npv_negative" not in _ids(_ctx(npv="500000"))


def test_irr_below_hurdle_warning_and_risk():
    ids = _ids(_ctx(npv="100000", irr="0.05"))
    assert "viability.irr_below_hurdle" in ids
    review = run_review(_ctx(npv="-1", irr="0.05"))
    sev = {f.id: f.severity for f in review.findings}
    assert sev["viability.irr_below_hurdle"] == "risk"
    assert "viability.irr_below_hurdle" not in _ids(_ctx(irr="0.30"))


def test_irr_undefined_info():
    assert "viability.irr_undefined" in _ids(_ctx(irr=None))
    assert "viability.irr_undefined" not in _ids(_ctx(irr="0.30"))


def test_pi_below_one():
    assert "viability.pi_below_one" in _ids(_ctx(pi="0.80"))
    assert "viability.pi_below_one" not in _ids(_ctx(pi="1.20"))


def test_no_payback():
    assert "viability.no_payback" in _ids(_ctx(pb=None))
    assert "viability.no_payback" not in _ids(_ctx(pb=6))


def test_irr_unreliable_on_alternating_flow():
    n = 4
    cf = Statement(CASHFLOW_LINES, n)
    cf["C13"] = [Decimal(-100), Decimal(50), Decimal(-30), Decimal(80)]
    model = build_sample_project()
    ctx = ReviewContext(model=model, result=_result(n=n, irr="0.20", cashflow=cf))
    assert "viability.irr_unreliable" in {f.id for f in run_review(ctx).findings}
    cf2 = Statement(CASHFLOW_LINES, n)
    cf2["C13"] = [Decimal(-100), Decimal(40), Decimal(50), Decimal(60)]
    ctx2 = ReviewContext(model=model, result=_result(n=n, irr="0.20", cashflow=cf2))
    assert "viability.irr_unreliable" not in {f.id for f in run_review(ctx2).findings}


def test_sample_project_is_flagged_as_marginal():
    # Демо «Мини-производство» убыточно (NPV<0, PI<1, нет окупаемости) — ревью это ловит.
    model = build_sample_project()
    review = run_review(ReviewContext(model=model, result=run(model)))
    assert review.light == "risk"
    ids = {f.id for f in review.findings}
    assert {"viability.npv_negative", "viability.pi_below_one",
            "viability.no_payback", "viability.irr_undefined"} <= ids


# --- R2: liquidity ---

def _stmt(catalog, n=6, **rows):
    """Отчёт с явно заданными строками (без пересчёта итогов — для изоляции правил)."""
    st = Statement(catalog, n)
    for code, vals in rows.items():
        st[code] = [Decimal(str(v)) for v in vals]
    return st


def _liq_ctx(*, balance=None, cashflow=None, income=None, peak=None,
             auto_fin=False, n=6) -> ReviewContext:
    model = build_sample_project()
    model.settings.discount_rate_annual = Decimal("0.15")
    model.financing.auto_financing.enabled = auto_fin
    result = CalcResult(
        engine_version="t", n=n,
        income=income if income is not None else Statement(INCOME_LINES, n),
        cashflow=cashflow if cashflow is not None else Statement(CASHFLOW_LINES, n),
        balance=balance if balance is not None else Statement(BALANCE_LINES, n),
        profit_use=Statement(PROFIT_USE_LINES, n),
        metrics=InvestmentMetrics(
            npv=Decimal("1"), irr_annual=Decimal("0.30"),
            pi=Decimal("1.5"), pb_months=1,
            peak_financing_need=Decimal(str(peak)) if peak is not None else None,
        ),
    )
    return ReviewContext(model=model, result=result)


def test_cash_gap_fires_without_autofinancing():
    bal = _stmt(BALANCE_LINES, B1=[100, -50, -200, 10, 5, 5])
    fired = liquidity.cash_gap(_liq_ctx(balance=bal, auto_fin=False), DEFAULT_CONFIG)
    assert len(fired) == 1 and fired[0].severity == "risk"
    assert fired[0].evidence["worst_month"] == 3          # худший месяц — самый глубокий минус
    # автоподбор включён — движок закрывает разрыв, находки нет
    assert liquidity.cash_gap(_liq_ctx(balance=bal, auto_fin=True), DEFAULT_CONFIG) == []
    # нет отрицательных остатков — тишина
    bal_ok = _stmt(BALANCE_LINES, B1=[100, 50, 20, 10, 5, 5])
    assert liquidity.cash_gap(_liq_ctx(balance=bal_ok), DEFAULT_CONFIG) == []


def test_financing_dependency():
    cf = _stmt(CASHFLOW_LINES, C21=[100, 0, 0, 0, 0, 0])
    assert liquidity.financing_dependency(_liq_ctx(cashflow=cf, peak=1000), DEFAULT_CONFIG)
    # в пределах порога 3× — тишина
    assert liquidity.financing_dependency(_liq_ctx(cashflow=cf, peak=200), DEFAULT_CONFIG) == []
    # без собственного капитала не делим на ноль
    cf0 = _stmt(CASHFLOW_LINES, C21=[0, 0, 0, 0, 0, 0])
    assert liquidity.financing_dependency(_liq_ctx(cashflow=cf0, peak=1000), DEFAULT_CONFIG) == []
    # потребности в финансировании нет
    assert liquidity.financing_dependency(_liq_ctx(cashflow=cf, peak=None), DEFAULT_CONFIG) == []


def test_current_ratio_low():
    bal = _stmt(BALANCE_LINES, B8=[200, 150, 80, 300, 300, 300],
                B25=[100, 100, 100, 100, 100, 100])
    fired = liquidity.current_ratio_low(_liq_ctx(balance=bal), DEFAULT_CONFIG)
    assert len(fired) == 1 and fired[0].evidence["month"] == 3
    # текущие активы всюду покрывают обязательства — тишина
    bal_ok = _stmt(BALANCE_LINES, B8=[200, 200, 200, 200, 200, 200],
                   B25=[100, 100, 100, 100, 100, 100])
    assert liquidity.current_ratio_low(_liq_ctx(balance=bal_ok), DEFAULT_CONFIG) == []


def test_overleverage():
    bal = _stmt(BALANCE_LINES, B22=[0, 0, 0, 0, 0, 300],
                B26=[0, 0, 0, 0, 0, 300], B33=[100, 100, 100, 100, 100, 100])
    assert liquidity.overleverage(_liq_ctx(balance=bal), DEFAULT_CONFIG)
    # рычаг в пределах порога 2× — тишина
    bal_ok = _stmt(BALANCE_LINES, B22=[0, 0, 0, 0, 0, 50],
                   B26=[0, 0, 0, 0, 0, 50], B33=[100, 100, 100, 100, 100, 100])
    assert liquidity.overleverage(_liq_ctx(balance=bal_ok), DEFAULT_CONFIG) == []
    # отрицательный капитал — коэффициент не считаем (guard)
    bal_neg = _stmt(BALANCE_LINES, B22=[0, 0, 0, 0, 0, 300],
                    B26=[0, 0, 0, 0, 0, 0], B33=[0, 0, 0, 0, 0, -10])
    assert liquidity.overleverage(_liq_ctx(balance=bal_neg), DEFAULT_CONFIG) == []


def test_interest_coverage_low_risk_and_warning():
    inc_risk = _stmt(INCOME_LINES, I18=[100, 0, 0, 0, 0, 0], I23=[-50, 0, 0, 0, 0, 0])
    fired = liquidity.interest_coverage_low(_liq_ctx(income=inc_risk), DEFAULT_CONFIG)
    assert fired and fired[0].severity == "risk"          # покрытие 0,5 < 1 → risk
    inc_warn = _stmt(INCOME_LINES, I18=[100, 0, 0, 0, 0, 0], I23=[20, 0, 0, 0, 0, 0])
    warn = liquidity.interest_coverage_low(_liq_ctx(income=inc_warn), DEFAULT_CONFIG)
    assert warn and warn[0].severity == "warning"         # покрытие 1,2 ∈ [1; 1,5) → warning
    inc_ok = _stmt(INCOME_LINES, I18=[100, 0, 0, 0, 0, 0], I23=[100, 0, 0, 0, 0, 0])
    assert liquidity.interest_coverage_low(_liq_ctx(income=inc_ok), DEFAULT_CONFIG) == []
    # процентов нет — правило молчит
    assert liquidity.interest_coverage_low(_liq_ctx(), DEFAULT_CONFIG) == []


def test_run_review_surfaces_liquidity_risk():
    # Полный прогон реестра: кассовый разрыв поднимает «светофор» до risk.
    bal = _stmt(BALANCE_LINES, B1=[100, -50, -200, 10, 5, 5])
    review = run_review(_liq_ctx(balance=bal, auto_fin=False))
    assert review.light == "risk"
    assert "liquidity.cash_gap" in {f.id for f in review.findings}


# --- R3: structure ---

def _income(**rows) -> Statement:
    return _stmt(INCOME_LINES, **rows)


def test_revenue_concentration():
    ctx = _liq_ctx()
    ctx.model.operating_plan.products = [Product(id="A", name="Хлеб"), Product(id="B", name="Соль")]
    ctx.model.operating_plan.sales = [
        SalesLine(product_id="A", volume=[Decimal(8)], price=[Decimal(100)]),
        SalesLine(product_id="B", volume=[Decimal(1)], price=[Decimal(100)]),
    ]
    fired = structure.revenue_concentration(ctx, DEFAULT_CONFIG)
    assert len(fired) == 1 and fired[0].evidence["top_product"] == "A"
    # сбалансированный портфель — тишина
    ctx.model.operating_plan.sales = [
        SalesLine(product_id="A", volume=[Decimal(5)], price=[Decimal(100)]),
        SalesLine(product_id="B", volume=[Decimal(5)], price=[Decimal(100)]),
    ]
    assert structure.revenue_concentration(ctx, DEFAULT_CONFIG) == []
    # один продукт — концентрация не считается находкой
    ctx.model.operating_plan.sales = [
        SalesLine(product_id="A", volume=[Decimal(5)], price=[Decimal(100)]),
    ]
    assert structure.revenue_concentration(ctx, DEFAULT_CONFIG) == []


def test_gross_margin_rules():
    neg_ctx = _liq_ctx(income=_income(I4=[100, 0, 0, 0, 0, 0], I8=[-20, 0, 0, 0, 0, 0]))
    neg = structure.negative_gross_margin(neg_ctx, DEFAULT_CONFIG)
    assert neg and neg[0].severity == "risk"
    thin_ctx = _liq_ctx(income=_income(I4=[100, 0, 0, 0, 0, 0], I8=[5, 0, 0, 0, 0, 0]))
    thin = structure.thin_gross_margin(thin_ctx, DEFAULT_CONFIG)
    assert thin and thin[0].severity == "warning"
    # здоровая маржа — оба правила молчат
    healthy = _liq_ctx(income=_income(I4=[100, 0, 0, 0, 0, 0], I8=[40, 0, 0, 0, 0, 0]))
    assert structure.negative_gross_margin(healthy, DEFAULT_CONFIG) == []
    assert structure.thin_gross_margin(healthy, DEFAULT_CONFIG) == []
    # отрицательная маржа не считается «тонкой» — её ловит risk-правило
    assert structure.thin_gross_margin(neg_ctx, DEFAULT_CONFIG) == []


def test_cost_line_outlier():
    ctx = _liq_ctx(income=_income(I4=[500, 0, 0, 0, 0, 0]))
    # Смесь прямых и постоянных статей; «Консалтинг» — выброс: > IQR и > 30% выручки.
    ctx.model.operating_plan.direct_costs = [DirectCostLine(name="Материалы", amount=[Decimal(10)])]
    ctx.model.operating_plan.fixed_costs = [
        FixedCostLine(name="Связь", amount=[Decimal(11)]),
        FixedCostLine(name="Реклама", amount=[Decimal(12)]),
        FixedCostLine(name="Консалтинг", amount=[Decimal(200)]),
    ]
    fired = structure.cost_line_outlier(ctx, DEFAULT_CONFIG)
    assert len(fired) == 1 and fired[0].evidence["line"] == "Консалтинг"
    assert fired[0].severity == "info"
    # ровный ряд статей — выброса нет
    ctx.model.operating_plan.direct_costs = []
    ctx.model.operating_plan.fixed_costs = [
        FixedCostLine(name="Аренда", amount=[Decimal(10)]),
        FixedCostLine(name="Связь", amount=[Decimal(11)]),
        FixedCostLine(name="Реклама", amount=[Decimal(12)]),
        FixedCostLine(name="Прочее", amount=[Decimal(13)]),
    ]
    assert structure.cost_line_outlier(ctx, DEFAULT_CONFIG) == []
    # мало статей — IQR неустойчив, правило не срабатывает
    ctx.model.operating_plan.fixed_costs = [
        FixedCostLine(name="Аренда", amount=[Decimal(10)]),
        FixedCostLine(name="Консалтинг", amount=[Decimal(500)]),
    ]
    assert structure.cost_line_outlier(ctx, DEFAULT_CONFIG) == []


def test_run_review_includes_structure_risk():
    # Полный прогон: отрицательная валовая маржа — единственная сработавшая находка (risk).
    ctx = _liq_ctx(income=_income(I4=[100, 0, 0, 0, 0, 0], I8=[-20, 0, 0, 0, 0, 0]))
    ctx.model.operating_plan.sales = []
    ctx.model.operating_plan.direct_costs = []
    ctx.model.operating_plan.fixed_costs = []
    review = run_review(ctx)
    assert {f.id for f in review.findings} == {"structure.negative_gross_margin"}
    assert review.light == "risk"
