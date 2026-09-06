"""Документ заключения несёт ядро due diligence (Финанс-Аудит; SPEC, Приложение У).

Документ уходит из системы и читается без экрана. До этой фазы он рассказывал о
финансовом состоянии и молчал о находках, качестве прибыли, обязательствах, оценке и
рисках — при том, что читатель документа и есть тот, кому они адресованы. Здесь
проверяется не вёрстка, а состав и **сохранение оговорок на бумаге**: сумма оценённых
флагов не выдаётся за скидку к цене, флаг без денежной меры не превращается в ноль,
забалансовые обязательства не складываются с балансовым долгом, непосчитанное названо.

Отдельно — инвариант против расхождения: экран и документ идут из одного конвейера
(`audit_core.pipeline`), и раньше вторая копия порядка слоёв половину из них теряла.
"""
from __future__ import annotations

import re
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from app.audit_docgen import build_audit_docx
from audit_core import review_case
from audit_core.models import AuditSubjectModel
from audit_core.pipeline import NOT_REQUESTED

D = Decimal

ASSUMPTIONS = {
    "enabled": True, "horizon_years": 5, "wacc": "0.20", "terminal_growth": "0.03",
    "tax_rate": "0.20", "growth": ["0.10", "0.08", "0.06", "0.05", "0.04"],
    "capex": ["70", "70", "70", "70", "70"],
    "nwc_change": ["20", "15", "12", "10", "10"],
}


def model(**over) -> AuditSubjectModel:
    """Дело на 2 года: прибыль есть, долг 520, деньги 130 — база для всех слоёв."""
    data: dict = {
        "name": "ООО «Цель»",
        "industry": "Перевозки",
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
    }
    for key, value in over.items():
        if key in ("balance", "income") and isinstance(value, dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def text_of(m: AuditSubjectModel) -> str:
    """Весь текст документа: абзацы и ячейки таблиц (в XML они лежат вперемешку)."""
    content = build_audit_docx(review_case(m), subject_name=m.name)
    assert content[:2] == b"PK"                      # валидный zip (docx)
    xml = ZipFile(BytesIO(content)).read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


def test_due_diligence_core_reaches_the_paper():
    """Разделы ядра проверки есть в документе — все, а не только состояние."""
    text = text_of(model(valuation=ASSUMPTIONS))
    for heading in ("Вердикт по делу", "Реестр красных флагов", "Качество прибыли",
                    "Обязательства и залоги", "Оценка стоимости", "Риски оценки"):
        assert heading in text, heading


def test_verdict_carries_coverage_and_open_procedures():
    """Вердикт без охвата читается как полная проверка."""
    text = text_of(model())
    assert "охват проверки" in text
    assert "незакрытых процедур" in text


def test_priced_flags_are_not_called_a_discount():
    """Сумма оценённых находок и торг — разные величины (Прил. Н.3)."""
    text = text_of(model(income={"I_OTHER": ["0", "300"]}))
    assert "оценённое влияние флагов" in text.lower()
    assert "Это не скидка к цене" in text


def test_flag_without_a_price_is_not_zero_roubles():
    """У флага без денежной меры её нет — это не «ноль рублей»."""
    # Отрицательный капитал денежной меры не имеет: флаг есть, суммы у него нет.
    m = model(balance={"P_EQUITY": ["-100", "-200"], "P_SHORT": ["900", "1120"]})
    text = text_of(m)
    review = review_case(m)
    assert any(f.impact is None for f in review.flags.flags)
    assert "меры нет" in text


def test_off_balance_is_never_added_to_debt():
    """Забалансовое и балансовый долг — две величины, и их сложение запрещено (Л.1)."""
    text = text_of(model(obligations=[
        {"creditor": "Банк", "kind": "loan", "amount": "520", "maturity_year": 2029},
        {"creditor": "Дочка", "kind": "guarantee", "amount": "300"},
    ]))
    assert "Забалансовые обязательства" in text
    assert "с балансовым долгом она не складывается" in text


def test_valuation_absence_names_its_blockers():
    """Оценки нет — печатаются препятствия, а не нули."""
    text = text_of(model())                           # допущения не введены
    assert "Оценка не посчитана" in text
    assert "Не посчитано:" in text


def test_valuation_prints_the_bridge_and_the_multiple():
    text = text_of(model(valuation=ASSUMPTIONS))
    assert "Мост от стоимости бизнеса к цене доли" in text
    assert "Стоимость бизнеса (EV)" in text
    assert "подразумеваемый мультипликатор" in text


def test_monte_carlo_prints_the_condition_of_reading_it():
    """Распределения задаёт аналитик — на бумаге это условие, а не сноска (Прил. Р)."""
    m = model(valuation=ASSUMPTIONS, risk={
        "iterations": 200, "seed": 7,
        "uncertain": [{"param": "growth",
                       "distribution": {"kind": "uniform", "low": "0.8", "high": "1.2"}}],
    })
    text = text_of(m)
    assert "Монте-Карло" in text
    assert "настолько хороши, насколько верны" in text


def test_plan_fact_is_printed_only_when_a_plan_was_entered():
    """Раздел «сравнивать не с чем» на бумаге занимает место и ничего не сообщает."""
    assert "План-факт после сделки" not in text_of(model())
    # У плана-факта должен быть хотя бы один флаг: подписи по источнику стоят
    # рядом с числами, а не сами по себе.
    with_plan = model(seller_plan={"I_REVENUE": ["1900", "2100"]},
                      income={"I_OTHER": ["0", "300"]})
    text = text_of(with_plan)
    assert "План-факт после сделки" in text
    # Обе половины подписаны по источнику (Прил. Т.4).
    assert "посчитано платформой" in text and "введены аналитиком" in text


def test_the_document_still_carries_statements_and_diagnostics():
    """Ядро проверки добавлено, состояние не вытеснено: оба слоя на бумаге."""
    text = text_of(model())
    for heading in ("Баланс (аналитическая форма)", "Отчёт о финансовых результатах",
                    "Диагностика финансового состояния", "Чек-лист процедур"):
        assert heading in text, heading


def test_screen_and_document_come_from_one_pipeline():
    """Главный инвариант: что видно на экране, то и в документе.

    Раньше конвейер был записан дважды, и в копии для документа не было ни оценки, ни
    рисков, ни сводки. Расходятся такие копии молча — поэтому сверяется не наличие
    раздела, а совпадение содержимого с тем, что отдаёт разбор.
    """
    m = model(valuation=ASSUMPTIONS, income={"I_OTHER": ["0", "300"]})
    review = review_case(m)
    text = text_of(m)
    assert review.flags.flags, "нужен хотя бы один флаг, иначе тест ничего не стережёт"
    for flag in review.flags.flags:
        assert flag.title in text, flag.title
    assert review.summary.headline in text


def test_shallow_review_skips_only_the_stochastic_layer():
    """`deep=False` убирает риски и ничего больше — числа дела те же (Прил. У.1).

    Сравнение дел идёт этим режимом: если он менял бы вердикт или оценку, колонки
    сравнения расходились бы с карточкой дела, и заметить это было бы нечем.
    """
    m = model(valuation=ASSUMPTIONS, income={"I_OTHER": ["0", "300"]})
    deep, shallow = review_case(m), review_case(m, deep=False)
    assert shallow.summary == deep.summary
    assert shallow.valuation == deep.valuation
    assert shallow.procedures == deep.procedures
    assert shallow.earnings == deep.earnings
    assert [f.code for f in shallow.flags.flags] == [f.code for f in deep.flags.flags]


def test_skipped_risk_names_its_reason_instead_of_looking_computed():
    """«Не считали» и «посчитали, не вышло» — разные вещи, и это видно в объекте."""
    shallow = review_case(model(valuation=ASSUMPTIONS), deep=False)
    assert shallow.risk.available is False
    assert shallow.risk.blockers == [NOT_REQUESTED]
