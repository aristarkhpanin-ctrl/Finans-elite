"""Сводка дела и вердикт (Финанс-Аудит, «Экран 1»; методика — SPEC, Приложение Н).

Проверяются решения методики, которые легко потерять при следующей правке:

* ошибка ввода отменяет вердикт целиком, а не понижает его (Н.1);
* тяжёлый флаг не даёт зелёного, каким бы ни был светофор (Н.1);
* охват идёт вместе с вердиктом, а не сноской (Н.1);
* Долг / EBITDA не считается при неположительной прибыли (Н.2);
* оценки сделки на экране нет, и пробелы перечислены (Н.3).
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import (
    analyze,
    build_obligations,
    check_input,
    detect_flags,
    run_procedures,
)
from audit_core.earnings import normalize_earnings
from audit_core.models import AuditSubjectModel
from audit_core.samples import build_trading_subject
from audit_core.summary import (
    NOT_COMPUTED,
    OK,
    RISK,
    UNRELIABLE,
    WARNING,
    build_summary,
    leverage,
)

D = Decimal


def model(**over) -> AuditSubjectModel:
    """Здоровое предприятие на 2 года: актив 1120, долг 520, EBIT 220."""
    data = {
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "220"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "600"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "320"],
            "M_RETAINED": ["180", "250"],
        },
        "income": {
            "I_REVENUE": ["1800", "1980"], "I_COGS": ["1260", "1386"],
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


def summary(m: AuditSubjectModel, with_procedures: bool = True):
    result = analyze(m)
    obligations = build_obligations(m, result)
    flags = detect_flags(m, result, obligations)
    issues = check_input(m)
    earnings = normalize_earnings(m, result)
    procedures = (run_procedures(m, result, flags, issues, obligations, earnings)
                  if with_procedures else None)
    return build_summary(m, result, flags, issues, obligations, earnings, procedures)


def metric(m: AuditSubjectModel, key: str):
    found = [x for x in summary(m).metrics if x.key == key]
    assert len(found) == 1, f"ожидался один показатель {key}"
    return found[0]


# ── Н.1. Вердикт ─────────────────────────────────────────────────────────────

def test_empty_model_has_no_verdict_and_no_green_by_default():
    """Без отчётности вердикта не существует — «зелёного по умолчанию» тоже."""
    s = summary(AuditSubjectModel())
    assert s.state == "empty"
    assert "не введена" in s.detail
    assert s.metrics == []


def test_input_error_cancels_the_verdict_entirely():
    """Противоречивая отчётность отменяет вердикт, а не понижает его.

    Числа, выведенные из несходящегося баланса, нельзя ни подтвердить, ни
    опровергнуть; красить их в светофор — придавать им вес, которого нет.
    """
    s = summary(model(balance={"A_CASH": ["100", "999"]}))
    assert s.verdict == UNRELIABLE
    assert s.input_errors >= 1
    assert "не выносится" in s.detail


#: Отрицательный капитал при сходящемся балансе: долг съел вложения собственников.
#: Баланс обязан сходиться — иначе сработало бы правило ошибки ввода, и тест
#: проверял бы не тяжёлый флаг, а несведённый баланс.
NEGATIVE_EQUITY = {"P_EQUITY": ["500", "-100"], "P_LONG": ["200", "900"],
                   "M_RETAINED": ["180", "-400"]}


def test_risk_flag_forbids_a_green_verdict():
    """Один тяжёлый флаг перевешивает светофор — как NPV < 0 в первом продукте."""
    s = summary(model(balance=NEGATIVE_EQUITY))
    assert s.risk_flags >= 1
    assert s.verdict in (WARNING, RISK)
    assert s.verdict != OK
    assert "не даёт оценить состояние как благополучное" in s.detail


def test_clean_case_says_so_without_pretending_flags_exist():
    s = summary(model())
    assert s.risk_flags == 0
    assert "Красных флагов по введённой отчётности не найдено" in s.detail


def test_coverage_travels_with_the_verdict():
    """«Устойчивое состояние» при охвате 60% — это оценка шести десятых работы."""
    s = summary(model())
    assert s.coverage is not None and s.open_procedures > 0
    assert "Охват проверки" in s.detail
    assert "непроверенное не считается благополучным" in s.detail


def test_without_a_checklist_no_coverage_is_invented():
    s = summary(model(), with_procedures=False)
    assert s.coverage is None and s.open_procedures == 0
    assert "Охват проверки" not in s.detail


# ── Н.2. Долг / EBITDA ───────────────────────────────────────────────────────

def test_leverage_uses_the_normalized_measure():
    """Кратность считается к тому, что бизнес зарабатывает устойчиво."""
    m = model(earnings_adjustments=[{"label": "Разовый доход", "kind": "one_off",
                                     "amounts": ["0", "-100"]}])
    result = analyze(m)
    earnings = normalize_earnings(m, result)
    assert earnings.normalized[1] == earnings.reported[1] - 100
    assert leverage(result, earnings) == D(520) / earnings.normalized[1]


def test_leverage_names_the_measure_it_used():
    """EBIT и EBITDA различаются на всю амортизацию — подпись обязана их различать."""
    assert metric(model(), "leverage").label == "Долг / EBIT"
    with_depreciation = model(income={"M_DEPRECIATION": ["50", "60"]})
    assert metric(with_depreciation, "leverage").label == "Долг / EBITDA"


def test_leverage_is_not_computed_on_a_loss():
    """Долг к убытку не измеряется кратностью: вышло бы отрицательное «плечо»."""
    m = model(income={"I_OPEX": ["340", "3000"]})
    result = analyze(m)
    earnings = normalize_earnings(m, result)
    assert earnings.normalized[1] < 0
    assert leverage(result, earnings) is None
    item = metric(m, "leverage")
    assert item.value is None and item.tone == "neutral"
    assert "не положителен" in item.note


def test_leverage_tone_follows_the_declared_scale():
    assert metric(model(), "leverage").tone == "ok"          # 520 / 220 ≈ 2.4×
    heavy = model(balance={"P_LONG": ["200", "700"], "P_EQUITY": ["500", "100"]})
    assert metric(heavy, "leverage").tone == "risk"          # 1020 / 220 ≈ 4.6×


def test_leverage_thresholds_are_declared_as_a_convention():
    """Шкала — соглашение, а не измерение, и это сказано рядом с числом."""
    assert "соглашение методики" in metric(model(), "leverage").note


# ── Н.3. Чего на экране нет ──────────────────────────────────────────────────

def test_no_price_discount_is_produced():
    """Дисконт к цене унесли бы в переговоры — а вывести его не из чего.

    Запрошенной цены в модели нет, оценка не построена; оценённое влияние флагов
    скидкой не является.
    """
    s = summary(model())
    assert not hasattr(s, "discount")
    assert not hasattr(s, "fair_price")
    assert not any("цена" in m.label.lower() for m in s.metrics)


def test_gaps_are_listed_rather_than_left_silent():
    """Отсутствующий раздел читается как благополучие — поэтому пробелы названы."""
    s = summary(model())
    joined = " ".join(s.not_computed)
    assert "Оценка сделки" in joined
    assert "банковской выпиской" in joined
    assert "Сравнение с отраслью" in joined
    assert len(s.not_computed) == len(NOT_COMPUTED)


def test_priced_total_is_carried_with_the_count_of_unpriced():
    """Итог влияния без числа неоценённых читался бы как полная цена рисков."""
    m = model(balance=NEGATIVE_EQUITY)
    s = summary(m)
    assert s.unpriced >= 1               # у отрицательного капитала денежной меры нет
    expected = sum((f.impact for f in detect_flags(m, analyze(m)).flags
                    if f.impact is not None), D(0))
    assert s.priced_total == expected


# ── Забалансовое в шапке ─────────────────────────────────────────────────────

def test_off_balance_is_shown_apart_and_only_when_entered():
    m = model(obligations=[{"creditor": "Банк", "kind": "credit", "amount": "520"},
                           {"creditor": "Связанная", "kind": "guarantee", "amount": "180"}])
    item = metric(m, "off_balance")
    assert item.value == D(180)
    assert "не складывается" in item.note
    assert not [x for x in summary(model()).metrics if x.key == "off_balance"]


# ── Демо-дело ────────────────────────────────────────────────────────────────

def test_demo_case_gets_a_verdict_with_its_coverage():
    s = summary(build_trading_subject())
    assert s.state == "ready"
    assert s.verdict != UNRELIABLE
    assert s.coverage is not None
    assert metric(build_trading_subject(), "leverage").value is not None
