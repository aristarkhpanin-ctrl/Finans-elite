"""Тесты защиты секрета JWT (fail-fast в production)."""
import pytest

from app.security import _MIN_SECRET_LEN, _require_secure_secret

_STRONG = "x" * _MIN_SECRET_LEN


def test_dev_env_allows_any_secret():
    # Вне production заглушка допустима — разработке не мешаем.
    _require_secure_secret("development", "dev-secret-change-me")
    _require_secure_secret("", None)


@pytest.mark.parametrize("bad", ["", None, "dev-secret-change-me", "change-me-in-production", "short"])
def test_production_rejects_insecure_secret(bad):
    with pytest.raises(RuntimeError):
        _require_secure_secret("production", bad)


def test_production_accepts_strong_secret():
    _require_secure_secret("production", _STRONG)
    _require_secure_secret("PRODUCTION", _STRONG + "-extra")  # регистронезависимо
