"""Журнал покрывает то, что меняет данные (ADMIN-DECOMPOSITION.md, фаза A2).

Журнал вёлся только для «Аудита»: участники, дела и справочник ориентиров. В «Элит» не
писалось **ничего** — ни создание проекта, ни правка модели, ни финализация, ни выгрузка
бизнес-плана. Асимметрию было видно только при разборе инцидента, то есть когда поздно.

Главный тест здесь — не про конкретное действие, а про **перечень**: каждый изменяющий
эндпоинт обязан либо писать журнал, либо стоять в списке исключений с причиной. Иначе
следующий добавленный маршрут выпадет из журнала молча, ровно как выпал весь первый
продукт.
"""
from __future__ import annotations

import inspect
import re

from app.routers import (
    admin,
    audit,
    auth,
    billing,
    holdings,
    integrator,
    jobs,
    organizations,
    projects,
)

#: Роутеры продукта. Перечислены явно: авто-обход внутренностей приложения зависел бы от
#: устройства фреймворка, а список роутеров — часть самого продукта.
ROUTERS = [admin.router, audit.router, auth.router, billing.router, holdings.router, integrator.router,
           jobs.router, organizations.router, projects.router]

#: Изменяющие маршруты, которые журнал **не** пишут — каждый с причиной.
NOT_LOGGED: dict[str, str] = {
    # Чтение результата, а не изменение данных: экран результатов зовёт расчёт при каждом
    # открытии, и записи о нём утопили бы журнал (правило 5 плана).
    "POST /api/v1/projects/{project_id}/calculate": "просмотр результата",
    "POST /api/v1/audit/subjects/{subject_id}/analyze": "просмотр результата",
    "POST /api/v1/audit/subjects/{subject_id}/risk": "просмотр результата",
    "POST /api/v1/projects/{project_id}/sensitivity": "анализ без записи",
    "POST /api/v1/projects/{project_id}/monte-carlo": "анализ без записи",
    "POST /api/v1/projects/{project_id}/monte-carlo/async": "анализ без записи",
    "POST /api/v1/projects/{project_id}/what-if": "анализ без записи",
    "POST /api/v1/audit/compare": "анализ без записи",
    "POST /api/v1/audit/consolidate": "анализ без записи",
    "POST /api/v1/audit/groups/{group_id}/analyze": "анализ без записи",
    "POST /api/v1/holdings/{holding_id}/consolidate": "анализ без записи",
    "POST /api/v1/integrator/consolidate": "анализ без записи",
    # Вход в систему пишется через журналы организаций пользователя (log_user_action),
    # а не привязан к организации из пути.
    "POST /api/v1/auth/login": "пишется через log_user_action",
    "POST /api/v1/auth/register": "организация ещё не существует; пишется org.create",
    "POST /api/v1/auth/activate": "пишется через log_user_action",
    "POST /api/v1/auth/password": "пишется через log_user_action",
    "PATCH /api/v1/auth/me": "профиль пользователя, а не данные организации",
    # Биллинг: подтверждение провайдера приходит без пользователя-актора.
    "POST /api/v1/billing/webhook/yookassa": "внешнее уведомление провайдера, актора нет",
    # Состав холдинга — детали одной сущности; событие пишет сам холдинг.
    "POST /api/v1/holdings/{holding_id}/members": "состав холдинга",
    "PATCH /api/v1/holdings/{holding_id}/members/{project_id}": "состав холдинга",
    "DELETE /api/v1/holdings/{holding_id}/members/{project_id}": "состав холдинга",
}

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _mutating_routes() -> list[tuple[str, str, object]]:
    """Изменяющие маршруты продукта: метод, путь и сам обработчик."""
    out = []
    for router in ROUTERS:
        for route in router.routes:
            methods = getattr(route, "methods", set()) or set()
            for method in sorted(methods & _MUTATING):
                out.append((method, route.path, route.endpoint))
    return sorted(out, key=lambda r: (r[1], r[0]))


def _source_of(endpoint) -> str:
    return inspect.getsource(endpoint)


def test_every_mutating_endpoint_either_logs_or_is_listed():
    """Новый изменяющий маршрут не может выпасть из журнала незаметно.

    Либо он зовёт `log_action`, либо стоит в `NOT_LOGGED` с причиной — и тогда причину
    видно в этом файле, а не только в чужой голове.
    """
    missing = []
    for method, path, endpoint in _mutating_routes():
        key = f"{method} {path}"
        if key in NOT_LOGGED:
            continue
        if "log_action" not in _source_of(endpoint):
            missing.append(key)
    assert missing == [], (
        "эти маршруты меняют данные и не пишут журнал; добавьте запись или внесите их "
        "в NOT_LOGGED с причиной: " + ", ".join(missing))


def test_exceptions_list_has_no_stale_entries():
    """Список исключений не должен переживать сами маршруты — иначе он врёт о продукте."""
    live = {f"{m} {p}" for m, p, _ in _mutating_routes()}
    stale = sorted(set(NOT_LOGGED) - live)
    assert stale == [], f"маршрутов больше нет, уберите их из NOT_LOGGED: {stale}"


def test_both_products_are_covered():
    """Асимметрия «Аудит пишет, Элит молчит» не должна вернуться."""
    logged = {f"{m} {p}" for m, p, _ in _mutating_routes()
              if f"{m} {p}" not in NOT_LOGGED}
    assert any(re.search(r"/api/v1/projects", k) for k in logged)
    assert any(re.search(r"/api/v1/audit/subjects", k) for k in logged)
    assert any(re.search(r"/api/v1/holdings", k) for k in logged)
