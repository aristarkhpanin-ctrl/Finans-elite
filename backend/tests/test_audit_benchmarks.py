"""Свои отраслевые ориентиры организации (Финанс-Аудит; SPEC, Приложение Ф).

Макеты трижды обещают сравнение с отраслью, и платформа трижды отказывала: рыночной
статистики сделок у неё нет. Ориентиры организации превращают отказ в функцию — но
только пока их ни на секунду не выдают за рынок.

Проверяется ровно это: число подписано автором и датой, оговорка «это ваш ориентир»
выводится **всегда**, базы не смешиваются (мультипликатор к EBITDA и к EBIT — разные
величины), отрасль не угадывается, а причина отказа называется вместо нулей.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from audit_core import Benchmark, review_case
from audit_core.benchmarks import METRICS, OWN_DATA, compare_to_benchmark
from audit_core.models import AuditSubjectModel

D = Decimal

VALUATION = {
    "enabled": True, "horizon_years": 5, "wacc": "0.20", "terminal_growth": "0.03",
    "tax_rate": "0.20", "growth": ["0.10"] * 5, "capex": ["70"] * 5,
    "nwc_change": ["20"] * 5,
}


def model(*, industry: str = "Перевозки", **over) -> AuditSubjectModel:
    """Дело с посчитанной оценкой: у мультипликатора есть чему сопоставляться."""
    data: dict = {
        "name": "ООО «Цель»", "industry": industry,
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "220"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "600"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "320"],
        },
        "income": {
            "I_REVENUE": ["1800", "1980"], "I_COGS": ["1260", "1386"],
            "I_OPEX": ["340", "374"], "I_INTEREST": ["40", "40"],
            "I_OTHER": ["0", "0"], "I_TAX": ["32", "36"], "M_DEPRECIATION": ["50", "60"],
        },
        "valuation": VALUATION,
    }
    data.update(over)
    return AuditSubjectModel.model_validate(data)


def bench(**over) -> Benchmark:
    # База дела — EBITDA (в отчётности есть амортизация), и ориентир по умолчанию тот же:
    # сравнение возможно только при совпадении баз.
    data = {"industry": "Перевозки", "metric": "ev_ebitda", "value": D("5.0"),
            "source": "медиана по 3 сделкам фонда", "updated_at": date(2026, 9, 1)}
    data.update(over)
    return Benchmark(**data)                                    # type: ignore[arg-type]


def view(m: AuditSubjectModel, benchmarks: list[Benchmark]):
    r = review_case(m, deep=False)
    return compare_to_benchmark(r.valuation, r.earnings, benchmarks, m.industry)


def test_comparison_says_whose_number_it_is():
    """Ориентир без подписи неотличим от рыночной медианы."""
    v = view(model(), [bench()])
    assert v.available is True
    assert v.source == "медиана по 3 сделкам фонда"
    assert v.updated_at == date(2026, 9, 1)
    assert OWN_DATA in v.caveats


def test_caveat_is_printed_even_when_the_case_matches_the_benchmark():
    """Оговорка — условие чтения блока, а не реакция на отклонение."""
    v = view(model(), [bench()])
    assert any("не рынок" in c for c in v.caveats)


def test_deviation_is_a_share_of_the_benchmark():
    v = view(model(), [bench(value=D("4.0"))])
    assert v.benchmark == D("4.0") and v.case_multiple is not None
    expected = (v.case_multiple - D("4.0")) / D("4.0")
    assert v.deviation == expected


def test_bases_are_never_mixed():
    """Мультипликатор к EBITDA и к EBIT — разные величины (та же логика, что в сравнении)."""
    v = view(model(), [bench(metric="ev_ebit")])
    assert v.available is False
    assert "по другой базе" in v.blockers[0]


def test_industry_is_matched_exactly_but_case_insensitively():
    # «перевозки» и «Перевозки» — одно и то же; «Грузоперевозки» — нет, и угадывать
    # платформа не вправе.
    assert view(model(), [bench(industry="  перевозки ")]).available is True
    assert view(model(), [bench(industry="Грузоперевозки")]).available is False


def test_absent_benchmark_names_the_reason_not_zero():
    v = view(model(), [])
    assert v.available is False and v.benchmark is None
    assert "не заведены" in v.blockers[0]


def test_case_without_industry_is_not_compared():
    v = view(model(industry=""), [bench()])
    assert v.available is False and "отрасль" in v.blockers[0]


def test_without_valuation_there_is_nothing_to_compare():
    m = model()
    m.valuation.enabled = False
    v = view(m, [bench()])
    assert v.available is False and "без оценки" in v.blockers[0]


def test_zero_benchmark_gives_no_share():
    """Деление на ноль — не «дороже в бесконечность раз»: доли просто нет."""
    v = view(model(), [bench(value=D(0))])
    assert v.available is True and v.deviation is None
    assert any("нулю" in c for c in v.caveats)


def test_market_medians_are_named_as_not_computed():
    """Отказ остаётся названным: своих ориентиров мало, чтобы объявить их рынком."""
    v = view(model(), [bench()])
    assert any("не собирает статистику сделок" in t for t in v.not_computed)


def test_metric_labels_cover_the_supported_bases():
    assert set(METRICS) == {"ev_ebitda", "ev_ebit", "ev_revenue"}


# --- API: справочник организации ---

def _benchmarks(client, headers) -> str:
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return f"/api/v1/organizations/{org}/benchmarks"


def test_benchmarks_are_saved_and_returned(client, auth_headers):
    url = _benchmarks(client, auth_headers)
    body = [{"industry": "Перевозки", "metric": "ev_ebit", "value": "5.0",
             "source": "3 сделки фонда"}]
    r = client.put(url, json=body, headers=auth_headers)
    assert r.status_code == 200 and r.json()[0]["value"] == "5.0"
    assert client.get(url, headers=auth_headers).json()[0]["source"] == "3 сделки фонда"


def test_duplicate_pair_is_refused_with_a_reason(client, auth_headers):
    """Два ориентира на одну пару означали бы, что платформа выбирает за пользователя."""
    url = _benchmarks(client, auth_headers)
    body = [{"industry": "Перевозки", "metric": "ev_ebit", "value": "5.0", "source": ""},
            {"industry": " перевозки", "metric": "ev_ebit", "value": "6.0", "source": ""}]
    r = client.put(url, json=body, headers=auth_headers)
    assert r.status_code == 422 and "выбрать между ними" in r.json()["detail"]


def test_benchmarks_are_isolated_by_organization(client, register):
    a = register(email="bm-a@e.ru", org="Орг A")
    b = register(email="bm-b@e.ru", org="Орг B")
    client.put(_benchmarks(client, a),
               json=[{"industry": "Перевозки", "metric": "ev_ebit", "value": "5.0",
                      "source": ""}], headers=a)
    assert client.get(_benchmarks(client, b), headers=b).json() == []


def test_analysis_carries_the_comparison(client, auth_headers):
    """Ориентир организации доезжает до разбора дела, а не остаётся в справочнике."""
    client.put(_benchmarks(client, auth_headers),
               json=[{"industry": "Перевозки", "metric": "ev_ebitda", "value": "5.0",
                      "source": "3 сделки фонда"}], headers=auth_headers)
    sid = client.post("/api/v1/audit/subjects",
                      json={"name": "ООО «Цель»", "model": model().model_dump(mode="json")},
                      headers=auth_headers).json()["id"]
    body = client.post(f"/api/v1/audit/subjects/{sid}/analyze",
                       headers=auth_headers).json()["benchmark"]
    assert body["available"] is True
    assert body["source"] == "3 сделки фонда"
    assert any("не рынок" in c for c in body["caveats"])
