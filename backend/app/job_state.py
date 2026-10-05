"""Состояние фоновой задачи: что о ней известно и чего мы не знаем (ADMIN-PHASE-F, F3).

`AnalysisJob` хранит только владение (кто завёл, когда, какого рода). Состояние живёт в
Celery, и опросить задачу можно было **только по её идентификатору и только своим
арендатором**. Значит зависшая или упавшая задача не видна никому: ни клиенту (он ушёл с
экрана), ни платформе. Первый зависший Монте-Карло платформа узнаёт от клиента по
телефону.

Два правила, которые здесь важнее самого списка:

1. **Молчание сети — не отказ задачи.** Недоступный брокер даёт ``unknown`` с названной
   причиной, а не ``failure`` и не 500. До этого запрос к упавшему Redis превращался в
   «не удалось загрузить» на экране клиента — то есть в сообщение о поломке продукта
   там, где сломалось соседнее хозяйство.
2. **Истёкший результат — не «в очереди».** Celery хранит результаты
   :data:`RESULT_TTL` (час), после чего `AsyncResult` отвечает ``PENDING`` **для любой**
   задачи, включая давно посчитанную. Старая задача выглядела бы вечно стоящей в
   очереди; здесь она честно названа ``unknown`` — «срок хранения результата истёк».

Функции чистые: время и опрос приходят параметрами, поэтому оба правила проверяются без
брокера.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

#: Celery → наш статус. Прочие состояния (PENDING/RETRY) означают «в очереди».
STATES: dict[str, str] = {"SUCCESS": "success", "FAILURE": "failure", "STARTED": "running"}

#: Сколько Celery хранит результат (`celery_app.conf.result_expires`). Держится рядом с
#: правилом, которое на него опирается: разойдясь, они дали бы «в очереди» там, где
#: задача давно посчитана.
RESULT_TTL = timedelta(hours=1)

UNKNOWN = "unknown"

BROKER_SILENT = ("Состояние неизвестно: хранилище результатов не ответило. Это молчание "
                 "сети, а не отказ задачи — сама задача могла и посчитаться.")

RESULT_EXPIRED = ("Состояние неизвестно: срок хранения результата истёк (час), и Celery "
                  "отвечает о ней так же, как о несуществующей. «В очереди» здесь было "
                  "бы неправдой.")


@dataclass(frozen=True)
class JobState:
    """Что известно о задаче. ``note`` заполняется только у ``unknown`` — и тогда
    обязательно: «неизвестно» без причины неотличимо от поломки."""

    status: str
    error: str = ""
    note: str = ""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def interpret(state: str | None, *, created_at: datetime | None = None,
              now: datetime | None = None, error: str = "") -> JobState:
    """Состояние Celery → наше, с двумя правилами честности.

    ``state is None`` — брокер не ответил: это ``unknown`` с причиной.
    ``PENDING`` у задачи старше :data:`RESULT_TTL` — тоже ``unknown``: Celery отвечает
    так и о посчитанной задаче, чей результат уже удалён.
    """
    if state is None:
        return JobState(UNKNOWN, note=BROKER_SILENT)
    status = STATES.get(state, "pending")
    if status == "failure":
        return JobState(status, error=error)
    if status == "pending" and created_at is not None:
        moment = now or datetime.now(timezone.utc)
        if moment - _aware(created_at) > RESULT_TTL:
            return JobState(UNKNOWN, note=RESULT_EXPIRED)
    return JobState(status)


def poll(job_id: str, fetch: Callable[[str], tuple[str, object]]) -> tuple[str, object]:
    """Опросить задачу, **не падая** из-за чужого хозяйства.

    ``fetch`` возвращает пару «состояние, результат»; любое исключение от него значит
    «брокер не ответил» и превращается в ``(None, None)``. Ловится
    :class:`Exception` целиком осознанно: Redis, kombu и сам Celery бросают свои типы,
    и перечислить их значило бы узнать об очередном только из отчёта об инциденте.
    """
    try:
        return fetch(job_id)
    except Exception:                                    # noqa: BLE001 — см. докстринг
        return (None, None)                              # type: ignore[return-value]


def age_minutes(created_at: datetime, now: datetime | None = None) -> int:
    """Сколько задача живёт. «В очереди 40 минут» — это и есть сигнал."""
    moment = now or datetime.now(timezone.utc)
    return max(0, int((moment - _aware(created_at)).total_seconds() // 60))
