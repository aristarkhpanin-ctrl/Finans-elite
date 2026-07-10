"""Тесты ревью бизнес-плана (R0 каркас, R1 viability)."""
from decimal import Decimal

from calc_core import run
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
