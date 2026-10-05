"""План-факт после сделки (Финанс-Аудит, «Экран 17»; методика — SPEC, Приложение Т).

Проверяются решения методики, которые легко потерять при следующей правке:

* факт берётся из отчётности дела — второго источника фактических чисел нет (Т.1);
* период без плана в сравнение не идёт, а нулевой факт назван двусмысленным (Т.2);
* потоки складываются, остатки берутся на конец — сложить остаток нельзя (Т.2);
* направление объявлено: себестоимость ниже плана — успех, а не недобор (Т.3);
* предсказанное посчитано, фактическое введено; отметка-сирота названа (Т.4);
* доходности вложения нет (Т.5).
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, build_obligations, detect_flags
from audit_core.models import AuditSubjectModel
from audit_core.planfact import MATERIAL, NOT_COMPUTED, build_plan_fact

D = Decimal


def case(**over) -> AuditSubjectModel:
    """Дело на 2 года: выручка 1800 → 1900, деньги 100 → 130."""
    data = {
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "420"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "700"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "420"],
        },
        "income": {
            "I_REVENUE": ["1800", "1900"], "I_COGS": ["1260", "1386"],
            "I_OPEX": ["340", "374"], "I_INTEREST": ["40", "40"],
            "I_OTHER": ["0", "0"], "I_TAX": ["32", "36"],
        },
    }
    for key, value in over.items():
        if key in ("balance", "income"):
            data[key] = {**data[key], **value}      # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def plan_fact(m: AuditSubjectModel, with_flags: bool = True):
    result = analyze(m)
    flags = (detect_flags(m, result, build_obligations(m, result))
             if with_flags and result.n else None)
    return build_plan_fact(m, flags)


def row(pf, code: str):
    found = [r for r in pf.rows if r.code == code]
    assert len(found) == 1, f"ожидалась одна строка {code}"
    return found[0]


# ── Т.1. План вводится, факт уже есть ────────────────────────────────────────

def test_without_a_plan_there_is_nothing_to_compare():
    """Плана нет — это не «всё сошлось»."""
    pf = plan_fact(case())
    assert not pf.available and pf.rows == []
    assert any("Прогноз продавца не введён" in c for c in pf.caveats)


def test_fact_comes_from_the_case_reporting():
    """Второго источника фактических чисел нет: иначе дело показывало бы две выручки."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"]}))
    assert row(pf, "I_REVENUE").fact == D(3700)      # 1800 + 1900 из отчётности


# ── Т.2. Охват сравнения и нулевой факт ──────────────────────────────────────

def test_only_periods_with_a_plan_are_compared():
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["0", "2200"]}))
    assert pf.periods == ["2024"]
    assert row(pf, "I_REVENUE").fact == D(1900)      # только второй период
    assert any("Периоды без плана в сравнение не вошли" in c for c in pf.caveats)


def test_zero_fact_is_shown_as_a_shortfall_and_called_ambiguous():
    """Ноль значит либо «не было», либо «ещё не отражено» — молча выбрать нельзя."""
    pf = plan_fact(case(income={"I_REVENUE": ["0", "0"]},
                        seller_plan={"I_REVENUE": ["1800", "2200"]}))
    item = row(pf, "I_REVENUE")
    assert item.fact == 0 and item.delta_share == D(-1) and item.verdict == "worse"
    assert "платформа их не различает" in item.note
    assert any("Нулевой факт при заданном плане" in c for c in pf.caveats)


def test_flows_are_summed_and_levels_taken_at_the_end():
    """Сложить остаток денег за два года — получить величину, которой не существует."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"],
                                     "A_CASH": ["100", "200"]}))
    assert row(pf, "I_REVENUE").plan == D(4000)      # поток — сумма
    assert row(pf, "A_CASH").plan == D(200)          # остаток — конец периода
    assert row(pf, "A_CASH").fact == D(130)


def test_line_absent_from_the_plan_is_not_compared():
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"]}))
    assert [r.code for r in pf.rows] == ["I_REVENUE"]


def test_empty_plan_rows_are_said_rather_than_shown_as_success():
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["0", "0"]}))
    assert not pf.available
    assert any("Ни в одном периоде план не заполнен" in c for c in pf.caveats)


# ── Т.3. Направление отклонения ──────────────────────────────────────────────

def test_revenue_below_plan_is_bad_and_cost_below_plan_is_good():
    """«−12%» само по себе не значит ничего: у расхода минус читается как успех."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2400"],
                                     "I_COGS": ["1500", "1800"]}))
    assert row(pf, "I_REVENUE").delta < 0 and row(pf, "I_REVENUE").verdict == "worse"
    assert row(pf, "I_COGS").delta < 0 and row(pf, "I_COGS").verdict == "better"


def test_small_deviation_is_shown_but_not_judged():
    """Порог существенности объявлен: в его пределах отклонение не красится."""
    # План 3750 против факта 3700 — 1,3%, меньше порога.
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "1950"]}))
    item = row(pf, "I_REVENUE")
    assert abs(item.delta_share) < MATERIAL
    assert item.verdict == "on_plan" and item.delta != 0


# ── Т.4. Флаги ───────────────────────────────────────────────────────────────

def test_predicted_is_computed_and_actual_is_entered():
    m = case(seller_plan={"I_REVENUE": ["1800", "2200"]},
             realized_flags=[{"code": "receivables_outpace_revenue", "realized": True,
                              "actual_cost": "150", "note": "дебиторка не собрана"}])
    pf = plan_fact(m)
    item = [f for f in pf.flags if f.code == "receivables_outpace_revenue"][0]
    assert item.predicted is not None and item.predicted > 0   # посчитано платформой
    assert item.actual_cost == D(150)                          # введено аналитиком
    assert pf.realized_total == D(150)
    assert pf.predicted_total == item.predicted


def test_unmarked_flag_is_listed_but_not_counted():
    """Флаг без отметки — не «не реализовался», а «не отмечен»; в итог он не идёт."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"]}))
    assert pf.flags and all(not f.realized for f in pf.flags)
    assert pf.predicted_total == 0 and pf.realized_total == 0


def test_realized_flag_without_a_money_measure_is_counted_apart():
    """Сводить факт не с чем: предсказанной величины у такого флага нет вовсе."""
    m = case(balance={"P_EQUITY": ["500", "-100"], "P_LONG": ["200", "1220"]},
             seller_plan={"I_REVENUE": ["1800", "2200"]},
             realized_flags=[{"code": "negative_equity", "realized": True,
                              "actual_cost": "80"}])
    pf = plan_fact(m)
    assert pf.unpriced_realized == 1
    assert pf.realized_total == 0                     # в итог не вошёл
    assert any("без денежной меры" in c for c in pf.caveats)


def test_mark_for_a_vanished_flag_is_named_not_dropped():
    """Молча выбросить отметку значило бы потерять работу аналитика."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"]},
                        realized_flags=[{"code": "flag_that_no_longer_fires",
                                         "realized": True, "actual_cost": "10"}]))
    assert pf.orphan_marks == ["flag_that_no_longer_fires"]
    assert any("которых в текущем реестре больше нет" in c for c in pf.caveats)


def test_actual_cost_not_entered_is_not_zero():
    """«Факт ещё не оценён» и «обошёлся в ноль» — разные вещи."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"]},
                        realized_flags=[{"code": "receivables_outpace_revenue",
                                         "realized": True}]))
    item = [f for f in pf.flags if f.code == "receivables_outpace_revenue"][0]
    assert item.realized and item.actual_cost is None
    assert pf.predicted_total > 0 and pf.realized_total == 0


# ── Т.5. Чего план-факт не считает ───────────────────────────────────────────

def test_no_investment_return_is_produced():
    """Запрошенная цена уплаченную не заменяет: торг на то и был."""
    pf = plan_fact(case(seller_plan={"I_REVENUE": ["1800", "2200"]}))
    assert not hasattr(pf, "irr")
    assert not hasattr(pf, "investment_return")
    assert any("Доходность вложения" in line for line in pf.not_computed)
    assert len(pf.not_computed) == len(NOT_COMPUTED)


def test_empty_model_is_inert():
    pf = build_plan_fact(AuditSubjectModel())
    assert not pf.available and pf.rows == [] and pf.flags == []
