"""Отраслевые шаблоны и свои чек-листы (ADMIN-DECOMPOSITION.md, D4).

Шаблон обязан **считаться** (иначе он не шаблон, а витрина поломки) и **не выдавать себя
за отраслевую норму**: базы отраслевых данных у платформы нет, и цифра, похожая на
правду, — самый дорогой способ соврать.
"""
from __future__ import annotations

from decimal import Decimal

from calc_core import run
from calc_core.samples import TEMPLATES
from calc_core.templates import INDUSTRY_TEMPLATES, NOT_A_BENCHMARK

# --- Шаблоны считаются ---

def test_every_template_calculates_and_the_balance_converges():
    """Шаблон, который не считается, — витрина поломки на первом же экране продукта.

    Проверяется главное свойство модели (актив = пассив), а не конкретные числа: числа
    шаблона живут не в golden — их правят, когда правят сам шаблон.
    """
    for tid, template in INDUSTRY_TEMPLATES.items():
        result = run(template.build())
        gap = max(abs(a - b) for a, b in zip(result.balance["B20"], result.balance["B34"],
                                             strict=True))
        assert gap < Decimal("0.01"), f"{tid}: баланс не сходится на {gap}"
        assert result.warnings == [], f"{tid}: расчёт с предупреждениями {result.warnings}"


def test_no_template_starves_for_cash():
    """Шаблон с кассовым разрывом учит, что так бывает нормально. Разрыв в примере —
    это не урок, а недосмотр автора: у каждого шаблона деньги на месте."""
    for tid, template in INDUSTRY_TEMPLATES.items():
        result = run(template.build())
        worst = min(result.cashflow["C29"])
        assert worst >= 0, f"{tid}: касса уходит в минус ({worst})"


def test_metrics_are_plausible_or_honestly_absent():
    """Показатели шаблона читают как пример: «IRR −100%» и «PI 44» учат неверному.

    Там, где норма доходности к потоку неприменима (действующий бизнес без вложения),
    ответом обязан быть `None`, а не число с потолка.
    """
    for tid, template in INDUSTRY_TEMPLATES.items():
        metrics = run(template.build()).metrics
        if metrics.irr_annual is not None:
            assert Decimal("-0.9") < metrics.irr_annual < Decimal(20), (
                f"{tid}: IRR {metrics.irr_annual} — это не пример, а артефакт")


# --- Шаблон не выдаёт себя за норму ---

def test_every_template_says_its_numbers_are_invented():
    """Оговорка едет **вместе** с шаблоном: человек обязан узнать про выдуманные числа
    там же, где увидит цифры, а не в документации, которую не откроет."""
    for tid, template in INDUSTRY_TEMPLATES.items():
        assert template.assumptions, f"{tid}: допущения не названы"
        assert template.assumptions[0] == NOT_A_BENCHMARK, (
            f"{tid}: первым пунктом обязан стоять отказ от отраслевой нормы")
        assert len(template.assumptions) >= 3, (
            f"{tid}: три пункта — минимум, иначе список формальный")


def test_every_template_says_what_it_shows():
    """Шаблон полезен не числами, а тем, какую машинерию модели он показывает."""
    for tid, template in INDUSTRY_TEMPLATES.items():
        assert template.shows and template.industry, f"{tid}: не назван смысл шаблона"


def test_template_ids_do_not_collide_with_the_demo_ones():
    """Совпавший ключ молча спрятал бы один шаблон за другим."""
    assert set(INDUSTRY_TEMPLATES) & set(TEMPLATES) == set()


# --- API ---

def test_the_catalog_carries_assumptions(client):
    body = client.get("/api/v1/templates").json()
    by_id = {t["id"]: t for t in body}
    assert set(INDUSTRY_TEMPLATES) <= set(by_id)
    assert all(t["assumptions"] for t in body), "шаблон без оговорки в каталоге"
    assert "не отраслевая норма" in by_id["cafe"]["assumptions"][0]


def test_a_template_model_can_start_a_project(client, register):
    headers = register()
    model = client.get("/api/v1/templates/farming").json()
    created = client.post("/api/v1/projects", json={"name": "Поля", "model": model},
                          headers=headers)
    assert created.status_code == 201
    calc = client.post(f"/api/v1/projects/{created.json()['id']}/calculate",
                       headers=headers)
    assert calc.status_code == 200 and calc.json()["n"] == 36


def test_an_unknown_template_is_a_404(client):
    assert client.get("/api/v1/templates/нет-такого").status_code == 404


# --- Свои чек-листы организации ---

def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def test_a_checklist_is_saved_whole_and_read_back(client, register):
    headers = register()
    org = _org_id(client, headers)
    body = [{"name": "Проверка производственной компании", "scope": "Производство",
             "items": ["Осмотреть площадку", "Сверить остатки склада", "  ", ""]}]
    saved = client.put(f"/api/v1/organizations/{org}/checklists", json=body,
                       headers=headers).json()
    assert len(saved) == 1
    # Пустые пункты не сохраняются: пустая строка в чек-листе — это не процедура.
    assert saved[0]["items"] == ["Осмотреть площадку", "Сверить остатки склада"]
    assert saved[0]["author_email"] == "owner@e.ru"


def test_two_checklists_with_one_name_are_refused(client, register):
    headers = register()
    org = _org_id(client, headers)
    r = client.put(f"/api/v1/organizations/{org}/checklists",
                   json=[{"name": "Базовый", "items": ["а"]},
                         {"name": " базовый ", "items": ["б"]}], headers=headers)
    assert r.status_code == 422 and "выбрать между ними" in r.json()["detail"]


def test_checklists_belong_to_the_organization_not_to_the_platform(client, register):
    """Платформа не утверждает, что именно проверяют в отрасли: чек-лист пишет тот, кто
    знает отрасль, и он принадлежит его организации."""
    first = register()
    org_a = _org_id(client, first)
    client.put(f"/api/v1/organizations/{org_a}/checklists",
               json=[{"name": "Наш", "items": ["раз"]}], headers=first)

    second = register(email="other@e.ru", org="Другая")
    org_b = _org_id(client, second)
    assert client.get(f"/api/v1/organizations/{org_b}/checklists",
                      headers=second).json() == []
    assert client.get(f"/api/v1/organizations/{org_a}/checklists",
                      headers=second).status_code == 403


def test_replacing_checklists_is_written_to_the_journal(client, register):
    headers = register()
    org = _org_id(client, headers)
    client.put(f"/api/v1/organizations/{org}/checklists",
               json=[{"name": "Базовый", "items": ["раз"]}], headers=headers)
    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=headers).json()["entries"]}
    assert "checklists.replace" in actions
