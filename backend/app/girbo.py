"""Запрос к ГИР БО: поиск по ИНН, карточка организации, её отчётность (пакет L, L3).

Разбор ответа и сопоставление строк — в ``audit_core/girbo.py`` (чисто, без сети); здесь —
только дорога туда и обратно.

* **Адрес один** — ресурс ФНС, его задаёт владелец установки (``GIRBO_BASE_URL``; по
  умолчанию ``bo.nalog.gov.ru`` — ресурс однажды уже переезжал с ``bo.nalog.ru``, и
  второй переезд не должен требовать выпуска продукта). Платформа не ходит по адресам,
  которые прислал пользователь: в запросе только ИНН, проверенный до отправки.
* **Недоступность — отказ с причиной**, а не пустая отчётность: пустая выглядела бы как
  «у организации ничего нет».
* Выключается ``GIRBO_ENABLED=0`` — например, если установке запрещены внешние запросы;
  тогда кнопка в деле говорит, почему её нет, а отчётность вводится из Excel.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from audit_core.girbo import clean
from audit_core.requisites import valid_inn

from .env import env

DEFAULT_BASE = "https://bo.nalog.gov.ru"
#: Секунды на каждый из трёх запросов: ресурс ФНС бывает медленным, а человек ждёт.
TIMEOUT = 20

Fetch = Callable[[str], Any]


class GirboError(Exception):
    """Загрузка не удалась: статус ответа и причина словами."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def enabled() -> bool:
    return os.getenv("GIRBO_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def base_url() -> str:
    return env("GIRBO_BASE_URL", DEFAULT_BASE).rstrip("/")


def _get(url: str) -> Any:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True,
                         headers={"Accept": "application/json",
                                  "User-Agent": "finans-audit (bo import)"})
    response.raise_for_status()
    return response.json()


UNAVAILABLE = ("Ресурс ГИР БО сейчас не отвечает. Попробуйте позже или загрузите "
               "отчётность из Excel — шаблон на этой же вкладке.")


def fetch(inn: str, *, get: Fetch | None = None) -> tuple[dict, list[dict], list[str]]:
    """Карточка организации, её отчётности и оговорки поиска.

    ``get`` подменяется в тестах: сеть в тестах — источник хрупкости и молчаливой
    зависимости от чужой доступности.
    """
    if not enabled():
        raise GirboError(503, "Загрузка отчётности из ГИР БО на этой установке выключена "
                              "(GIRBO_ENABLED=0). Отчётность вводится из Excel или руками.")
    inn = inn.strip()
    if not valid_inn(inn):
        raise GirboError(422, f"ИНН «{inn}» не проходит проверку контрольной цифры — "
                              "проверьте, нет ли опечатки.")
    get = get or _get
    base = base_url()
    try:
        found = get(f"{base}/advanced-search/organizations/search?query={inn}&page=0")
        matches = [c for c in (found or {}).get("content") or [] if clean(c.get("inn")) == inn]
        if not matches:
            raise GirboError(404, f"Организации с ИНН {inn} в ГИР БО нет: отчётность не "
                                  "сдавалась, сдана под другим ИНН или доступ к ней в "
                                  "ресурсе ограничен.")
        notes: list[str] = []
        if len(matches) > 1:
            notes.append(f"С ИНН {inn} в ресурсе {len(matches)} записи — взята та, у которой "
                         "отчётность свежее.")
        matches.sort(key=lambda c: str(((c.get("bfo") or {}).get("period")) or ""),
                     reverse=True)
        org_id = matches[0]["id"]
        org = get(f"{base}/nbo/organizations/{org_id}")
        reports = get(f"{base}/nbo/organizations/{org_id}/bfo/")
    except GirboError:
        raise
    except Exception as exc:                       # noqa: BLE001 — любой сбой сети = «недоступен»
        raise GirboError(503, UNAVAILABLE) from exc
    if not isinstance(org, dict) or not isinstance(reports, list):
        raise GirboError(503, UNAVAILABLE)
    return org, reports, notes
