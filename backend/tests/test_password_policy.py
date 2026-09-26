"""Требования к паролю и проверка по утечкам (ADMIN-DECOMPOSITION.md, C2).

Правило было одно — «не короче 8 символов», — и оно пропускало `12345678`, `qwertyui` и
собственный адрес пользователя, то есть ровно то, с чего начинают подбор.

Половина тестов здесь про то, чего платформа **не** делает: не требует заглавных и
знаков (это даёт `Parol123!`, который не надёжнее и не запоминается), не выдаёт «не
проверили» за «не встречался» и не запирает регистрацию, когда чужой сервис молчит.
"""
from __future__ import annotations

import pytest

from app.password_policy import MIN_LENGTH, check_password, policy_rules
from app.pwned import leaked_count

# --- Правила, работающие всегда ---

def test_good_password_passes():
    assert check_password("тверская-смета-2026", email="ivan@e.ru") == ""
    assert check_password("kofe-i-pyshki", email="ivan@e.ru") == ""


def test_short_password_names_the_length():
    problem = check_password("korotk")
    assert str(MIN_LENGTH) in problem


@pytest.mark.parametrize("password", ["password", "QWERTY123", "12345678", "Пароль",
                                      "йцукенгш", "iloveyou"])
def test_the_most_common_passwords_are_refused(password):
    """Короткий список ловит то, что вводят не задумываясь. Он **не заменяет** проверку
    по утечкам и не притворяется полным: миллионы строк в коде не держат."""
    assert check_password(password) != ""


def test_keyboard_runs_are_refused_in_both_layouts():
    """«Слово + 1234» и «пальцем по ряду» — первое, что перебирают."""
    assert check_password("moloko1234") != ""
    assert check_password("qwerty-moloko") != ""
    assert check_password("молокойцукен") != ""
    # Три символа подряд — не повод отказывать: `abc` встречается в обычных словах.
    assert check_password("abcdefg") != ""          # семь подряд — это ряд
    assert check_password("skladabc-2026") == ""


def test_password_repeating_the_address_is_refused():
    """Адрес знает каждый, кому человек писал: секретом он быть не может."""
    assert check_password("ivanov-parol", email="ivanov@example.ru") != ""
    # Короткая локальная часть не в счёт: иначе «ab» запретило бы половину паролей.
    assert check_password("ab-kakoy-parol", email="ab@example.ru") == ""


def test_single_repeated_character_is_refused():
    assert check_password("ааааааааааа") != ""


def test_composition_is_not_required():
    """Заглавные, цифры и знаки **не требуются** — и это решение, а не упущение.

    Требование состава даёт «Parol123!»: буква требования выполнена, энтропии не
    прибавилось, зато пароль уехал на бумажку под клавиатуру.
    """
    assert check_password("простоцифрыибуквы") == ""
    assert check_password("однистрочныебуквы") == ""
    assert "не требуются" in " ".join(policy_rules(leak_check=False))


def test_rules_do_not_promise_a_check_that_is_off():
    """Обещать проверку по утечкам при выключенной значило бы утверждать, что платформа
    делает то, чего не делает."""
    assert not [r for r in policy_rules(leak_check=False) if "утёкших" in r]
    assert [r for r in policy_rules(leak_check=True) if "утёкших" in r]


# --- Проверка по утечкам ---

def test_leak_check_sends_only_the_prefix():
    """Сам пароль наружу не уходит: отправляются пять знаков отпечатка, сравнение идёт
    у нас. Сервис не узнаёт ни пароля, ни того, какой из тысяч отпечатков наш."""
    seen: list[str] = []

    def fetch(prefix: str) -> str:
        seen.append(prefix)
        # SHA-1 «password» = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
        return "1E4C9B93F3F0682250B6CF8331B7EE68FD8:3730471\r\nAAAAA:1"

    assert leaked_count("password", fetch=fetch, enabled=True) == 3730471
    assert seen == ["5BAA6"]
    assert "password" not in seen[0]


def test_password_not_in_the_range_is_zero_not_none():
    """Ноль означает «в утечках не встречался» — это ответ, а не отсутствие ответа."""
    assert leaked_count("пароль-которого-нет", fetch=lambda _: "AAAA:1\r\nBBBB:2",
                        enabled=True) == 0


def test_unreachable_service_gives_none_not_zero():
    """`None` и ноль — **разные** ответы. Выдать «не проверили» за «не встречался»
    значило бы соврать ровно в ту сторону, в которую врать нельзя."""
    def boom(_: str) -> str:
        raise RuntimeError("нет маршрута")

    assert leaked_count("любой-пароль", fetch=boom, enabled=True) is None


def test_unparseable_answer_is_none_too():
    assert leaked_count("password", enabled=True,
                        fetch=lambda _: "1E4C9B93F3F0682250B6CF8331B7EE68FD8:много") is None


def test_disabled_check_does_not_go_to_the_network():
    """По умолчанию проверка выключена: до сервиса может не быть маршрута вовсе, и
    каждая смена пароля упиралась бы в таймаут."""
    def boom(_: str) -> str:
        raise AssertionError("сеть не должна трогаться")

    assert leaked_count("password", fetch=boom, enabled=False) is None


# --- Двери, где пароль задаётся ---

def test_all_three_doors_use_the_same_rules(client, register):
    """Разные требования в разных дверях — не строгость, а её иллюзия."""
    weak = "qwerty123"
    assert client.post("/api/v1/auth/register", json={
        "email": "n@e.ru", "password": weak, "full_name": "",
        "organization_name": "Орг"}).status_code == 422

    owner = register(email="o@e.ru", org="Орг")
    org = client.get("/api/v1/organizations", headers=owner).json()[0]["id"]
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    assert client.post("/api/v1/auth/activate",
                       json={"token": member["invite_token"],
                             "password": weak}).status_code == 422
    assert client.post("/api/v1/auth/password",
                       json={"current_password": "secret123", "new_password": weak},
                       headers=owner).status_code == 422


def test_refusal_says_what_is_wrong_and_what_to_do(client):
    """«Пароль не подходит» отправляет человека перебирать варианты вслепую — и он
    придёт к чему-нибудь вроде «Parol1234!»."""
    detail = client.post("/api/v1/auth/register", json={
        "email": "n@e.ru", "password": "qwerty123", "full_name": "",
        "organization_name": "Орг"}).json()["detail"]
    assert "Придумайте другой" in detail or "подбирают" in detail


def test_activation_names_the_broken_link_before_the_weak_password(client, register):
    """Недействительная ссылка — беда крупнее слабого пароля, и называется первой."""
    r = client.post("/api/v1/auth/activate", json={"token": "мусор", "password": "qwerty123"})
    assert r.status_code == 400 and "Ссылка" in r.json()["detail"]


def test_policy_endpoint_is_open_and_matches_the_rules(client):
    """Экран берёт требования **с сервера**: перечисленные своим текстом, они однажды
    разойдутся с проверкой, и человек прочтёт одно, а получит другое."""
    policy = client.get("/api/v1/auth/password-policy").json()
    assert policy["min_length"] == MIN_LENGTH
    assert policy["rules"] == policy_rules(leak_check=policy["leak_check"])
