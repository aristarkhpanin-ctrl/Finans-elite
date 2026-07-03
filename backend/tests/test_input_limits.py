"""Границы входных данных: защита от исчерпания ресурсов (DoS)."""
import pytest
from pydantic import ValidationError

from calc_core.models import ProjectHeader


def test_duration_months_upper_bound():
    ProjectHeader(duration_months=600)  # 50 лет — верхняя граница допустима
    for bad in (601, 100_000, 100_000_000):
        with pytest.raises(ValidationError):
            ProjectHeader(duration_months=bad)


def test_calculate_rejects_absurd_horizon(client):
    sample = client.get("/api/v1/sample").json()
    sample["header"]["duration_months"] = 1_000_000
    r = client.post("/api/v1/calculate", json=sample)
    assert r.status_code == 422  # отклонено валидацией до расчёта, воркер не нагружается
