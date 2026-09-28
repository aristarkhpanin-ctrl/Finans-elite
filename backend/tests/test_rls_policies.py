"""Каждая таблица организации либо под RLS, либо названа исключением (найдено в F3).

Изоляцию арендатора на PostgreSQL держит политика ``tenant_isolation``. Исключения
существуют и законны — строку читают раньше, чем становится известен арендатор
(членство, ключ доступа, подписка), либо она вообще не принадлежит клиенту (служебный
журнал, события пользования), — но каждое обязано быть **названо**.

**Этот тест заведён потому, что проверять было нечем.** В F2 в докстринг `Payment`
попало утверждение «RLS-политики нет — единственной среди таблиц с ``organization_id``».
Оно было неправдой в момент написания: таких таблиц семь. Утверждение прожило две фазы
ровно потому, что его никто не мог проверить: политики объявляются в миграциях, а
претензия жила в докстринге модели.

Теперь перечень сверяется с самими миграциями. Тест падает в обе стороны: новая таблица
организации без политики и без причины — и причина, оставшаяся для таблицы, которая
политику всё-таки получила.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.database import Base
from app.db_models import NO_RLS_POLICY

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _tables_with_policy() -> set[str]:
    """Кому миграции завели ``tenant_isolation`` — по самим миграциям, а не по памяти.

    Форм объявления две: имя таблицы прямо в SQL и подстановка из кортежа ``_TABLES``
    (так сделана самая первая миграция RLS). Учитывать надо обе: выборка, знающая одну,
    молча объявила бы половину таблиц незащищёнными — ровно так первый черновик этого
    теста и «нашёл» несуществующую дыру в `projects`.
    """
    source = "\n".join(p.read_text(encoding="utf-8") for p in _VERSIONS.glob("*.py"))
    tables = set(re.findall(r"CREATE POLICY tenant_isolation ON (\w+)", source))
    for block in re.findall(r"_TABLES\s*=\s*\(([^)]*)\)", source):
        tables |= set(re.findall(r'"(\w+)"', block))
    return tables


def _tables_with_org() -> set[str]:
    return {m.class_.__tablename__ for m in Base.registry.mappers
            if hasattr(m.class_, "organization_id")}


def test_the_detection_of_policies_actually_sees_them():
    """Сторож самого теста: выборка обязана находить заведомо защищённые таблицы.

    Без него «политик нет ни у кого» выглядело бы как зелёный перечень исключений.
    """
    assert {"projects", "audit_subjects", "comments", "support_grants"} \
        <= _tables_with_policy()


def test_every_tenant_table_is_either_protected_or_named():
    """Новая таблица организации не может остаться без изоляции незаметно."""
    unnamed = _tables_with_org() - _tables_with_policy() - set(NO_RLS_POLICY)
    assert unnamed == set(), (
        "эти таблицы привязаны к организации, не имеют RLS-политики и не названы "
        "исключением с причиной: " + ", ".join(sorted(unnamed)))


def test_no_reason_is_left_for_a_table_that_got_a_policy():
    """Обратная сторона. Оставленная причина утверждает, что изоляции нет там, где она
    есть, — и следующий читатель построит на этом решение."""
    stale = set(NO_RLS_POLICY) & _tables_with_policy()
    assert stale == set(), (
        "у этих таблиц политика есть, а причина «политики нет» осталась: "
        + ", ".join(sorted(stale)))


def test_every_exception_has_a_reason():
    assert all(reason.strip() for reason in NO_RLS_POLICY.values())


def test_the_payment_docstring_no_longer_claims_to_be_the_only_one():
    """Исправленное утверждение — тоже утверждение, и оно тоже проверяется.

    Проверяется **само утверждение**, а не слова из него: прежняя фраза осталась в
    докстринге как цитата («здесь было написано…»), и запрет на подстроку вычеркнул бы
    заодно рассказ о том, как ошибка появилась. Ловится связка «нет — единственной»,
    которой утверждение и делалось.
    """
    from app.db_models import Payment

    doc = Payment.__doc__ or ""
    assert "нет — единственной" not in doc
    assert "NO_RLS_POLICY" in doc and "нашлась она в F3" in doc
