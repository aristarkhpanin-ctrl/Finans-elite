"""Проверка качества ввода (Финанс-Аудит, «Экран 19 — Ошибки данных»).

У каждого правила два теста: срабатывание на подготовленных данных и **тишина** на
здоровой отчётности. Без второго линтер быстро превращается в шум, который перестают
читать, — и тогда настоящая ошибка ввода теряется среди придирок.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from audit_core import check_input
from audit_core.models import AuditSubjectModel
from audit_core.samples import build_trading_subject


def model(**over) -> AuditSubjectModel:
    """Здоровая модель на 2 периода; именованные аргументы переопределяют части."""
    data = {
        "name": "ООО «Пример»",
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["100", "120"], "A_INVENTORY": ["30", "35"],
            "A_RECEIVABLE": ["40", "45"], "A_CASH": ["30", "50"],
            "P_EQUITY": ["120", "150"], "P_LONG": ["30", "30"], "P_SHORT": ["50", "70"],
        },
        "income": {
            "I_REVENUE": ["500", "600"], "I_COGS": ["300", "360"],
            "I_OPEX": ["80", "90"], "I_INTEREST": ["10", "12"],
            "I_OTHER": ["0", "0"], "I_TAX": ["22", "28"],
        },
    }
    data.update(over)
    return AuditSubjectModel.model_validate(data)


def codes(m: AuditSubjectModel) -> list[str]:
    return [i.code for i in check_input(m)]


def issue(m: AuditSubjectModel, code: str):
    found = [i for i in check_input(m) if i.code == code]
    assert found, f"правило {code} не сработало: {codes(m)}"
    return found[0]


# ── Тишина ────────────────────────────────────────────────────────────────────

def test_clean_model_is_silent():
    """Здоровая отчётность не даёт ни одной находки."""
    assert check_input(model()) == []


def test_empty_model_is_silent():
    """Пустая модель — это отсутствие ввода, а не ошибка ввода.

    Список проблем на только что созданном деле сказал бы пользователю, что он уже
    что-то сломал, хотя он ещё ничего не вводил.
    """
    assert check_input(AuditSubjectModel()) == []


@pytest.mark.parametrize("build", [build_trading_subject])
def test_samples_are_silent(build):
    """Эталонные семплы продукта проходят проверку чисто."""
    assert check_input(build()) == []


# ── Правила ───────────────────────────────────────────────────────────────────

def test_balance_gap_names_periods_and_amounts():
    m = model(balance={**model().balance, "P_EQUITY": ["120", "999"]})
    i = issue(m, "balance_gap")
    assert i.severity == "error" and i.periods == [1]
    assert "2024" in i.detail and "2023" not in i.detail
    assert i.evidence["max_gap"] == Decimal("-849")


def test_negative_line_flags_impossible_article():
    m = model(balance={**model().balance, "A_INVENTORY": ["30", "-5"]})
    i = issue(m, "negative_line")
    assert i.severity == "error" and i.periods == [1]
    assert "Запасы" in i.title and i.evidence["min"] == Decimal("-5")


def test_negative_equity_is_not_an_error():
    """Отрицательный капитал — законный факт, а не опечатка.

    Непокрытый убыток, превысивший вклады, — важнейшее, что может показать баланс.
    Объявить его ошибкой ввода значило бы спрятать худшую находку продукта.
    """
    m = model(balance={**model().balance, "P_EQUITY": ["-30", "150"],
                       "P_SHORT": ["200", "70"]})
    assert "negative_line" not in codes(m)


def test_cogs_without_revenue():
    m = model(income={**model().income, "I_REVENUE": ["0", "600"]})
    i = issue(m, "cogs_without_revenue")
    assert i.severity == "error" and i.periods == [0]


def test_retained_over_equity():
    m = model(balance={**model().balance, "M_RETAINED": ["500", "10"]})
    i = issue(m, "retained_over_equity")
    assert i.severity == "warning" and i.periods == [0]
    assert i.evidence["max_excess"] == Decimal("380")


def test_retained_not_entered_is_silent():
    """Правило молчит, когда справочная строка не введена вовсе."""
    assert "retained_over_equity" not in codes(model())


def test_half_of_reporting_missing():
    assert "no_income" in codes(model(income={}))
    assert "no_balance" in codes(model(balance={}))
    # обе половины введены — тишина
    assert "no_income" not in codes(model()) and "no_balance" not in codes(model())


def test_empty_period():
    m = model(
        periods=[{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"},
                 {"label": "2025", "kind": "year"}],
        balance={k: [*v, "0"] for k, v in model().balance.items()},
        income={k: [*v, "0"] for k, v in model().income.items()},
    )
    i = issue(m, "empty_period")
    assert i.periods == [2] and "2025" in i.detail


def test_duplicate_period_label_names_the_label():
    m = model(periods=[{"label": "2023", "kind": "year"}, {"label": "2023", "kind": "year"}])
    i = issue(m, "duplicate_period_label")
    assert i.severity == "error" and i.periods == [1] and "2023" in i.detail


def test_blank_period_label_is_info_not_error():
    """Без подписи период считается, но в свод группы не попадёт — это info."""
    m = model(periods=[{"label": "", "kind": "year"}, {"label": "2024", "kind": "year"}])
    i = issue(m, "blank_period_label")
    assert i.severity == "info" and i.periods == [0]
    # пустые подписи не считаются дублями друг друга
    assert "duplicate_period_label" not in codes(m)


def test_issues_sorted_by_severity():
    """Тяжёлые находки идут первыми: читают обычно только верх списка."""
    m = model(
        periods=[{"label": "", "kind": "year"}, {"label": "2024", "kind": "year"}],
        balance={**model().balance, "P_EQUITY": ["120", "999"], "M_RETAINED": ["500", "10"]},
    )
    order = [i.severity for i in check_input(m)]
    assert order == sorted(order, key=["error", "warning", "info"].index)
    assert order[0] == "error"


def test_check_does_not_touch_the_model():
    """Проверка только читает: модель после неё побайтово та же."""
    m = model(balance={**model().balance, "P_EQUITY": ["120", "999"]})
    before = m.model_dump(mode="json")
    check_input(m)
    assert m.model_dump(mode="json") == before
