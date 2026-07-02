"""Тесты HTTP-API (5.3) через TestClient."""
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _line(statement: dict, code: str) -> list[str]:
    for line in statement["lines"]:
        if line["code"] == code:
            return line["values"]
    raise KeyError(code)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine_version"]


def test_sample_endpoint_returns_model():
    r = client.get("/api/v1/sample")
    assert r.status_code == 200
    model = r.json()
    assert model["header"]["duration_months"] == 12
    assert model["operating_plan"]["sales"]


def test_templates_list_and_calculate():
    """Шаблоны: список доступен, каждый шаблон — валидная модель, считается без ошибок."""
    lst = client.get("/api/v1/templates")
    assert lst.status_code == 200
    items = lst.json()
    ids = {t["id"] for t in items}
    assert {"production", "trade", "services", "enterprise"} <= ids
    for tid in ids:
        model = client.get(f"/api/v1/templates/{tid}")
        assert model.status_code == 200
        calc = client.post("/api/v1/calculate", json=model.json())
        assert calc.status_code == 200, f"шаблон {tid} не считается"
    assert client.get("/api/v1/templates/nope").status_code == 404


def test_calculate_roundtrip():
    sample = client.get("/api/v1/sample").json()
    r = client.post("/api/v1/calculate", json=sample)
    assert r.status_code == 200
    data = r.json()
    assert data["n"] == 12
    assert data["engine_version"]
    # балансовый инвариант сохраняется и в ответе API
    b20 = _line(data["balance"], "B20")
    b34 = _line(data["balance"], "B34")
    for a, b in zip(b20, b34):
        assert abs(Decimal(a) - Decimal(b)) <= Decimal("0.01")
    # показатели и коэффициенты присутствуют
    assert "npv" in data["metrics"]
    assert "Коэффициент текущей ликвидности" in data["ratios"]["liquidity"]


def test_calculate_unbalanced_starting_balance_422():
    bad = {"company": {"starting_balance": {"cash": "100"}}}  # актив 100 ≠ пассив 0
    r = client.post("/api/v1/calculate", json=bad)
    assert r.status_code == 422


def test_calculate_validation_error_422():
    # duration_months < 1 нарушает валидацию модели
    r = client.post("/api/v1/calculate", json={"header": {"duration_months": 0}})
    assert r.status_code == 422


def test_openapi_available():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/api/v1/calculate" in r.json()["paths"]
