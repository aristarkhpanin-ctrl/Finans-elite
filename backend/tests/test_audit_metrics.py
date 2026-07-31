"""Пользовательские методики Финанс-Аудит (фаза G): формулы над аналитической формой."""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze
from audit_core.models import AuditPeriod, AuditSubjectModel, UserMetric

D = Decimal


def _model(metrics: list[UserMetric] | None = None) -> AuditSubjectModel:
    return AuditSubjectModel(
        periods=[AuditPeriod(label="2023"), AuditPeriod(label="2024")],
        balance={
            "A_FIXED": [D(100), D(120)], "A_INVENTORY": [D(30), D(35)],
            "A_RECEIVABLE": [D(40), D(45)], "A_CASH": [D(30), D(50)],
            "P_EQUITY": [D(120), D(150)], "P_LONG": [D(30), D(30)],
            "P_SHORT": [D(50), D(70)], "M_RETAINED": [D(60), D(90)],
        },
        income={
            "I_REVENUE": [D(500), D(600)], "I_COGS": [D(300), D(360)],
            "I_OPEX": [D(80), D(90)], "I_INTEREST": [D(10), D(12)],
            "I_OTHER": [D(0), D(0)], "I_TAX": [D(22), D(28)],
        },
        user_metrics=metrics or [],
    )


def _by_name(r, name):
    return next(u for u in r.user_metrics if u.name == name)


def test_metric_over_analytical_lines():
    """Формула видит строки аналитической формы, включая производные подытоги."""
    r = analyze(_model([
        UserMetric(name="Доля запасов", formula="A_INVENTORY / A_TOTAL"),
        UserMetric(name="Маржа EBIT", formula="I_EBIT / I_REVENUE"),
        UserMetric(name="Оборотные минус долг", formula="A_CURRENT - P_SHORT"),
    ]))
    assert _by_name(r, "Доля запасов").values == [D(30) / D(200), D(35) / D(250)]
    assert _by_name(r, "Маржа EBIT").values == [D(120) / D(500), D(150) / D(600)]
    assert _by_name(r, "Оборотные минус долг").values == [D(50), D(60)]


def test_metric_sees_memo_and_period_count():
    """Доступны справочная строка (M_RETAINED) и число периодов N."""
    r = analyze(_model([
        UserMetric(name="Накопленная прибыль к активам", formula="M_RETAINED / A_TOTAL"),
        UserMetric(name="Число периодов", formula="N"),
    ]))
    assert _by_name(r, "Накопленная прибыль к активам").values == [D(60) / D(200), D(90) / D(250)]
    assert _by_name(r, "Число периодов").values == [D(2), D(2)]


def test_formula_error_does_not_break_analysis():
    """Ошибка формулы: показатель с сообщением и нулями, остальной анализ цел."""
    r = analyze(_model([
        UserMetric(name="Битая", formula="A_TOTAL / "),
        UserMetric(name="Неизвестная строка", formula="НЕТ_ТАКОЙ + 1"),
        UserMetric(name="Рабочая", formula="A_CASH"),
    ]))
    broken = _by_name(r, "Битая")
    assert broken.error and broken.values == [D(0), D(0)]
    assert _by_name(r, "Неизвестная строка").error is not None
    # анализ не пострадал
    assert _by_name(r, "Рабочая").values == [D(30), D(50)]
    assert r.ratios["liquidity"]["Коэффициент текущей ликвидности"][0] == D(100) / D(50)


def test_no_metrics_is_inert():
    """Без методик раздел пуст."""
    assert analyze(_model()).user_metrics == []


def test_metrics_in_api_and_docx(client, auth_headers):
    """Показатели доходят до ответа API и попадают в документ."""
    from io import BytesIO

    from docx import Document

    model = {
        "periods": [{"label": "2024", "kind": "year"}],
        "balance": {"A_CASH": ["200"], "P_EQUITY": ["150"], "P_SHORT": ["50"]},
        "income": {"I_REVENUE": ["500"], "I_COGS": ["300"], "I_OPEX": ["100"],
                   "I_INTEREST": ["10"], "I_OTHER": ["0"], "I_TAX": ["18"]},
        "user_metrics": [{"name": "Своя маржа", "formula": "I_NET / I_REVENUE"}],
    }
    sid = client.post("/api/v1/audit/subjects", json={"name": "С", "model": model},
                      headers=auth_headers).json()["id"]
    body = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()
    assert [u["name"] for u in body["user_metrics"]] == ["Своя маржа"]
    assert body["user_metrics"][0]["error"] is None

    docx = client.get(f"/api/v1/audit/subjects/{sid}/report.docx", headers=auth_headers).content
    text = "\n".join(p.text for p in Document(BytesIO(docx)).paragraphs)
    assert "Пользовательские показатели" in text
