"""Как сервер называет момент времени в своих сообщениях — одна функция на всех.

Сообщения сервера (срок гранта поддержки, автор чужой правки) уходят человеку текстом, и
формат у них должен быть один. Раньше функция жила внутри служебного роутера, и второй
модуль, которому понадобилось назвать время, завёл бы свою копию — с другим форматом.

Часовой пояс назван прямо (UTC), а не подразумевается: сервер не знает, где находится
читатель, и «14:05» без пояса у человека в Новосибирске означало бы другое время.
"""
from __future__ import annotations

from datetime import datetime, timezone


def when_utc(moment: datetime) -> str:
    """«05.09.2026 14:05 UTC».

    SQLite отдаёт время без пояса (значения в нём — UTC). ``astimezone`` приняло бы такое
    время за **местное** и сдвинуло бы его на пояс машины, где запущен сервер, — поэтому
    наивное время сначала объявляется тем, чем оно и является.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def day_utc(moment: datetime) -> str:
    """«05.09.2026» — когда важен день, а не минута (запуск по расписанию не обещает
    часа: «следующая попытка — 06.09.2026», а не «в 04:00»)."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).strftime("%d.%m.%Y")
