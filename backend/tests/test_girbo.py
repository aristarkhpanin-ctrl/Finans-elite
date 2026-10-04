"""Отчётность по ИНН из ГИР БО (пакет L, L3).

Фикстуры — **настоящие ответы ресурса ФНС** (публичная бухгалтерская отчётность), урезанные
до полей, которые читает импорт: крупная розничная сеть (полная форма 0710099) и
крестьянское хозяйство (упрощённая 0710096). Сеть в тестах не участвует: дорога туда
подменяется, разбор и сопоставление проверяются на том, что ресурс действительно отдаёт.

Главное, что стережёт файл: **подытоги отчётности сохраняются** — прибыль от продаж, до
налогообложения и чистая выходят ровно такими, как в форме, а актив равен пассиву; и
каждое отнесение строк названо, а не спрятано.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app import girbo
from audit_core import analyze
from audit_core.flags import detect_flags
from audit_core.girbo import (
    THOUSAND,
    GirboYear,
    build_import,
    clean,
    collect_years,
    to_analytic,
)
from audit_core.models import AuditPeriod, AuditSubjectModel, RegistrySnapshot
from audit_core.requisites import REGISTRY_NOT_EGRUL, build_requisites

FIX = Path(__file__).parent / "fixtures" / "girbo"
TODAY = date(2026, 10, 4)


def _load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def tander():
    return build_import(_load("tander_org.json"), _load("tander_bfo.json"), today=TODAY)


@pytest.fixture
def farm():
    return build_import(_load("farm_org.json"), _load("farm_bfo.json"), today=TODAY)


def _rsbu(reports, period, form, column="current"):
    report = next(r for r in reports if r["period"] == period)
    corr = report["typeCorrections"][0]["correction"]
    return {k[len(column):]: Decimal(str(v)) for k, v in corr[form].items()
            if k.startswith(column) and k[len(column):].isdigit()}


def test_subtotals_of_the_form_survive_the_mapping(tander):
    """Прибыль от продаж (2200), до налогообложения (2300) и чистая (2400) — ровно как в
    форме, в рублях; актив равен пассиву и итогу баланса (1600)."""
    reports = _load("tander_bfo.json")
    for t, period in enumerate(tander.periods):
        bal, inc = _rsbu(reports, period, "balance"), _rsbu(reports, period, "financialResult")
        i = {k: v[t] for k, v in tander.income.items()}
        b = {k: v[t] for k, v in tander.balance.items()}
        gross = i["I_REVENUE"] - i["I_COGS"]
        ebit = gross - i["I_OPEX"]
        ebt = ebit - i["I_INTEREST"] + i["I_OTHER"]
        net = ebt - i["I_TAX"]
        assert ebit == inc["2200"] * THOUSAND, period
        assert ebt == inc["2300"] * THOUSAND, period
        assert net == inc["2400"] * THOUSAND, period
        assets = b["A_FIXED"] + b["A_INVENTORY"] + b["A_RECEIVABLE"] + b["A_CASH"]
        liabilities = b["P_EQUITY"] + b["P_LONG"] + b["P_SHORT"]
        assert assets == liabilities == bal["1600"] * THOUSAND, period
        assert b["M_RETAINED"] == bal["1370"] * THOUSAND


def test_the_line_mapping_is_the_named_one(tander):
    """1240 — к деньгам, запасы — остаток оборотных: 1210, 1220, 1260 и строка без своей
    статьи. На настоящей отчётности такая нашлась — 1215; потерять её значило бы, что
    актив перестал бы сходиться с итогом баланса."""
    bal = _rsbu(_load("tander_bfo.json"), "2025", "balance")
    t = tander.periods.index("2025")
    assert tander.balance["A_CASH"][t] == (bal["1240"] + bal["1250"]) * THOUSAND
    assert tander.balance["A_RECEIVABLE"][t] == bal["1230"] * THOUSAND
    inventory = bal["1210"] + bal["1215"] + bal["1220"] + bal["1260"]
    assert tander.balance["A_INVENTORY"][t] == inventory * THOUSAND
    assert any("1215" in n and "1220" in n and "1260" in n and "1240" in n
               for n in tander.notes)


def test_the_import_balances_in_the_case_analysis(tander):
    model = AuditSubjectModel(
        periods=[AuditPeriod(label=p, kind="year") for p in tander.periods],
        balance={k: list(v) for k, v in tander.balance.items()},
        income={k: list(v) for k, v in tander.income.items()})
    assert model.is_balanced()
    result = analyze(model)
    net = next(ln for ln in result.income if ln.code == "I_NET").values
    assert net[-1] == _rsbu(_load("tander_bfo.json"), "2025", "financialResult")["2400"] * 1000


def test_years_come_from_own_reports_and_the_limit_is_named(tander):
    assert tander.periods == ["2021", "2022", "2023", "2024", "2025"]
    assert tander.sources[-1] == "отчётность за 2025 год"
    assert any("последние 5 лет" in n for n in tander.notes)
    years, notes = collect_years(_load("tander_bfo.json"), limit=10)
    assert [y.period for y in years][0] == "2020"
    assert any(n.startswith("2020 год — из сравнительных данных") for n in notes)


def test_a_restated_year_is_named_and_the_own_report_wins():
    reports = _load("farm_bfo.json")
    later = next(r for r in reports if r["period"] == "2025")
    later["typeCorrections"][0]["correction"]["financialResult"]["previous2110"] = 999.0
    years, notes = collect_years(reports)
    assert next(y for y in years if y.period == "2024").income["2110"] == Decimal("200")
    assert any("Данные 2024 года в отчётности за 2025 год пересчитаны" in n for n in notes)


def test_the_simplified_form_says_what_it_cannot_split(farm):
    assert farm.forms == ["упрощённая"] * 5
    assert farm.income["I_OPEX"] == [Decimal(0)] * 5
    assert any("Упрощённая форма" in n and "2120" in n for n in farm.notes)
    assert any("1370" in n and "Альтмана" in n for n in farm.notes)
    t = farm.periods.index("2025")
    net = (farm.income["I_REVENUE"][t] - farm.income["I_COGS"][t] - farm.income["I_OPEX"][t]
           - farm.income["I_INTEREST"][t] + farm.income["I_OTHER"][t] - farm.income["I_TAX"][t])
    assert net == Decimal("124") * THOUSAND


def test_an_unbalanced_filing_is_named_not_hidden():
    year = GirboYear("2024", "0710099", "отчётность за 2024 год",
                     balance={"1100": Decimal(10), "1200": Decimal(5), "1600": Decimal(20),
                              "1300": Decimal(15), "1700": Decimal(20)},
                     income={"2110": Decimal(1), "2400": Decimal(1)})
    _, _, notes = to_analytic(year)
    assert any("актива" in n and "не сходится" in n for n in notes)
    assert any("пассива" in n and "не сходится" in n for n in notes)


def test_the_registry_snapshot_is_cleaned(tander):
    reg = tander.registry
    assert reg["inn"] == "2310031475" and reg["ogrn"] == "1022301598549"
    assert reg["status_code"] == "ACTIVE" and reg["fetched_on"] == "2026-10-04"
    assert reg["okved"].startswith("47.11 — ")
    assert clean("<strong>2310031475</strong>") == "2310031475"


# --- Дорога к ресурсу: отказы словами, без сети ---

def _fake_get(org="tander", *, search=None):
    def get(url: str):
        if "/advanced-search/" in url:
            return search if search is not None else _load(f"{org}_search.json")
        if url.endswith("/bfo/"):
            return _load(f"{org}_bfo.json")
        return _load(f"{org}_org.json")
    return get


def test_fetch_finds_by_exact_inn():
    org, reports, notes = girbo.fetch("2310031475", get=_fake_get())
    assert org["inn"] == "2310031475" and len(reports) == 5 and notes == []


def test_a_mistyped_inn_never_leaves_the_server():
    def explode(url):
        raise AssertionError("запрос ушёл с ИНН, не прошедшим контрольную цифру")
    with pytest.raises(girbo.GirboError) as exc:
        girbo.fetch("2310031476", get=explode)
    assert exc.value.status == 422 and "контрольной цифры" in exc.value.detail


def test_not_found_and_unavailable_are_named():
    with pytest.raises(girbo.GirboError) as exc:
        girbo.fetch("2310031475", get=_fake_get(search={"content": []}))
    assert exc.value.status == 404 and "ограничен" in exc.value.detail

    def down(url):
        raise OSError("connection reset")
    with pytest.raises(girbo.GirboError) as exc:
        girbo.fetch("2310031475", get=down)
    assert exc.value.status == 503 and "Excel" in exc.value.detail


def test_the_switch_turns_it_off(monkeypatch):
    monkeypatch.setenv("GIRBO_ENABLED", "0")
    with pytest.raises(girbo.GirboError) as exc:
        girbo.fetch("2310031475", get=_fake_get())
    assert exc.value.status == 503 and "GIRBO_ENABLED=0" in exc.value.detail


def test_the_preview_route(client, register, monkeypatch):
    monkeypatch.setattr(girbo, "_get", _fake_get())
    headers = register()
    client.get("/api/v1/organizations", headers=headers)
    r = client.get("/api/v1/audit/girbo/2310031475", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["periods"][-1] == "2025" and body["status_label"] == "действующая"
    assert body["registry"]["inn"] == "2310031475"
    assert Decimal(body["income"]["I_REVENUE"][-1]) == Decimal("3050026081") * 1000
    bad = client.get("/api/v1/audit/girbo/123", headers=headers)
    assert bad.status_code == 422


# --- Что снимок реестра меняет в деле ---

def _case(status="ACTIVE", **requisites) -> AuditSubjectModel:
    model = AuditSubjectModel(periods=[AuditPeriod(label="2025", kind="year")],
                              balance={"A_CASH": [Decimal(1)], "P_EQUITY": [Decimal(1)]},
                              income={"I_REVENUE": [Decimal(1)]})
    model.registry = RegistrySnapshot(inn="2310031475", ogrn="1022301598549",
                                      full_name='АКЦИОНЕРНОЕ ОБЩЕСТВО "ТАНДЕР"',
                                      address="350002, КРАСНОДАР", status_code=status,
                                      status_date=date(2026, 3, 31), fetched_on=TODAY)
    for key, value in requisites.items():
        setattr(model.report, key, value)
    return model


def test_an_inactive_organization_is_a_risk_flag():
    model = _case("INACTIVE")
    flags = detect_flags(model, analyze(model)).flags
    [flag] = [f for f in flags if f.code == "registry_inactive"]
    assert flag.severity == "risk" and "недействующая" in flag.detail
    assert "31.03.2026" in flag.detail and "04.10.2026" in flag.detail
    assert flag.impact is None                      # не сумма, а вопрос о предмете сделки
    # Тишина: действующая и без снимка.
    active = _case("ACTIVE")
    assert not [f for f in detect_flags(active, analyze(active)).flags
                if f.code == "registry_inactive"]
    plain = _case()
    plain.registry = None
    assert not [f for f in detect_flags(plain, analyze(plain)).flags
                if f.code == "registry_inactive"]


def test_requisites_are_reconciled_with_the_snapshot_and_named():
    model = _case(subject_inn="2310031475", subject_ogrn="1022301598549",
                  subject_full_name="АО «Тандер»")
    view = build_requisites(model)
    assert any("Совпадают со сведениями ГИР БО на 04.10.2026: ИНН, ОГРН" in c
               for c in view.caveats)
    assert any("Наименование в деле («АО «Тандер»») расходится" in c for c in view.caveats)
    assert REGISTRY_NOT_EGRUL in view.not_computed
    assert not any(item.startswith("Сверка реквизитов с ЕГРЮЛ") for item in view.not_computed)
    # Без снимка — по-прежнему «не сверяются».
    plain = _case(subject_inn="2310031475")
    plain.registry = None
    assert any(item.startswith("Сверка реквизитов с ЕГРЮЛ")
               for item in build_requisites(plain).not_computed)


def test_the_document_names_the_source_before_the_numbers(tander):
    """DOCX: раздел «Источник отчётности» — откуда числа и на какую дату, до таблиц."""
    from io import BytesIO

    from docx import Document

    from app.audit_docgen import build_audit_docx
    from audit_core.pipeline import review_case

    model = AuditSubjectModel(
        periods=[AuditPeriod(label=p, kind="year") for p in tander.periods],
        balance={k: list(v) for k, v in tander.balance.items()},
        income={k: list(v) for k, v in tander.income.items()},
        registry=RegistrySnapshot(**tander.registry))
    doc = Document(BytesIO(build_audit_docx(review_case(model, deep=False),
                                            subject_name="Цель", today=TODAY)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Источник отчётности" in text
    assert "загружена из ГИР БО (ресурс бухгалтерской отчётности ФНС) на 04.10.2026" in text
    assert text.index("Источник отчётности") < text.index("Баланс (аналитическая форма)")
    assert "в тысячах рублей" in text
