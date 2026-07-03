"""Детерминизм расчёта относительно Decimal-контекста (#9).

`getcontext()` — thread-local; раньше `run()` полагался на дефолт потока (воркер
FastAPI получал prec=28 вместо 34). Теперь вычисления обёрнуты в `CALC_CONTEXT`,
поэтому результат один и тот же независимо от контекста вызывающего/потока/хоста.
"""
from __future__ import annotations

from decimal import Context, getcontext, localcontext

from calc_core import run
from calc_core.money import CALC_CONTEXT
from calc_core.samples import build_sample_project


def test_context_is_pinned():
    assert CALC_CONTEXT.prec == 34


def test_result_independent_of_hostile_ambient_context():
    model = build_sample_project()
    normal = run(model)
    # Крошечная точность у вызывающего не должна менять результат.
    with localcontext(Context(prec=6)):
        hostile = run(model)
    for code in ("B1", "B20", "B34"):
        assert normal.balance[code] == hostile.balance[code]
    assert normal.metrics.npv == hostile.metrics.npv
    assert normal.valuation.net_assets == hostile.valuation.net_assets


def test_run_does_not_leak_context():
    # localcontext восстанавливает контекст вызывающего после run().
    with localcontext(Context(prec=6)):
        run(build_sample_project())
        assert getcontext().prec == 6
