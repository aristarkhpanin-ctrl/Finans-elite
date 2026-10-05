"""Каждое действие журнала организации клиент читает словами, а не кодом.

Найдено в G5: журнал показывал клиенту **36** действий машинными кодами —
``staff.org_view`` (к вам заходила платформа), ``support.project_view`` (поддержка
открыла вашу модель по гранту), ``auth.totp_disabled``, ``billing.overdue``… Экран
подписывает действия словарём ``ACTION`` в ``AuditLogTab.tsx`` и незнакомый код
показывает как есть, — а словарь не пополнялся с фазы A2. Самые важные для клиента
записи (приход постороннего, чтение его чисел) читались хуже всех: ради них журнал и
заводили.

Перечень сверяется в обе стороны: действие, которое пишется в журнал организации, обязано
иметь подпись; подпись без действия — ложь о продукте (её однажды прочтут как «так
бывает»). Действия берутся **разбором кода** (``ast``), а не поиском по тексту: вызов
на трёх строках или действие из условного выражения поиск по строке пропустил бы молча.

Тест стоит в бэкенде намеренно: тот, кто заводит новое действие, узнаёт о подписи
сразу, а не когда клиент спросит, что значит ``billing.auto_renew_off``.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
LABELS = ROOT / "frontend" / "src" / "pages" / "org" / "AuditLogTab.tsx"

#: Функции, которые пишут журнал **организации**, и позиция действия среди аргументов.
#: ``log_staff_action`` сюда не входит: служебный журнал читают сотрудники платформы.
_WRITERS = {"log_action": 3, "log_user_action": 2}


def _strings(node: ast.AST) -> list[str]:
    """Строковые константы выражения: ``"a.b"`` и ``"a.b" if x else "a.c"``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _strings(node.body) + _strings(node.orelse)
    return []


def _name(func: ast.AST) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def backend_actions() -> set[str]:
    """Действия, которые код пишет в журнал организации."""
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = _name(node.func)
            if name in _WRITERS and len(node.args) > _WRITERS[name]:
                found.update(_strings(node.args[_WRITERS[name]]))
            # Отложенная запись (D1): ``background.add_task(send_and_log, …, action)``.
            if (name == "add_task" and node.args and _name(node.args[0]) == "send_and_log"):
                found.update(_strings(node.args[-1]))
    return {a for a in found if re.fullmatch(r"[a-z_]+\.[a-z_]+", a)}


def frontend_labels() -> set[str]:
    """Ключи словаря ``ACTION`` на экране журнала."""
    text = LABELS.read_text()
    block = text[text.index("const ACTION"):text.index("};", text.index("const ACTION"))]
    return set(re.findall(r'"([a-z_]+\.[a-z_]+)":', block))


def test_the_scan_is_not_blind():
    """Сторож самой выборки: пустой разбор сделал бы оба теста ниже зелёными."""
    actions = backend_actions()
    assert len(actions) > 60, f"действий журнала подозрительно мало: {len(actions)}"
    assert {"project.update", "staff.org_view", "auth.login",
            "comment.mention_mail"} <= actions


def test_every_journal_action_has_a_label():
    missing = sorted(backend_actions() - frontend_labels())
    assert missing == [], (
        "эти действия пишутся в журнал организации, а клиент увидит их кодом — добавьте "
        "подпись в ACTION (frontend/src/pages/org/AuditLogTab.tsx): " + ", ".join(missing))


def test_no_label_outlives_its_action():
    stale = sorted(frontend_labels() - backend_actions())
    assert stale == [], ("подписи к действиям, которых код больше не пишет, — уберите: "
                         + ", ".join(stale))
