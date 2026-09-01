"""Анализ рисков оценки (Финанс-Аудит, «Экран 13»; методика — SPEC, Приложение Р).

Проверяются решения методики, которые легко потерять при следующей правке:

* смещение мультипликативное и одно для всех параметров, шаг объявлен (Р.1);
* торнадо не выдумывает сторону, которой не существует (Р.1);
* прогон без оценки не заменяется нулём и не выбрасывается молча (Р.2);
* неполное распределение не подменяется значением по умолчанию (Р.2);
* результат воспроизводим (Р.2);
* вероятность существует только против запрошенной цены (Р.4);
* сценариев с вероятностями и стресс-теста нет — и это сказано (Р.5).
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, build_obligations
from audit_core.earnings import normalize_earnings
from audit_core.models import AuditSubjectModel
from audit_core.risk import NOT_COMPUTED, analyze_risk

D = Decimal

VALUATION = {
    "enabled": True, "horizon_years": 5, "wacc": "0.20", "terminal_growth": "0.03",
    "tax_rate": "0.20", "growth": ["0.10", "0.08", "0.06", "0.05", "0.04"],
    "capex": ["70"], "nwc_change": ["20"],
}


def model(risk: dict | None = None, valuation: dict | None = None,
          **over) -> AuditSubjectModel:
    """Предприятие на 2 года: EBIT 220, амортизация 60, долг 520, деньги 130."""
    data = {
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "220"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "600"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "320"],
        },
        "income": {
            "I_REVENUE": ["1800", "1980"], "I_COGS": ["1260", "1386"],
            "I_OPEX": ["340", "374"], "I_INTEREST": ["40", "40"],
            "I_OTHER": ["0", "0"], "I_TAX": ["32", "36"],
            "M_DEPRECIATION": ["50", "60"],
        },
        "valuation": {**VALUATION, **(valuation or {})},
        "risk": {"iterations": 200, **(risk or {})},
    }
    for key, value in over.items():
        if key in ("balance", "income"):
            data[key] = {**data[key], **value}      # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def risk(m: AuditSubjectModel):
    result = analyze(m)
    return analyze_risk(m, result, normalize_earnings(m, result),
                        build_obligations(m, result))


def bar(res, param: str):
    found = [b for b in res.tornado if b.param == param]
    assert len(found) == 1, f"ожидался один столбец {param}"
    return found[0]


UNIFORM = {"kind": "uniform", "low": "0.9", "high": "1.1"}


# ── Доступность ──────────────────────────────────────────────────────────────

def test_without_a_valuation_there_is_nothing_to_analyse():
    """Причины берутся из оценки, чтобы человек не искал их на другом экране."""
    res = risk(model(valuation={"enabled": False}))
    assert not res.available and res.blockers
    assert res.tornado == [] and res.monte_carlo is None


def test_valuation_blockers_are_carried_over_verbatim():
    res = risk(model(income={"M_DEPRECIATION": []}))
    assert not res.available
    assert any("амортизация" in b for b in res.blockers)


# ── Р.1. Торнадо ─────────────────────────────────────────────────────────────

def test_tornado_covers_every_assumption_and_is_sorted_by_span():
    res = risk(model())
    assert {b.param for b in res.tornado} == {
        "wacc", "terminal_growth", "tax_rate", "growth", "capex", "nwc_change"}
    spans = [b.span for b in res.tornado if b.span is not None]
    assert spans == sorted(spans, reverse=True)


def test_step_is_declared_and_configurable():
    """Шаг — соглашение: он объявлен, показывается и его можно изменить."""
    assert risk(model()).step == D("0.10")
    res = risk(model({"tornado_step": "0.25"}))
    assert res.step == D("0.25")
    assert all(b.step == D("0.25") for b in res.tornado)
    # Больший шаг двигает цену сильнее — иначе шаг не применялся бы.
    assert bar(res, "wacc").span > bar(risk(model()), "wacc").span


def test_shift_is_multiplicative_for_scalars_and_rows_alike():
    """Одно правило на все параметры: иначе столбцы несопоставимы."""
    res = risk(model())
    # Ставка дисконтирования — скаляр, рост показателя — ряд; оба сдвинулись.
    assert bar(res, "wacc").span > 0
    assert bar(res, "growth").span > 0


def test_wacc_moves_the_price_the_most_in_this_model():
    res = risk(model())
    assert res.tornado[0].param == "wacc"
    # Снижение ставки поднимает цену, рост — опускает.
    assert bar(res, "wacc").low_delta > 0 > bar(res, "wacc").high_delta


def test_unset_assumption_is_named_rather_than_shown_as_influential():
    """Незаданное допущение цену не двигает — и это сказано, а не выглядит нулём."""
    res = risk(model(valuation={"nwc_change": []}))
    item = bar(res, "nwc_change")
    assert item.span == 0 and "не задано" in item.note


def test_side_that_does_not_exist_is_not_replaced_by_the_base():
    """Смещение может увести туда, где оценки нет: это факт, а не «цена не изменилась»."""
    # Рост в постпрогнозе 19% при ставке 20%: +10% уводит его за ставку.
    res = risk(model(valuation={"terminal_growth": "0.19"}))
    item = bar(res, "terminal_growth")
    assert item.high_price is None and item.high_delta is None
    assert item.span is None
    assert "не считается" in item.note


def test_bars_without_a_span_sink_to_the_bottom():
    res = risk(model(valuation={"terminal_growth": "0.19"}))
    assert res.tornado[-1].param == "terminal_growth"


# ── Р.2. Монте-Карло ─────────────────────────────────────────────────────────

def test_no_uncertain_assumptions_means_no_monte_carlo():
    """Прогон по нулю распределений дал бы одну цену N раз и выглядел бы анализом."""
    assert risk(model()).monte_carlo is None


def test_monte_carlo_runs_and_reports_its_spread():
    res = risk(model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]}))
    mc = res.monte_carlo
    assert mc.iterations == 200 and mc.valued + mc.unvalued == 200
    assert mc.minimum < mc.median < mc.maximum
    assert mc.p10 <= mc.p25 <= mc.median <= mc.p75 <= mc.p90


def test_run_is_reproducible():
    """Без этого медиана менялась бы при каждом обновлении страницы."""
    m = model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]})
    assert risk(m).monte_carlo.median == risk(m).monte_carlo.median


def test_seed_changes_the_run():
    """Воспроизводимость — не то же, что постоянство: другой seed даёт другой прогон."""
    base = {"uncertain": [{"param": "wacc", "distribution": UNIFORM}]}
    first = risk(model({**base, "seed": 1})).monte_carlo
    second = risk(model({**base, "seed": 2})).monte_carlo
    assert first.median != second.median


def test_runs_without_a_valuation_are_counted_apart_not_zeroed():
    """Ноль занизил бы медиану, тихое выбрасывание скрыло бы такие прогоны вовсе."""
    # Широкое распределение роста в постпрогнозе уводит часть прогонов за ставку.
    res = risk(model({"uncertain": [{"param": "terminal_growth",
                                     "distribution": {"kind": "uniform", "low": "0.5",
                                                      "high": "8.0"}}]},
                     valuation={"terminal_growth": "0.05"}))
    mc = res.monte_carlo
    assert mc.unvalued > 0
    assert mc.valued + mc.unvalued == mc.iterations
    assert mc.minimum > 0                        # нулей в выборке нет


def test_histogram_holds_every_valued_run():
    res = risk(model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]}))
    mc = res.monte_carlo
    assert sum(h.count for h in mc.histogram) == mc.valued
    assert mc.histogram[0].from_ == mc.minimum


def test_incomplete_distribution_is_excluded_with_a_warning():
    """Подставить своё значение значило бы прогнать модель по чужому допущению."""
    res = risk(model({"uncertain": [
        {"param": "wacc", "distribution": {"kind": "uniform", "low": "0.9"}}]}))
    assert res.monte_carlo is None
    assert any("задано не полностью" in w for w in res.warnings)


def test_one_broken_distribution_does_not_cancel_the_others():
    res = risk(model({"uncertain": [
        {"param": "wacc", "distribution": UNIFORM},
        {"param": "growth", "distribution": {"kind": "normal", "mean": "1.0"}}]}))
    assert res.monte_carlo is not None and res.monte_carlo.valued > 0
    assert any("задано не полностью" in w for w in res.warnings)


def test_all_three_distribution_kinds_are_sampled():
    for dist in ({"kind": "uniform", "low": "0.9", "high": "1.1"},
                 {"kind": "normal", "mean": "1.0", "std": "0.05"},
                 {"kind": "triangular", "low": "0.9", "mode": "1.0", "high": "1.1"}):
        res = risk(model({"uncertain": [{"param": "wacc", "distribution": dist}]}))
        assert res.monte_carlo.valued > 0, dist["kind"]


# ── Р.3. Сверка медианы с базой ──────────────────────────────────────────────

def test_median_close_to_the_base_is_silent():
    res = risk(model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]}))
    assert abs(res.monte_carlo.median_drift) < D("0.10")
    assert not any("расходится с базовой" in w for w in res.warnings)


def test_skewed_distributions_are_reported():
    """Смещённые распределения — не «модель устойчива», и молчать об этом нельзя."""
    res = risk(model({"uncertain": [
        {"param": "wacc", "distribution": {"kind": "uniform", "low": "1.3",
                                           "high": "1.6"}}]}))
    assert abs(res.monte_carlo.median_drift) > D("0.10")
    assert any("расходится с базовой" in w for w in res.warnings)


# ── Р.4. Вероятность против запрошенной цены ─────────────────────────────────

def test_probability_needs_the_asking_price():
    """То же правило, что для дисконта: без второго операнда величины нет."""
    without = risk(model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]}))
    assert without.monte_carlo.below_asking is None

    with_price = risk(model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]},
                            valuation={"asking_price": "1400"}))
    assert with_price.monte_carlo.below_asking == D(1)   # база 776 — все прогоны ниже


def test_probability_is_a_share_of_valued_runs():
    res = risk(model({"uncertain": [{"param": "wacc", "distribution": UNIFORM}]},
                     valuation={"asking_price": "700"}))
    share = res.monte_carlo.below_asking
    assert D(0) < share < D(1)


# ── Р.5. Чего анализ не делает ───────────────────────────────────────────────

def test_no_probability_weighted_scenarios_are_produced():
    """Взвешенная вероятностями «ожидаемая цена» — сумма догадок, а не расчёт."""
    res = risk(model())
    assert not hasattr(res, "scenarios")
    assert not hasattr(res, "expected_price")
    assert any("Сценарии с вероятностями" in line for line in res.not_computed)


def test_gaps_are_named():
    res = risk(model())
    assert len(res.not_computed) == len(NOT_COMPUTED)
    assert any("потеря контрагента" in line for line in res.not_computed)


def test_empty_model_is_inert():
    res = analyze_risk(AuditSubjectModel(), analyze(AuditSubjectModel()))
    assert not res.available and res.tornado == []
