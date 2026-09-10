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
    comments,
    holdings,
    integrator,
    jobs,
    organizations,
    projects,
)

#: Роутеры продукта. Перечислены явно: авто-обход внутренностей приложения зависел бы от
#: устройства фреймворка, а список роутеров — часть самого продукта.
ROUTERS = [admin.router, audit.router, auth.router, billing.router, comments.router,
           holdings.router, integrator.router, jobs.router, organizations.router,
           projects.router]

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
    "PATCH /api/v1/auth/me": "профиль пользователя, а не данные организации",
    # Настройка второго фактора начата, но не подтверждена: доступ она ещё не меняет, а
    # запись «начал настраивать» в журнале организации отвечала бы на вопрос, которого
    # никто не задаёт. Включение, выключение и сброс — пишутся.
    "POST /api/v1/auth/totp/setup": "секрет заведён, но второй фактор ещё не действует",
    # Биллинг: подтверждение провайдера приходит без пользователя-актора.
    "POST /api/v1/billing/webhook/yookassa": "внешнее уведомление провайдера, актора нет",
    # Реплика обсуждения (D3) сама себя журналирует: у неё есть автор, время, текст и
    # «надгробие» после удаления — вторая копия в журнале утопила бы его в разговоре.
    # Правки текста нет вовсе, поэтому «кто и когда изменил» здесь не возникает.
    "POST /api/v1/projects/{project_id}/comments": "реплика — сама себе запись",
    "POST /api/v1/audit/subjects/{subject_id}/comments": "реплика — сама себе запись",
    "POST /api/v1/comments/{comment_id}/resolve": "закрывший назван в самой реплике",
    "DELETE /api/v1/comments/{comment_id}/resolve": "открывший назван в самой реплике",
    "DELETE /api/v1/comments/{comment_id}": "«надгробие» остаётся в самой реплике",
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


#: Чем маршрут может писать журнал. Событие человека (вход, смена пароля, блокировка
#: учётной записи) не привязано к организации из пути и уходит в журналы **всех** его
#: организаций через `log_user_action` — но это ровно такая же запись, и считать её
#: «исключением из журнала» значило бы держать в списке исключений то, что пишется.
#:
#: `send_and_log` — то же самое, отложенное на после ответа (D1): письмо «забыли пароль»
#: нельзя отправлять в самом ответе (время ответа выдало бы существование адреса), а
#: исход отправки попадает в журнал теми же словами, какими вернулся.
_LOGGERS = ("crud.log_action", "crud.log_user_action", "send_and_log")


def _logs(endpoint) -> bool:
    source = _source_of(endpoint)
    return any(call in source for call in _LOGGERS)


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
        if not _logs(endpoint):
            missing.append(key)
    assert missing == [], (
        "эти маршруты меняют данные и не пишут журнал; добавьте запись или внесите их "
        "в NOT_LOGGED с причиной: " + ", ".join(missing))


def test_exceptions_list_does_not_cover_routes_that_do_log():
    """Исключение, которое на самом деле пишет журнал, — ложь о продукте.

    Без этой проверки список исключений однажды перестал бы означать «журнал не
    пишется»: маршрут научился писать, а строка о нём осталась — и следующий, кто её
    прочтёт, будет искать пропажу там, где всё на месте.
    """
    logging_but_listed = [f"{m} {p}" for m, p, e in _mutating_routes()
                          if f"{m} {p}" in NOT_LOGGED and _logs(e)]
    assert logging_but_listed == [], (
        "эти маршруты пишут журнал — уберите их из NOT_LOGGED: "
        + ", ".join(logging_but_listed))


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


#: Маршруты, объявленные прямо на приложении, а не в роутере. Каждый — с причиной:
#: они не трогают данных организации вовсе, и журналу писать о них нечего.
APP_LEVEL: dict[str, str] = {
    "/api/v1/calculate": "расчёт без сохранения: ничего не принадлежит организации",
    "/api/v1/sample": "образец модели — константа продукта",
    "/api/v1/templates": "каталог шаблонов — константа продукта",
    "/api/v1/templates/{template_id}": "шаблон — константа продукта",
}


def test_the_roster_of_routers_is_not_stale():
    """Перечень роутеров обязан покрывать всё, что приложение действительно включило.

    Найдено при добавлении обсуждения (D3): новый роутер не попал в этот список, и
    проверка покрытия журналом **молча его не увидела** — то есть перечень, заведённый
    ровно против таких пропаж, сам оказался местом, где пропажа возможна.
    """
    from app.main import app

    covered = {r.path for router in ROUTERS for r in router.routes} | set(APP_LEVEL)
    live = {getattr(r, "path", "") for r in app.routes
            if getattr(r, "path", "").startswith("/api/v1")}
    missing = sorted(p for p in live if p not in covered)
    assert missing == [], (
        "эти маршруты приложения не покрыты перечнем ROUTERS — добавьте их роутер "
        "(или, если они не трогают данных организации, внесите в APP_LEVEL с причиной): "
        + ", ".join(missing))


def test_the_app_level_exceptions_are_not_stale():
    """Исключение, пережившее свой маршрут, врёт о продукте — как и в NOT_LOGGED."""
    from app.main import app

    live = {getattr(r, "path", "") for r in app.routes}
    stale = sorted(set(APP_LEVEL) - live)
    assert stale == [], f"маршрутов больше нет, уберите их из APP_LEVEL: {stale}"
