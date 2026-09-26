"""Проверка пароля по базе утечек — по k-анонимному диапазону отпечатка (C2).

**Сам пароль наружу не уходит.** Считается SHA-1, отправляются **первые пять знаков**
отпечатка, в ответ приходят все известные окончания с этим началом — сравнение идёт уже
у нас. Сервис не узнаёт ни пароля, ни того, какой именно из тысяч отпечатков наш.

**Недоступность сервиса не запирает регистрацию.** Внешняя служба может не отвечать —
особенно из России, где до неё может не быть маршрута вовсе. Отказать человеку завести
пароль потому, что чужой сервер молчит, значит поставить свою работу в зависимость от
чужой; поэтому при любой ошибке проверка возвращает ``None`` — «не проверили», а не ноль.
``None`` и ноль здесь **разные ответы**, и путать их нельзя: ноль означает «в утечках не
встречался», а `None` — «мы не знаем».

**По умолчанию выключено.** Включается переменной ``PWNED_CHECK=1`` осознанно — тем, кто
проверил, что маршрут до сервиса есть. Иначе каждая смена пароля упиралась бы в таймаут,
а платформа делала бы вид, что проверяет. Что именно проверяется, экран берёт из
:func:`app.password_policy.policy_rules`, и обещание там появляется только при включённой
проверке.
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable

import httpx

log = logging.getLogger("finans")

PWNED_URL = "https://api.pwnedpasswords.com/range/"
#: Секунды. Короткий: проверка стоит в пути человека, который заводит пароль.
PWNED_TIMEOUT = float(os.getenv("PWNED_TIMEOUT", "2"))


def leak_check_enabled() -> bool:
    """Читается на каждом вызове, а не при импорте: тесты и эксплуатация меняют
    окружение, а модуль импортируется один раз за процесс."""
    return os.getenv("PWNED_CHECK", "").strip().lower() in {"1", "true", "yes", "on"}


def _fetch(prefix: str) -> str:
    """Запрос диапазона. ``Add-Padding`` просит сервис добить ответ пустышками, чтобы по
    его размеру нельзя было судить о нашем запросе."""
    response = httpx.get(f"{PWNED_URL}{prefix}", timeout=PWNED_TIMEOUT,
                         headers={"Add-Padding": "true",
                                  "User-Agent": "finans-elite-password-check"})
    response.raise_for_status()
    return response.text


def leaked_count(password: str, *, fetch: Callable[[str], str] | None = None,
                 enabled: bool | None = None) -> int | None:
    """Сколько раз пароль встречался в утечках; ``None`` — **проверить не удалось**.

    ``fetch`` подменяется в тестах: сеть в тестах — источник хрупкости и молчаливой
    зависимости от чужой доступности.
    """
    if enabled is None:
        enabled = leak_check_enabled()
    if not enabled or not password:
        return None
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324
    prefix, suffix = digest[:5], digest[5:]
    try:
        body = (fetch or _fetch)(prefix)
    except Exception as exc:                     # noqa: BLE001 — любой сбой = «не знаем»
        log.warning("Проверка пароля по утечкам недоступна: %s", exc)
        return None
    for line in body.splitlines():
        tail, _, count = line.partition(":")
        if tail.strip().upper() == suffix:
            try:
                return int(count.strip().replace(",", ""))
            except ValueError:
                # Ответ не разобрался — это «не знаем», а не «не встречался».
                log.warning("Непонятный ответ проверки утечек для диапазона %s", prefix)
                return None
    return 0
