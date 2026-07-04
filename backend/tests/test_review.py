"""Тесты ревью бизнес-плана. R0 — каркас: пустой реестр, валидный ReviewResult."""
from calc_core import run
from calc_core.review import ReviewContext, run_review
from calc_core.review.aggregates import (
    gross_margin,
    per_product_revenue,
    total_net_revenue,
)
from calc_core.samples import build_sample_project


def test_review_smoke_empty_registry():
    model = build_sample_project()
    review = run_review(ReviewContext(model=model, result=run(model)))
    assert review.light == "ok"                       # R0: правил нет → находок нет
    assert review.counts == {"risk": 0, "warning": 0, "info": 0}
    assert review.findings == []


def test_aggregates_on_sample():
    model = build_sample_project()
    result = run(model)
    assert total_net_revenue(result) > 0              # у демо есть продажи
    gm = gross_margin(result)
    assert gm is not None and -1 <= gm <= 1           # доля в разумных границах
    rev_by_product = per_product_revenue(model)
    assert rev_by_product and all(v >= 0 for v in rev_by_product.values())
