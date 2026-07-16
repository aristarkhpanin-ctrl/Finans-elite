"""Тесты анализа изменений версий (пакет №8, gap 4.4, V0): чистые диф-функции + crud."""
from decimal import Decimal

from app.versioning import (
    MODEL_DIFF_LIMIT,
    diff_metrics,
    diff_models,
    flatten_leaves,
)
from calc_core import run
from calc_core.samples import build_sample_project


def test_flatten_leaves_nested_and_lists():
    obj = {"a": 1, "b": {"c": "x"}, "d": [10, 20], "e": [], "f": {}}
    flat = flatten_leaves(obj)
    assert flat == {"a": 1, "b.c": "x", "d[0]": 10, "d[1]": 20, "e": [], "f": {}}


def test_diff_models_added_removed_changed():
    old = {"header": {"name": "П", "duration_months": 12}, "removed_field": 1}
    new = {"header": {"name": "П2", "duration_months": 12}, "added_field": 2}
    changes, truncated = diff_models(old, new)
    assert not truncated
    by_path = {c.path: c for c in changes}
    assert by_path["header.name"].kind == "changed"
    assert by_path["header.name"].old == "П" and by_path["header.name"].new == "П2"
    assert by_path["added_field"].kind == "added" and by_path["added_field"].new == 2
    assert by_path["removed_field"].kind == "removed" and by_path["removed_field"].old == 1
    assert "header.duration_months" not in by_path         # неизменное не попадает


def test_diff_models_long_series_only_changed_index():
    old = {"price": [str(i) for i in range(120)]}
    new = {"price": [str(i) for i in range(120)]}
    new["price"][3] = "999"
    changes, truncated = diff_models(old, new)
    assert not truncated
    assert len(changes) == 1
    assert changes[0].path == "price[3]" and changes[0].new == "999"


def test_diff_models_truncation():
    old = {"a": [0] * (MODEL_DIFF_LIMIT + 50)}
    new = {"a": [1] * (MODEL_DIFF_LIMIT + 50)}
    changes, truncated = diff_models(old, new)
    assert truncated and len(changes) == MODEL_DIFF_LIMIT


def test_diff_models_sorted_deterministic():
    old = {"z": 1, "a": 1, "m": 1}
    new = {"z": 2, "a": 2, "m": 2}
    changes, _ = diff_models(old, new)
    assert [c.path for c in changes] == ["a", "m", "z"]


def test_diff_metrics_headline_fields():
    model = build_sample_project()
    r1 = run(model)
    m2 = build_sample_project()
    m2.operating_plan.sales[0].price = [p * Decimal(2) for p in m2.operating_plan.sales[0].price]
    r2 = run(m2)
    changes = diff_metrics(r1, r2)
    keys = {c.key for c in changes}
    assert {"npv", "irr_annual", "pi", "pb_months"} <= keys
    npv = next(c for c in changes if c.key == "npv")
    assert npv.old != npv.new                              # удвоение цены изменило NPV
    assert npv.label == "NPV"


def test_diff_metrics_none_preserved():
    model = build_sample_project()
    r = run(model)
    changes = diff_metrics(r, r)
    for c in changes:
        assert c.old == c.new                              # одинаковые версии → без изменений


# --- crud: снимок/список/чтение версии ---

def test_crud_create_list_get_version(client, auth_headers, db_session):
    from app import crud
    from app.db_models import Project

    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "V", "model": sample},
                      headers=auth_headers).json()["id"]
    project = db_session.get(Project, pid)

    v = crud.create_version(db_session, project, "Базовая", npv="123.45",
                            engine_version="0.9.29")
    assert crud.count_versions(db_session, pid) == 1
    versions = crud.list_versions(db_session, project.organization_id, pid)
    assert len(versions) == 1 and versions[0].label == "Базовая"
    got = crud.get_version(db_session, project.organization_id, pid, v.id)
    assert got is not None and got.npv == "123.45" and got.engine_version == "0.9.29"
    assert got.model == project.model                      # снимок текущей модели

    crud.delete_version(db_session, got)
    assert crud.count_versions(db_session, pid) == 0
