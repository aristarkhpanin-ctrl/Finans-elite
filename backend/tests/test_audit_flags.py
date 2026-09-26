"""Реестр красных флагов (Финанс-Аудит, «Экран 9»; методика — SPEC, Приложение И).

У каждого правила два теста — срабатывание и тишина. Без второго реестр превращается
в шум, который перестают читать, и настоящий флаг теряется среди придирок. Отдельно
проверяется главное решение методики: денежная мера есть **не у всякого** флага, и
итог не делает вид, что она есть у всех.
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, detect_flags
from audit_core.models import AuditSubjectModel
from audit_core.samples import build_quarterly_subject, build_trading_subject

D = Decimal


def model(**over) -> AuditSubjectModel:
    """Здоровое предприятие на 2 года: рост выручки, стабильная маржа и структура."""
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
        },
    }
    for key, value in over.items():
        if key in ("balance", "income"):
            data[key] = {**data[key], **value}      # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def flags(m: AuditSubjectModel):
    return detect_flags(m, analyze(m))


def codes(m: AuditSubjectModel) -> list[str]:
    return [f.code for f in flags(m).flags]


def one(m: AuditSubjectModel, code: str):
    found = [f for f in flags(m).flags if f.code == code]
    assert found, f"правило {code} не сработало: {codes(m)}"
    return found[0]


# ── Тишина ────────────────────────────────────────────────────────────────────

def test_healthy_company_raises_nothing():
    assert flags(model()).flags == []


def test_samples_are_clean():
    """Эталонные семплы продукта не поднимают флагов — иначе golden-данные «подозрительны»."""
    for build in (build_trading_subject, build_quarterly_subject):
        m = build()
        assert detect_flags(m, analyze(m)).flags == []


def test_empty_model_raises_nothing():
    m = AuditSubjectModel()
    assert detect_flags(m, analyze(m)).flags == []


# ── Правила с денежной мерой ──────────────────────────────────────────────────

def test_receivables_outpacing_revenue_is_measured():
    """Дебиторка +60% при выручке +10%: мера — превышение над прежней оборачиваемостью."""
    m = model(balance={"A_RECEIVABLE": ["200", "320"], "A_CASH": ["100", "30"]})
    f = one(m, "receivables_outpace_revenue")
    assert f.severity == "risk" and f.periods == [1]
    # при прежней оборачиваемости дебиторка была бы 200 × (1980/1800) = 220
    assert f.evidence["expected_receivables"] == D(220)
    assert f.impact == D(100)


def test_inventory_outpacing_cogs_is_measured():
    m = model(balance={"A_INVENTORY": ["300", "480"]})
    f = one(m, "inventory_outpace_cogs")
    assert f.severity == "warning" and f.impact == D(150)   # 480 − 300×(1386/1260)


def test_other_income_spike_is_measured_by_itself():
    """Разовые доходы — их же и вычитают: в следующем периоде их не будет."""
    m = model(income={"I_OTHER": ["0", "300"]})
    f = one(m, "other_income_spike")
    assert f.severity == "risk" and f.impact == D(300)


# ── Правила без денежной меры ─────────────────────────────────────────────────

def test_negative_equity_has_no_price():
    """Отрицательный капитал не выражается суммой скидки — и её не выдумываем."""
    m = model(balance={"P_EQUITY": ["500", "-50"], "P_SHORT": ["300", "970"]})
    f = one(m, "negative_equity")
    assert f.severity == "risk" and f.impact is None
    assert f.evidence["min_equity"] == D(-50)


def test_interest_not_covered_has_no_price():
    m = model(income={"I_INTEREST": ["40", "600"]})
    f = one(m, "interest_not_covered")
    assert f.severity == "risk" and f.impact is None


def test_profit_without_cash_has_no_price():
    """Разрыв прибыли и денег — сигнал, а не сумма: вычитать из цены нечего."""
    # чистая прибыль периода — 144; деньги упали на 80, то есть больше половины
    m = model(balance={"A_CASH": ["100", "20"], "A_FIXED": ["400", "550"]})
    f = one(m, "profit_without_cash")
    assert f.severity == "risk" and f.impact is None
    assert f.evidence["cash_drop"] == D(80)


def test_small_cash_dip_is_not_a_flag():
    """Небольшая просадка денег при растущей прибыли — норма работы, а не флаг.

    Любое предприятие временами вкладывается в оборотку. Без порога существенности
    правило срабатывало бы на здоровых данных (и срабатывало — на эталонном
    квартальном семпле), а реестр из шума перестают читать.
    """
    m = model(balance={"A_CASH": ["100", "90"], "A_FIXED": ["400", "480"]})
    assert "profit_without_cash" not in codes(m)


def test_short_debt_over_current_assets():
    m = model(balance={"P_SHORT": ["300", "900"], "P_LONG": ["200", "-380"]})
    f = one(m, "short_debt_over_current")
    assert f.severity == "warning" and f.impact is None


def test_margin_down_on_growth():
    """Рост выручки, купленный ценой: маржа падает."""
    m = model(income={"I_COGS": ["1260", "1600"]})
    f = one(m, "margin_down_on_growth")
    assert f.severity == "warning" and f.evidence["margin_now"] < f.evidence["margin_was"]


# ── Итог реестра ──────────────────────────────────────────────────────────────

def test_total_counts_only_priced_flags():
    """Итог складывает оценённые и **называет число неоценённых**.

    Иначе сумма выглядела бы полной ценой рисков, хотя половина рисков в неё не вошла:
    покупатель получил бы скидку с точностью до рубля там, где основание — суждение.
    """
    m = model(
        balance={"A_RECEIVABLE": ["200", "320"], "A_CASH": ["100", "30"],
                 "P_EQUITY": ["500", "-50"], "P_SHORT": ["300", "1170"]},
        income={"I_OTHER": ["0", "300"]},
    )
    reg = flags(m)
    priced = [f for f in reg.flags if f.impact is not None]
    unpriced = [f for f in reg.flags if f.impact is None]

    assert reg.unpriced == len(unpriced) > 0
    assert reg.priced_total == sum(f.impact for f in priced)
    # неоценённые в сумму не попали
    assert reg.priced_total == sum(f.impact for f in reg.flags if f.impact is not None)


def test_risks_come_first():
    """Тяжёлые флаги вверху: читают обычно только начало списка."""
    m = model(
        balance={"A_INVENTORY": ["300", "480"], "A_RECEIVABLE": ["200", "320"],
                 "A_CASH": ["100", "30"]},
    )
    severities = [f.severity for f in flags(m).flags]
    assert severities == sorted(severities, key=["risk", "warning"].index)
    assert flags(m).risks == severities.count("risk")


def test_flags_do_not_touch_the_analysis():
    """Реестр только читает: результат анализа после него тот же объект и те же числа."""
    m = model(balance={"A_RECEIVABLE": ["200", "320"]})
    result = analyze(m)
    before = [list(ln.values) for ln in result.balance]
    detect_flags(m, result)
    assert [list(ln.values) for ln in result.balance] == before
    # и в самом результате флагов нет — они не часть методики расчёта
    assert not hasattr(result, "flags")


# ── Реестр в API ──────────────────────────────────────────────────────────────

def _create(client, headers, balance, income):
    m = {"name": "ООО «Цель»", "currency": "RUB", "industry": "Торговля",
         "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
         "balance": balance, "income": income}
    return client.post("/api/v1/audit/subjects", json={"name": "ООО «Цель»", "model": m},
                       headers=headers).json()["id"]


def test_analyze_carries_flag_registry(client, auth_headers):
    """Ответ анализа несёт реестр — и итог в нём честный."""
    base = model(balance={"A_RECEIVABLE": ["200", "320"], "A_CASH": ["100", "30"],
                          "P_EQUITY": ["500", "-50"], "P_SHORT": ["300", "1170"]})
    sid = _create(client, auth_headers,
                  {k: [str(x) for x in v] for k, v in base.balance.items()},
                  {k: [str(x) for x in v] for k, v in base.income.items()})
    a = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()

    reg = a["flags"]
    codes_ = {f["code"] for f in reg["flags"]}
    assert "receivables_outpace_revenue" in codes_ and "negative_equity" in codes_
    # у флага без денежной меры impact пустой, а не нулевой
    neg = next(f for f in reg["flags"] if f["code"] == "negative_equity")
    assert neg["impact"] is None
    assert reg["unpriced"] >= 1 and float(reg["priced_total"]) > 0


def test_clean_case_has_empty_registry(client, auth_headers):
    base = model()
    sid = _create(client, auth_headers,
                  {k: [str(x) for x in v] for k, v in base.balance.items()},
                  {k: [str(x) for x in v] for k, v in base.income.items()})
    a = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()
    assert a["flags"]["flags"] == [] and a["flags"]["unpriced"] == 0


def test_flags_absent_from_golden_snapshot():
    """Флаги не входят в снимок анализа: методика расчёта ими не меняется."""
    from audit_core.serialize import result_to_dict
    m = model(balance={"A_RECEIVABLE": ["200", "320"]})
    assert "flags" not in result_to_dict(analyze(m))
