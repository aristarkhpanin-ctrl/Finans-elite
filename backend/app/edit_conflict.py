"""Защита от одновременной правки проекта и дела (пакет G, G2).

``PUT`` проекта и дела перезаписывает модель **целиком**. Двое открыли, оба сохранили —
правки первого исчезали молча: ошибки нет, в журнале две записи ``update``, и пропажу
замечали, когда не хватало чисел. Для этого продукта тихая потеря данных — худший класс
дефекта, а обсуждения (D3) прямо зовут к совместной работе над одной моделью.

**Ревизия — отпечаток имени и модели, а не ``updated_at``.** ``updated_at`` отвечает на
вопрос «писали ли что-нибудь в строку», а не «менялось ли содержимое». Финализация пишет
в строку статус и снимок ревью, и onupdate сдвигает ``updated_at``, хотя модель прежняя:
версия по нему давала бы 409 «кто-то сохранил» тому, кто правит, пока коллега
финализирует. (Сводку расчёта от того же сдвига уже защищает явный core-update с
``updated_at = Project.updated_at`` — однажды об onupdate здесь уже обжигались.)
Отпечаток меняется ровно тогда, когда меняется то, что можно потерять, и считается тем
же ``crud.model_hash``, что у гейта финализации, — миграции нет.

Совпадение содержимого конфликтом не считается: если кто-то сохранил ровно то же самое,
терять нечего.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import crud
from .timefmt import when_utc

#: Действия журнала, которые меняют модель. По ним отказ находит того, кто сохранил
#: раньше. Создание и дубль дают новый объект, финализация модели не меняет.
MODEL_ACTIONS: dict[str, tuple[str, ...]] = {
    "project": ("project.update", "project.version_restore"),
    "case": ("case.update", "case.version_restore"),
}

#: Род у проекта и дела разный: «проект изменён, он сохранён» и «дело изменено, оно
#: сохранено». Одна формулировка на оба дала бы ошибку в каждом втором отказе.
_PHRASES = {
    "project": {"changed": "Проект изменён", "saved": "он сохранён"},
    "case": {"changed": "Дело изменено", "saved": "оно сохранено"},
}


def revision_of(name: str, model: dict) -> str:
    """Ревизия содержимого: меняется вместе с именем или моделью и только с ними."""
    return crud.model_hash({"name": name, "model": model})


def conflict_message(db: Session, org_id: str, kind: str, entity_id: str) -> str:
    """Почему правка не записана — **кто и когда** сохранил раньше, если журнал это знает.

    Глагол не спрягается по роду автора: о человеке в журнале известен только адрес, и
    «сохранил»/«сохранила» было бы догадкой. Поэтому — страдательный залог.
    """
    phrase = _PHRASES[kind]
    entry = crud.last_log_entry(db, org_id, entity_id, MODEL_ACTIONS[kind])
    if entry is None:
        return (f"{phrase['changed']} после того, как вы его открыли; кто это сделал, "
                "журнал не называет. Ваши правки не записаны.")
    who = entry.actor_email or "системное действие"
    if entry.via_key:
        who += f", через ключ API «{entry.via_key}»"
    how = ("в нём восстановлена версия" if entry.action.endswith("version_restore")
           else phrase["saved"])
    return (f"{phrase['changed']} после того, как вы его открыли: {how} ({who}, "
            f"{when_utc(entry.created_at)}). Ваши правки не записаны.")


def ensure_fresh(db: Session, org_id: str, kind: str, entity_id: str, *,
                 current: str, expected: str | None) -> None:
    """Отказать 409, если клиент правил устаревшую версию.

    ``expected=None`` — клиент версии не прислал: прежнее поведение (перезапись). Это
    оставлено ради ключей API и скриптов, написанных до G2, и сказано в описании маршрута;
    интерфейс продукта присылает версию всегда.
    """
    if expected is None or expected == current:
        return
    raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                        detail=conflict_message(db, org_id, kind, entity_id))
