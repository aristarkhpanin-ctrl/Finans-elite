"""Оценка стоимости и мост EV → цена (Финанс-Аудит, «Экран 4»; методика — SPEC, Прил. П).

Проверяются решения методики, которые легко потерять при следующей правке:

* база прогноза — **нормализованный** показатель, ради чего нормализация и делалась (П.1);
* без амортизации оценка не считается, а не считается с нулём (П.2);
* терминальная стоимость не существует при ``g ≥ WACC`` (П.2);
* долг в мосте берётся из реестра, а агрегат — с оговоркой (П.3);
* забалансовое из EV **не вычитается**, но названо (П.3, Л.1);
* дисконта нет без запрошенной цены (П.4);
* «не посчитано» — это не «ноль рублей» (П.6).
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, build_obligations
from audit_core.earnings import normalize_earnings
from audit_core.models import AuditSubjectModel
from audit_core.valuation import build_valuation

D = Decimal

ASSUMPTIONS = {
    "enabled": True, "horizon_years": 5, "wacc": "0.20", "terminal_growth": "0.03",
    "tax_rate": "0.20", "growth": ["0.10", "0.08", "0.06", "0.05", "0.04"],
    "capex": ["70", "70", "70", "70", "70"],
    "nwc_change": ["20", "15", "12", "10", "10"],
}


def model(valuation: dict | None = None, **over) -> AuditSubjectModel:
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
        "valuation": {**ASSUMPTIONS, **(valuation or {})},
    }
    for key, value in over.items():
        if key in ("balance", "income"):
            data[key] = {**data[key], **value}      # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def valuation(m: AuditSubjectModel):
    result = analyze(m)
    return build_valuation(m, result, normalize_earnings(m, result),
                           build_obligations(m, result))


def bridge(v, label: str):
    found = [b for b in v.bridge if b.label == label]
    assert len(found) == 1, f"ожидалось одно слагаемое «{label}»"
    return found[0]


# ── П.1. Прогноз и его база ──────────────────────────────────────────────────

def test_disabled_valuation_is_not_zero_but_absent():
    """Выключенная оценка — «не посчитана», а не «бизнес стоит 0»."""
    v = valuation(model({"enabled": False}))
    assert not v.enabled and v.blockers
    assert v.enterprise_value is None and v.equity_value is None


def test_base_is_the_normalized_ebit_not_the_reported_one():
    """Ради этого нормализация и делалась: оценка идёт от устойчивого заработка."""
    plain = valuation(model())
    assert plain.base_ebit == D(220)                     # 1980 − 1386 − 374
    adjusted = valuation(model(earnings_adjustments=[
        {"label": "Разовый доход", "kind": "one_off", "amounts": ["0", "-40"]}]))
    assert adjusted.base_ebit == D(180)
    assert adjusted.enterprise_value < plain.enterprise_value


def test_base_is_ebit_even_when_the_multiple_is_to_ebitda():
    """Амортизация стоит в FCFF отдельным слагаемым — в базе её быть не должно.

    Иначе она учитывается дважды и стоимость завышается ровно на неё.
    """
    v = valuation(model())
    assert v.base_code == "EBITDA"                       # амортизация введена
    assert v.base_ebit == D(220)                         # но база — EBIT
    assert v.implied_multiple == v.enterprise_value / D(280)   # мультипликатор к EBITDA


def test_short_assumption_row_extends_by_its_last_value():
    """Рост задан на один год из пяти — хвост продлевается, а не обнуляется."""
    v = valuation(model({"growth": ["0.10"]}))
    prev = v.base_ebit
    for y in v.years:
        assert abs(y.ebit / prev - D("1.10")) < D("0.0001")
        prev = y.ebit


# ── П.2. Чего не хватает для оценки ──────────────────────────────────────────

def test_without_depreciation_valuation_is_refused_with_a_reason():
    """Ноль вместо амортизации занизил бы поток ровно на неё."""
    v = valuation(model(income={"M_DEPRECIATION": []}))
    assert v.enterprise_value is None
    assert any("амортизация" in b for b in v.blockers)
    assert any("EBITDA" in b for b in v.blockers)         # названа та же строка


def test_loss_making_business_is_not_valued():
    """Дисконтировать поток от убытка бессмысленно: любая стоимость была бы выдумкой."""
    v = valuation(model(income={"I_OPEX": ["340", "3000"]}))
    assert v.enterprise_value is None
    assert any("не положителен" in b for b in v.blockers)


def test_terminal_growth_above_wacc_has_no_value():
    """При g ≥ WACC формула Гордона даёт бесконечность или отрицательную величину."""
    v = valuation(model({"terminal_growth": "0.25"}))
    assert v.enterprise_value is None
    assert any("не меньше ставки" in b for b in v.blockers)


def test_terminal_share_shows_how_much_rests_on_the_tail():
    v = valuation(model())
    assert v.terminal_share is not None
    assert D(0) < v.terminal_share < D(1)
    assert v.pv_forecast + v.pv_terminal == v.enterprise_value


def test_discount_factors_are_a_geometric_series():
    v = valuation(model())
    for y in v.years:
        assert y.discount_factor == D(1) / (D("1.20") ** y.year)
        assert y.present_value == y.fcff * y.discount_factor


def test_fcff_follows_the_declared_formula():
    v = valuation(model())
    y = v.years[0]
    assert y.fcff == y.ebit * D("0.8") + y.depreciation - y.capex - y.nwc_change


# ── П.3. Мост EV → цена ──────────────────────────────────────────────────────

def test_debt_comes_from_the_register_when_it_is_filled():
    """Реестр даёт именно процентный долг, названный по договорам."""
    v = valuation(model(obligations=[
        {"creditor": "Сбербанк", "kind": "credit", "amount": "300"},
        {"creditor": "Лизинг", "kind": "lease", "amount": "80"}]))
    item = bridge(v, "Долг и займы")
    assert item.amount == D(380)
    assert "реестр" in item.note
    assert not any("завышает чистый долг" in w for w in v.warnings)


def test_aggregate_debt_is_used_with_a_stated_caveat():
    """Агрегат включает кредиторку и завышает долг — молча занижать цену нельзя."""
    v = valuation(model())
    item = bridge(v, "Долг и займы")
    assert item.amount == D(520)                          # P_LONG 200 + P_SHORT 320
    assert any("завышает чистый долг" in w for w in v.warnings)


def test_off_balance_is_not_subtracted_but_is_named():
    """Условное обязательство ещё не наступило (Л.1) — но промолчать о нём нельзя."""
    v = valuation(model(obligations=[
        {"creditor": "Банк", "kind": "credit", "amount": "520"},
        {"creditor": "Связанная", "kind": "guarantee", "amount": "180"}]))
    assert bridge(v, "Долг и займы").amount == D(520)     # 180 в долг не вошли
    assert any("Забалансовые обязательства" in w and "не входят" in w
               for w in v.warnings)


def test_bridge_arithmetic_is_the_declared_one():
    v = valuation(model({"minority_interest": "40"}))
    ev = bridge(v, "Enterprise Value").amount
    debt = bridge(v, "Долг и займы").amount
    cash = bridge(v, "Денежные средства").amount
    minority = bridge(v, "Доля миноритариев").amount
    assert bridge(v, "Цена за 100% доли").amount == ev - debt + cash - minority
    assert v.equity_value == ev - debt + cash - minority


def test_minority_is_entered_not_derived():
    assert "вводится" in bridge(valuation(model()), "Доля миноритариев").note


# ── П.4. Дисконт ─────────────────────────────────────────────────────────────

def test_no_asking_price_means_no_discount():
    """Величина без второго операнда — не «ноль процентов», её просто нет."""
    v = valuation(model())
    assert v.asking_price is None and v.discount is None


def test_discount_appears_with_the_asking_price():
    v = valuation(model({"asking_price": "1400"}))
    assert v.discount == D(1) - v.equity_value / D(1400)


def test_price_above_the_asking_gives_a_negative_discount():
    """Оценка выше запрошенной — премия; она показывается знаком, а не нулём."""
    v = valuation(model({"asking_price": "100"}))
    assert v.discount < 0


# ── П.5. Чувствительность ────────────────────────────────────────────────────

def test_sensitivity_grid_is_five_by_five_around_the_assumptions():
    v = valuation(model())
    assert len(v.sensitivity) == 5 and all(len(r) == 5 for r in v.sensitivity)
    assert v.sensitivity_wacc[2] == D("0.20")             # центр — заданный WACC
    assert v.sensitivity_growth[2] == D("0.03")
    assert v.sensitivity[2][2] == v.equity_value          # центральная клетка = оценка


def test_range_comes_from_the_grid():
    """Диапазон — это чувствительность, а не отдельные сценарии (П.5)."""
    v = valuation(model())
    cells = [c for row in v.sensitivity for c in row if c is not None]
    assert v.equity_min == min(cells) and v.equity_max == max(cells)


def test_impossible_cells_are_absent_not_zero():
    """Клетка с g ≥ WACC не существует — ноль читался бы как «бизнес ничего не стоит»."""
    v = valuation(model({"wacc": "0.05", "terminal_growth": "0.03"}))
    flat = [c for row in v.sensitivity for c in row]
    assert None in flat
    assert all(c is None or c != 0 for c in flat)


# ── П.6. Чего оценка не делает ───────────────────────────────────────────────

def test_gaps_are_named_rather_than_faked():
    v = valuation(model())
    joined = " ".join(v.not_computed)
    assert "Сопоставимые сделки" in joined
    assert "IRR сделки" in joined


def test_multiple_is_declared_as_our_own_not_a_market_benchmark():
    v = valuation(model())
    assert v.implied_multiple is not None
    assert any("не рыночный ориентир" in line for line in v.not_computed)


def test_empty_model_is_inert():
    v = build_valuation(AuditSubjectModel(), analyze(AuditSubjectModel()))
    assert not v.enabled and v.enterprise_value is None and v.bridge == []
