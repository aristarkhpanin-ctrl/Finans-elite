"""Переоценка статей и основа отчётности (Финанс-Аудит, v2).

Главное требование к переоценке: у каждой поправки есть корреспонденция в капитале,
поэтому «актив = пассив» сохраняется, а сами поправки не бывают молчаливыми.
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, consolidate_subjects
from audit_core.models import AuditPeriod, AuditSubjectModel, Revaluation
from audit_core.revaluation import apply_revaluations

D = Decimal


def _model(**kw) -> AuditSubjectModel:
    """Сходящийся субъект: актив 200 = пассив 200 (капитал 120)."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label="2024", kind="year")],
        balance={
            "A_FIXED": [D(100)], "A_INVENTORY": [D(30)],
            "A_RECEIVABLE": [D(40)], "A_CASH": [D(30)],
            "P_EQUITY": [D(120)], "P_LONG": [D(30)], "P_SHORT": [D(50)],
        },
        income={"I_REVENUE": [D(500)], "I_COGS": [D(300)], "I_OPEX": [D(80)],
                "I_INTEREST": [D(10)], "I_OTHER": [D(0)], "I_TAX": [D(22)]},
        **kw,
    )


def _line(r, code):
    for group in (r.balance, r.income):
        for ln in group:
            if ln.code == code:
                return ln.values
    raise AssertionError(code)


def test_no_revaluations_is_inert():
    """Без переоценок модель возвращается тем же объектом — ничего не пересчитывается."""
    m = _model()
    out, notes = apply_revaluations(m)
    assert out is m and notes == []
    assert analyze(m).revalued is False


def test_empty_amounts_are_inert():
    """Переоценка с нулевыми суммами не считается переоценкой (флаг не поднимается)."""
    m = _model(revaluations=[Revaluation(code="A_FIXED", amounts=[D(0)])])
    out, notes = apply_revaluations(m)
    assert out is m and notes == []


def test_asset_revaluation_credits_equity():
    """Дооценка актива увеличивает капитал на ту же сумму — баланс сходится."""
    m = _model(revaluations=[Revaluation(code="A_FIXED", label="дооценка ОС",
                                         amounts=[D(50)])])
    r = analyze(m)
    assert _line(r, "A_FIXED") == [D(150)]
    assert _line(r, "P_EQUITY") == [D(170)]          # 120 + 50
    assert _line(r, "A_TOTAL") == [D(250)] == _line(r, "P_TOTAL")
    assert r.balanced is True and r.revalued is True


def test_asset_writedown_debits_equity():
    """Уценка (отрицательная поправка) уменьшает и актив, и капитал."""
    m = _model(revaluations=[Revaluation(code="A_RECEIVABLE", label="безнадёжная дебиторка",
                                         amounts=[D(-25)])])
    r = analyze(m)
    assert _line(r, "A_RECEIVABLE") == [D(15)]
    assert _line(r, "P_EQUITY") == [D(95)]
    assert r.balanced is True


def test_liability_revaluation_has_opposite_sign():
    """Признание обязательства уменьшает капитал (знак обратный активу)."""
    m = _model(revaluations=[Revaluation(code="P_SHORT", label="непризнанный долг",
                                         amounts=[D(40)])])
    r = analyze(m)
    assert _line(r, "P_SHORT") == [D(90)]
    assert _line(r, "P_EQUITY") == [D(80)]           # 120 − 40
    assert _line(r, "P_TOTAL") == [D(200)] == _line(r, "A_TOTAL")
    assert r.balanced is True


def test_revaluation_is_never_silent():
    """Каждая применённая поправка названа в оговорках — числа уже не «как в отчётности»."""
    m = _model(revaluations=[Revaluation(code="A_INVENTORY", label="неликвиды",
                                         amounts=[D(-10)])])
    r = analyze(m)
    assert r.revalued is True
    assert any("Переоценка" in w and "неликвиды" in w for w in r.warnings)
    # оговорка о переоценке идёт раньше прочих предупреждений анализа
    assert "Переоценка" in r.warnings[0]


def test_equity_cannot_be_revalued():
    """Капитал — корреспонденция любой поправки, переоценивать его напрямую не к чему."""
    m = _model(revaluations=[Revaluation(code="P_EQUITY", label="прочее", amounts=[D(10)])])
    r = analyze(m)
    assert _line(r, "P_EQUITY") == [D(120)]          # не изменился
    assert any("не применена" in w and "капитал" in w.lower() for w in r.warnings)


def test_unknown_code_reported_not_ignored():
    """Неизвестная статья не переоценивается, но и не проглатывается молча."""
    m = _model(revaluations=[Revaluation(code="A_NOPE", amounts=[D(10)])])
    r = analyze(m)
    assert r.balanced is True
    assert any("не применена" in w and "A_NOPE" in w for w in r.warnings)


def test_revaluation_does_not_fix_unbalanced_input():
    """Разрыв исходного баланса переоценка не «чинит»: он остаётся прежним."""
    m = _model(revaluations=[Revaluation(code="A_FIXED", amounts=[D(50)])])
    m.balance["P_EQUITY"] = [D(200)]                 # пассив 280 против актива 200
    plain = analyze(_model_with_equity(D(200)))
    r = analyze(m)
    assert r.balance_gap == plain.balance_gap        # −80 и там, и там
    assert r.balanced is False


def _model_with_equity(equity: Decimal) -> AuditSubjectModel:
    m = _model()
    m.balance["P_EQUITY"] = [equity]
    return m


def test_revaluation_flows_into_ratios_and_diagnostics():
    """Переоценка меняет весь анализ, а не только строку баланса."""
    plain = analyze(_model())
    cut = analyze(_model(revaluations=[Revaluation(code="A_CASH", amounts=[D(-20)])]))
    cur_plain = plain.ratios["liquidity"]["Коэффициент текущей ликвидности"][0]
    cur_cut = cut.ratios["liquidity"]["Коэффициент текущей ликвидности"][0]
    assert cur_cut < cur_plain                       # ликвидность упала вместе с деньгами
    assert cut.ratios["gearing"]["Коэффициент автономии"][0] < \
        plain.ratios["gearing"]["Коэффициент автономии"][0]


def test_multiple_revaluations_accumulate_in_equity():
    """Несколько поправок складываются в капитале; инвариант держится."""
    m = _model(revaluations=[
        Revaluation(code="A_FIXED", amounts=[D(50)]),
        Revaluation(code="A_INVENTORY", amounts=[D(-10)]),
        Revaluation(code="P_LONG", amounts=[D(15)]),
    ])
    r = analyze(m)
    assert _line(r, "P_EQUITY") == [D(145)]          # 120 + 50 − 10 − 15
    assert _line(r, "A_TOTAL") == _line(r, "P_TOTAL")
    assert r.balanced is True


def test_source_model_not_mutated():
    """Переоценка не портит исходную модель — она остаётся учётной отчётностью."""
    m = _model(revaluations=[Revaluation(code="A_FIXED", amounts=[D(50)])])
    analyze(m)
    assert m.balance["A_FIXED"] == [D(100)] and m.balance["P_EQUITY"] == [D(120)]


# --- Основа отчётности ---

def test_reporting_standard_defaults_to_rsbu():
    assert _model().reporting_standard == "rsbu"


def test_group_of_mixed_standards_warns():
    """Смешение основ в своде не проходит молча: числа строго не сопоставимы."""
    a = _model(reporting_standard="rsbu")
    b = _model(reporting_standard="ifrs")
    c = consolidate_subjects([("A", a), ("B", b)])
    assert any("по разным основам" in w for w in c.warnings)
    # группе не приписывается ни один из стандартов участников
    assert c.model.reporting_standard == "management"


def test_group_of_same_standard_is_quiet():
    """Одна основа у всех — оговорки нет, основа переносится на группу."""
    c = consolidate_subjects([("A", _model(reporting_standard="ifrs")),
                              ("B", _model(reporting_standard="ifrs"))])
    assert not any("по разным основам" in w for w in c.warnings)
    assert c.model.reporting_standard == "ifrs"


def test_member_revaluation_applied_before_consolidation():
    """Свод считается по переоценённым данным участников, а не по учётным."""
    a = _model(revaluations=[Revaluation(code="A_FIXED", label="дооценка", amounts=[D(50)])])
    b = _model()
    c = consolidate_subjects([("A", a), ("B", b)])
    r = analyze(c.model)
    assert _line(r, "A_FIXED") == [D(250)]           # 150 + 100
    assert _line(r, "A_TOTAL") == _line(r, "P_TOTAL")
    assert any("переоценённые данные участников" in w for w in c.warnings)
    assert any("дооценка" in w for w in c.warnings)


def test_group_without_revaluations_is_quiet():
    """Без переоценок участников оговорки о них не появляется."""
    c = consolidate_subjects([("A", _model()), ("B", _model())])
    assert not any("переоценённые данные" in w for w in c.warnings)


# --- API ---

def test_revaluation_through_api(client, auth_headers):
    """Переоценка проходит через сохранение модели и видна в ответе анализа."""
    model = {
        "periods": [{"label": "2024", "kind": "year"}],
        "balance": {"A_FIXED": ["100"], "A_CASH": ["100"], "P_EQUITY": ["200"]},
        "income": {"I_REVENUE": ["500"], "I_COGS": ["300"], "I_OPEX": ["100"],
                   "I_INTEREST": ["0"], "I_OTHER": ["0"], "I_TAX": ["20"]},
        "reporting_standard": "ifrs",
        "revaluations": [{"code": "A_FIXED", "label": "дооценка ОС", "amounts": ["50"]}],
    }
    sid = client.post("/api/v1/audit/subjects", json={"name": "ПАО", "model": model},
                      headers=auth_headers).json()["id"]
    body = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()

    assert body["revalued"] is True
    fixed = next(ln for ln in body["balance"] if ln["code"] == "A_FIXED")
    equity = next(ln for ln in body["balance"] if ln["code"] == "P_EQUITY")
    assert str(fixed["values"][0]) == "150" and str(equity["values"][0]) == "250"
    assert body["balanced"] is True
    assert any("дооценка ОС" in w for w in body["warnings"])

    # основа отчётности сохранилась и попадает в документ
    got = client.get(f"/api/v1/audit/subjects/{sid}", headers=auth_headers).json()
    assert got["model"]["reporting_standard"] == "ifrs"
    doc = client.get(f"/api/v1/audit/subjects/{sid}/report.docx", headers=auth_headers)
    assert doc.status_code == 200 and len(doc.content) > 0


def test_analysis_without_revaluation_reports_false(client, auth_headers):
    """Без переоценок флаг в ответе — False (числа учётные)."""
    model = {"periods": [{"label": "2024", "kind": "year"}],
             "balance": {"A_CASH": ["100"], "P_EQUITY": ["100"]}, "income": {}}
    sid = client.post("/api/v1/audit/subjects", json={"name": "ООО", "model": model},
                      headers=auth_headers).json()["id"]
    body = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()
    assert body["revalued"] is False
