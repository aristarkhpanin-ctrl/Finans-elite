"""Второй фактор: одноразовые коды из приложения (TOTP, RFC 6238) — C2.

Реализовано на стандартной библиотеке. Это **не изобретение криптографии**: TOTP — это
HMAC-SHA1 от номера временного окна плюс усечение, всё описано в RFC 6238 и умещается в
двадцать строк. Тянуть ради них зависимость, которая однажды устареет и которую придётся
обновлять вместе с ней, смысла нет — тот же довод, по которому у продукта свои графики и
свой разбор строки браузера.

**Резервные коды обязательны, а не «по желанию».** Почты у платформы нет, значит и письма
«восстановите доступ» не будет: потерянный телефон без кодов означал бы потерянную
учётную запись. Коды показываются **один раз** и хранятся отпечатками — по той же
причине, по которой не хранится пароль.

Отпечаток кода — SHA-256, а не Argon2, и это осознанно. Медленный хэш нужен там, где
секрет **угадывают** по словарю; резервный код — 100 бит случайности, его не угадывают, а
медленная проверка десяти кодов подряд превратила бы вход в ожидание.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

#: Длина секрета в байтах. 20 = 160 бит, как в RFC 4226; столько же генерируют
#: приложения-аутентификаторы, и совместимость с ними здесь важнее «побольше».
SECRET_BYTES = 20

#: Шаг окна и длина кода — значения по умолчанию RFC 6238. Менять их нельзя не потому,
#: что нельзя, а потому что приложение пользователя о них не узнает: он введёт код,
#: который у нас не сойдётся, и решит, что сломалась платформа.
STEP_SECONDS = 30
CODE_DIGITS = 6

#: Сколько соседних окон принимать. Одно в каждую сторону — это ±30 секунд на расхождение
#: часов телефона и сервера. Больше означало бы продлевать жизнь подсмотренному коду.
DRIFT_STEPS = 1

#: Сколько резервных кодов выдаём и какой длины. Десять — чтобы хватило на несколько
#: потерянных телефонов; 20 знаков base32 = 100 бит, подобрать нельзя.
RECOVERY_COUNT = 10
_RECOVERY_BYTES = 13
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def new_secret() -> str:
    """Секрет в base32 — в таком виде его читают приложения-аутентификаторы."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()  # noqa: S324
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** CODE_DIGITS)).zfill(CODE_DIGITS)


def code_at(secret: str, moment: float | None = None) -> str:
    """Код, действующий в этот момент, — им же проверяется наша собственная реализация."""
    return _hotp(secret, int((moment if moment is not None else time.time()) // STEP_SECONDS))


def verify(secret: str, code: str, moment: float | None = None) -> bool:
    """Совпал ли код с одним из принимаемых окон.

    Сравнение — ``compare_digest``: обычное сравнение строк заканчивается на первом
    несовпавшем знаке, и по времени ответа код можно подбирать посимвольно.
    """
    cleaned = "".join(ch for ch in (code or "") if ch.isdigit())
    if not secret or len(cleaned) != CODE_DIGITS:
        return False
    now = int((moment if moment is not None else time.time()) // STEP_SECONDS)
    return any(hmac.compare_digest(_hotp(secret, now + shift), cleaned)
               for shift in range(-DRIFT_STEPS, DRIFT_STEPS + 1))


def otpauth_uri(secret: str, email: str, issuer: str = "Финанс") -> str:
    """Ссылка ``otpauth://`` — её читает приложение при настройке.

    Имя издателя попадает в список приложения: без него у человека с тремя аккаунтами
    будет три строки «неизвестно», и он не поймёт, какой код куда.
    """
    label = quote(f"{issuer}:{email}", safe="")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={CODE_DIGITS}&period={STEP_SECONDS}")


def format_secret(secret: str) -> str:
    """Ключ группами по четыре — его вводят руками, и сплошная строка из 32 знаков
    набирается с ошибкой примерно всегда."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


def new_recovery_codes() -> list[str]:
    """Свежий набор резервных кодов — в том виде, в каком их увидит человек."""
    out = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(20))
        out.append(f"{raw[:5]}-{raw[5:10]}-{raw[10:15]}-{raw[15:]}")
    return out


def hash_code(code: str) -> str:
    """Отпечаток резервного кода. Пробелы и регистр не считаются: код переписывают с
    бумажки, и отказать из-за строчной буквы значило бы потерять доступ на ровном месте."""
    normalized = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return hashlib.sha256(normalized.encode()).hexdigest()


def take_recovery_code(stored: list[str], code: str) -> list[str] | None:
    """Использовать код: вернуть оставшиеся отпечатки либо ``None``, если не подошёл.

    Использованный код **удаляется**: одноразовость — весь смысл резервного кода,
    иначе подсмотренный на бумажке код работает вечно.
    """
    digest = hash_code(code)
    if digest not in (stored or []):
        return None
    remaining = list(stored)
    remaining.remove(digest)
    return remaining
