"""Бизнес-план из дела «Аудита» (пакет G, G14): черновик модели «Элиты».

Проверяются обещания моста:

* стартовый баланс — из **последнего** периода дела и сходится (модель считается);
* **неразделимое не угадывается**, а названо: краткосрочные обязательства — займами (B22),
  запасы — одной строкой в сырьё, внеоборотные активы — одной строкой ОС, капитал делится
  только если в деле выделена нераспределённая прибыль;
* дата старта — после окончания периода, и только если подпись читается однозначно;
* несходящийся баланс и пустое дело — **отказ с причиной**, а не черновик;
* единицы измерения у дела нет — её называет человек (рубли / тысячи), и выбор назван;
* переоценки дела применяются и названы;
* происхождение — разделом бизнес-плана, чтобы уехало и в DOCX;
* маршрут только читает: ничего не создаёт и не пишет в журнал.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.audit_bridge import (
    PROVENANCE_TITLE,
    BridgeError,
    business_plan_draft,
    start_after,
)
from audit_core.models import AuditPeriod, AuditSubjectModel, Revaluation
from calc_core import run

D = Decimal
START = date(2026, 10, 1)


def _case(**balance: list[int]) -> AuditSubjectModel:
    rows = {"A_FIXED": [400, 500], "A_INVENTORY": [100, 150], "A_RECEIVABLE": [80, 90],
            "A_CASH": [20, 60], "P_EQUITY": [300, 380], "P_LONG": [200, 250],
            "P_SHORT": [100, 170], **balance}
    return AuditSubjectModel(
        name="ООО «Пример»",
        periods=[AuditPeriod(label="2024", kind="year"), AuditPeriod(label="2025", kind="year")],
        balance={code: [D(v) for v in values] for code, values in rows.items()},
    )


def _draft(case: AuditSubjectModel, **kw):
    return business_plan_draft("ООО «Пример»", case, default_start=START, **kw)


# --- Перенос ---

def test_the_opening_balance_comes_from_the_last_period_and_converges():
    draft = _draft(_case())
    sb = draft.model.company.starting_balance
    assert (sb.cash, sb.receivables, sb.raw_materials, sb.fixed_assets_net) == \
        (D(60), D(90), D(150), D(500))                     # последний период, не первый
    assert (sb.debt, sb.short_term_debt) == (D(250), D(170))
    assert sb.assets() == sb.liabilities_equity()
    result = run(draft.model)                              # модель считается
    assert abs(result.balance["B20"][0] - result.balance["B34"][0]) < D("0.01")


def test_what_cannot_be_split_is_named_not_guessed():
    notes = " ".join(_draft(_case()).notes)
    assert "краткосрочные займы (B22)" in notes and "не делит их на займы и кредиторку" in notes
    assert "одной строкой в сырьё" in notes
    assert "без амортизации" in notes                     # ОС без детализации не стареют
    assert "Не перенесено: выручка и расходы" in notes


def test_equity_is_split_only_where_the_case_names_retained_earnings():
    with_retained = _draft(_case(M_RETAINED=[50, 120])).model.company.starting_balance
    assert (with_retained.retained_earnings, with_retained.paid_in_capital) == (D(120), D(260))

    plain = _draft(_case())
    assert plain.model.company.starting_balance.paid_in_capital == D(380)
    assert "не выделена" in " ".join(plain.notes)

    # Отрицательный капитал — накопленный убыток, а не отрицательный уставный капитал.
    negative = _draft(_case(P_EQUITY=[-50, -50], P_LONG=[200, 250], P_SHORT=[400, 600]))
    sb = negative.model.company.starting_balance
    assert sb.retained_earnings == D(-50) and sb.paid_in_capital == 0
    assert sb.assets() == sb.liabilities_equity()


# --- Дата старта ---

@pytest.mark.parametrize("label, kind, expected", [
    ("2025", "year", date(2026, 1, 1)),
    ("2025 Q2", "quarter", date(2025, 7, 1)),
    ("2024 q1", "quarter", date(2024, 4, 1)),                 # «4» перед « q» — год
    ("2 кв. 2025", "quarter", date(2025, 7, 1)),
    ("дек 2025", "month", date(2026, 1, 1)),
    ("мар 2025", "month", date(2025, 4, 1)),                   # «ма» — не май
    ("май 2025", "month", date(2025, 6, 1)),
    ("2025-11", "month", date(2025, 12, 1)),
    ("2024–2025", "year", None),                               # два года — не угадываем
    ("Итого", "year", None),
    ("2025", "quarter", None),
])
def test_the_start_follows_the_period_only_when_the_label_is_unambiguous(label, kind, expected):
    assert start_after(label, kind) == expected


def test_an_unreadable_label_leaves_the_date_to_the_person():
    case = _case()
    case.periods[-1] = AuditPeriod(label="Итого", kind="year")
    draft = _draft(case)
    assert draft.start_date is None and draft.model.header.start_date == START
    assert "не угадана" in " ".join(draft.notes)


# --- Отказы ---

def test_an_unbalanced_last_period_is_refused_with_the_gap():
    with pytest.raises(BridgeError, match="разница"):
        _draft(_case(A_CASH=[20, 61]))


def test_an_empty_case_is_refused():
    with pytest.raises(BridgeError, match="нет периодов"):
        _draft(AuditSubjectModel(name="Пусто"))
    empty_balance = AuditSubjectModel(periods=[AuditPeriod(label="2025")])
    with pytest.raises(BridgeError, match="не введён"):
        _draft(empty_balance)


# --- Единицы, переоценки, валюта ---

def test_the_unit_is_chosen_by_the_person_and_named():
    thousands = _draft(_case(), scale=1000)
    assert thousands.model.company.starting_balance.cash == D(60_000)
    assert "в тысячах рублей" in thousands.notes[0]
    assert "в рублях" in _draft(_case()).notes[0]
    with pytest.raises(BridgeError):
        _draft(_case(), scale=100)


def test_revaluations_of_the_case_are_applied_and_named():
    case = _case()
    case.revaluations = [Revaluation(code="A_RECEIVABLE", label="Безнадёжный долг",
                                     amounts=[D(0), D(-30)])]
    draft = _draft(case)
    sb = draft.model.company.starting_balance
    assert sb.receivables == D(60)                          # 90 − 30
    assert sb.assets() == sb.liabilities_equity()           # корреспонденция в капитале
    assert draft.revaluations and "переоценки" in " ".join(draft.notes)


def test_a_foreign_currency_case_is_named_not_converted():
    case = _case()
    case.currency = "USD"
    assert "без пересчёта" in " ".join(_draft(case).notes)


def test_provenance_rides_in_the_business_plan_and_the_document():
    """Раздел плана, а не поле рядом: документ несёт его сам — банк, читающий бизнес-план,
    узнаёт, откуда взялся стартовый баланс и что в нём отнесено условно."""
    from io import BytesIO

    from docx import Document

    from app.docgen import build_business_plan_docx
    from calc_core.review import ReviewContext, run_review
    from calc_core.review.opinion import build_opinion

    model = _draft(_case()).model
    assert [s.title for s in model.business_plan] == [PROVENANCE_TITLE]
    assert "ООО «Пример»" in model.business_plan[0].text
    result = run(model)
    opinion = build_opinion(run_review(ReviewContext(model=model, result=result)), result)
    doc = Document(BytesIO(build_business_plan_docx(model, result, opinion,
                                                    project_name="План", today=START)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert PROVENANCE_TITLE in text and "краткосрочные займы (B22)" in text


# --- Маршрут ---

def _subject(client, headers, balance: dict | None = None) -> str:
    model = {"periods": [{"label": "2025", "kind": "year"}],
             "balance": balance or {"A_CASH": ["300"], "A_FIXED": ["700"],
                                    "P_EQUITY": ["600"], "P_SHORT": ["400"]}}
    return client.post("/api/v1/audit/subjects", json={"name": "ООО «Цель»", "model": model},
                       headers=headers).json()["id"]


def test_the_route_returns_a_draft_that_becomes_a_calculable_project(client, auth_headers):
    sid = _subject(client, auth_headers)
    before = client.get("/api/v1/projects", headers=auth_headers).json()
    r = client.get(f"/api/v1/audit/subjects/{sid}/business-plan-draft?months=24&scale=1000",
                   headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_date"] == "2026-01-01" and body["notes"]
    assert body["model"]["header"]["duration_months"] == 24
    assert body["model"]["company"]["starting_balance"]["short_term_debt"] == "400000"
    # Черновик не сохранён: проектов столько же.
    assert client.get("/api/v1/projects", headers=auth_headers).json() == before

    created = client.post("/api/v1/projects", headers=auth_headers,
                          json={"name": "План", "model": body["model"]})
    assert created.status_code in (200, 201), created.text
    calc = client.post(f"/api/v1/projects/{created.json()['id']}/calculate",
                       headers=auth_headers)
    assert calc.status_code == 200, calc.text


def test_the_route_refuses_with_the_reason(client, auth_headers):
    sid = _subject(client, auth_headers, {"A_CASH": ["300"], "P_EQUITY": ["200"]})
    r = client.get(f"/api/v1/audit/subjects/{sid}/business-plan-draft", headers=auth_headers)
    assert r.status_code == 422 and "разница" in r.json()["detail"]
    assert client.get("/api/v1/audit/subjects/nope/business-plan-draft",
                      headers=auth_headers).status_code == 404
