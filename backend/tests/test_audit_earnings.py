"""Качество прибыли и нормализация (Финанс-Аудит; методика — SPEC, Приложение К).

Главные проверки — не арифметика сложения поправок, а два решения методики: EBITDA не
выдаётся за EBIT, когда амортизации нет, и нормализованный показатель нигде не
подменяет отчётный молча.
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, normalize_earnings
from audit_core.models import AuditSubjectModel

D = Decimal


def model(*, depreciation: list[str] | None = None, adjustments=(), **over) -> AuditSubjectModel:
    """2 периода; EBIT = 1000−600−200 = 200 и 1200−720−240 = 240."""
    income = {
        "I_REVENUE": ["1000", "1200"], "I_COGS": ["600", "720"],
        "I_OPEX": ["200", "240"], "I_INTEREST": ["0", "0"],
        "I_OTHER": ["0", "0"], "I_TAX": ["0", "0"],
    }
    if depreciation is not None:
        income["M_DEPRECIATION"] = depreciation
    data = {
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {"A_CASH": ["500", "500"], "P_EQUITY": ["500", "500"]},
        "income": income,
        "earnings_adjustments": list(adjustments),
    }
    data.update(over)
    return AuditSubjectModel.model_validate(data)


def q(m: AuditSubjectModel):
    return normalize_earnings(m, analyze(m))


# ── EBITDA существует только при введённой амортизации ────────────────────────

def test_without_depreciation_it_is_ebit_and_says_so():
    """Без амортизации нормализуется EBIT — и показатель назван EBIT.

    Подписать EBIT словом EBITDA значило бы сдвинуть мультипликатор сделки на всю
    амортизацию: покупатель, умножающий 6× на не тот показатель, ошибётся ровно на неё.
    """
    r = q(model())
    assert r.base_code == "EBIT"
    assert r.reported == [D(200), D(240)]


def test_with_depreciation_it_is_ebitda():
    r = q(model(depreciation=["50", "60"]))
    assert r.base_code == "EBITDA"
    assert r.reported == [D(250), D(300)]        # EBIT + амортизация


def test_zero_depreciation_entered_is_still_ebitda():
    """Введённый ноль — это введённая величина: показатель EBITDA, просто равен EBIT.

    «Не введено» и «введён ноль» — разные факты, и здесь разница меняет **название**
    показателя, а не только число.
    """
    r = q(model(depreciation=["0", "0"]))
    assert r.base_code == "EBITDA" and r.reported == [D(200), D(240)]


# ── Поправки ──────────────────────────────────────────────────────────────────

def test_no_adjustments_is_inert():
    """Пустой список — содержательный ответ: отчётность принята как есть, оценка A."""
    r = q(model())
    assert r.normalized == r.reported
    assert r.grade == "A" and r.has_adjustments is False


def test_adjustment_signs_work_both_ways():
    """«−» убирает разовый доход, «+» возвращает лишний расход."""
    r = q(model(adjustments=[
        {"label": "Продажа склада", "kind": "one_off", "amounts": ["0", "-80"]},
        {"label": "Зарплата собственника сверх рынка", "kind": "owner",
         "amounts": ["0", "30"]},
    ]))
    assert r.normalized == [D(200), D(190)]      # 240 − 80 + 30
    assert [a.kind_label for a in r.adjustments] == [
        "Разовый доход или расход", "Вознаграждение собственника сверх рыночного"]


def test_adjustment_without_reason_is_not_applied():
    """Поправка без причины не применяется.

    Нормализованный показатель, который нельзя объяснить, нельзя и защитить в
    переговорах — а молча применённая безымянная поправка выглядит как расчёт.
    """
    r = q(model(adjustments=[{"label": "", "kind": "one_off", "amounts": ["0", "-500"]}]))
    assert r.normalized == r.reported and r.adjustments == []


def test_short_adjustment_row_is_padded_not_dropped():
    """Ряд короче числа периодов дополняется нулями, а не отбрасывается целиком."""
    r = q(model(adjustments=[{"label": "Разовое", "kind": "one_off", "amounts": ["-20"]}]))
    assert r.adjustments[0].amounts == [D(-20), D(0)]
    assert r.normalized == [D(180), D(240)]


def test_adjustment_total_is_reported():
    r = q(model(adjustments=[{"label": "Разовое", "kind": "one_off",
                              "amounts": ["-20", "-30"]}]))
    assert r.adjustments[0].total == D(-50)


# ── Шкала качества (объявленное соглашение) ───────────────────────────────────

def test_grade_a_for_small_deviation():
    r = q(model(adjustments=[{"label": "Мелочь", "kind": "one_off", "amounts": ["0", "-10"]}]))
    assert r.grade == "A" and r.deviation < D("0.05")


def test_grade_b_for_noticeable_deviation():
    r = q(model(adjustments=[{"label": "Разовое", "kind": "one_off", "amounts": ["0", "-30"]}]))
    assert r.grade == "B"                        # 30/240 = 12.5%


def test_grade_c_for_large_deviation():
    r = q(model(adjustments=[{"label": "Разовое", "kind": "one_off", "amounts": ["0", "-100"]}]))
    assert r.grade == "C"                        # 100/240 = 42%


def test_profit_wiped_out_is_c_with_its_own_reason():
    """Уход в минус — не «сильное расхождение», а другой факт: прибыльности нет.

    Формально это тоже C, но причина в оценке названа своя: покупателю важно не то,
    что числа разошлись, а то, что после очистки зарабатывать нечем.
    """
    r = q(model(adjustments=[{"label": "Разовое", "kind": "one_off", "amounts": ["0", "-260"]}]))
    assert r.grade == "C" and "уходит в ноль или минус" in r.grade_note


def test_zero_reported_has_no_grade():
    """Нулевой отчётный показатель не с чем сравнивать — буквы нет, а не «A»."""
    m = model(income={"I_REVENUE": ["1000", "800"], "I_COGS": ["600", "600"],
                      "I_OPEX": ["200", "200"], "I_INTEREST": ["0", "0"],
                      "I_OTHER": ["0", "0"], "I_TAX": ["0", "0"]})
    r = q(m)
    assert r.reported[1] == D(0)
    assert r.grade is None and r.deviation is None


# ── Границы модуля ────────────────────────────────────────────────────────────

def test_empty_model_is_silent():
    r = normalize_earnings(AuditSubjectModel(), analyze(AuditSubjectModel()))
    assert r.reported == [] and r.grade is None


def test_normalization_does_not_touch_the_model():
    """Нормализация только читает: модель после неё побайтово та же."""
    m = model(adjustments=[{"label": "Разовое", "kind": "one_off", "amounts": ["0", "-80"]}])
    before = m.model_dump(mode="json")
    normalize_earnings(m, analyze(m))
    assert m.model_dump(mode="json") == before


def test_not_in_golden_snapshot():
    """Нормализация не входит в снимок анализа — методика расчёта ею не меняется."""
    from audit_core.serialize import result_to_dict
    assert "earnings" not in result_to_dict(analyze(model()))
    assert "normalized" not in result_to_dict(analyze(model()))
