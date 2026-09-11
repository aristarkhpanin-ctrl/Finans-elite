"""Токенизатор и парсер языка формул (SPEC «Язык формул»; решения Q1–Q2 декомпозиции).

Никакого ``eval``: собственный рекурсивный парсер с жёсткими лимитами (длина, число узлов,
глубина) — формулы приходят от пользователя. AST — кортежи:
``("num", Decimal) | ("ident", str) | ("call", имя, [аргументы]) | ("bin", op, l, r) |
("neg", x)``.
"""
from __future__ import annotations

from decimal import Decimal

MAX_LENGTH = 500     # максимальная длина формулы, символов
MAX_NODES = 200      # максимум узлов AST
MAX_DEPTH = 32       # максимальная глубина вложенности


class FormulaError(ValueError):
    """Ошибка разбора или вычисления формулы (сообщение — пользователю)."""


_TWO_CHAR_OPS = ("<=", ">=", "==", "!=")
_ONE_CHAR_OPS = "+-*/^<>"


def _tokenize(text: str) -> list[tuple[str, str]]:
    if len(text) > MAX_LENGTH:
        raise FormulaError(f"Формула длиннее {MAX_LENGTH} символов")
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text[i:i + 2] in _TWO_CHAR_OPS:
            tokens.append(("op", text[i:i + 2]))
            i += 2
            continue
        if ch in _ONE_CHAR_OPS:
            tokens.append(("op", ch))
            i += 1
            continue
        if ch == "(":
            tokens.append(("lparen", ch))
            i += 1
            continue
        if ch == ")":
            tokens.append(("rparen", ch))
            i += 1
            continue
        if ch == ",":
            tokens.append(("comma", ch))
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            seen_dot = False
            while j < n and (text[j].isdigit() or (text[j] == "." and not seen_dot)):
                if text[j] == ".":
                    seen_dot = True
                j += 1
            tokens.append(("num", text[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(("ident", text[i:j].upper()))
            i = j
            continue
        raise FormulaError(f"Недопустимый символ «{ch}» (позиция {i + 1})")
    tokens.append(("eof", ""))
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0
        self.nodes = 0

    def _node(self, node):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise FormulaError(f"Формула сложнее {MAX_NODES} узлов")
        return node

    def _peek(self):
        return self.tokens[self.pos]

    def _next(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str, what: str):
        tok = self._next()
        if tok[0] != kind:
            raise FormulaError(f"Ожидалось {what}, получено «{tok[1] or 'конец формулы'}»")
        return tok

    def parse(self):
        node = self._cmp(0)
        if self._peek()[0] != "eof":
            raise FormulaError(f"Лишний текст после формулы: «{self._peek()[1]}»")
        return node

    def _guard(self, depth: int):
        if depth > MAX_DEPTH:
            raise FormulaError(f"Вложенность глубже {MAX_DEPTH}")

    def _cmp(self, d: int):
        self._guard(d)
        node = self._add(d + 1)
        while self._peek() == ("op", "<") or self._peek() == ("op", ">") or \
                self._peek()[1] in ("<=", ">=", "==", "!="):
            if self._peek()[0] != "op":
                break
            op = self._next()[1]
            node = self._node(("bin", op, node, self._add(d + 1)))
        return node

    def _add(self, d: int):
        self._guard(d)
        node = self._mul(d + 1)
        while self._peek()[0] == "op" and self._peek()[1] in "+-":
            op = self._next()[1]
            node = self._node(("bin", op, node, self._mul(d + 1)))
        return node

    def _mul(self, d: int):
        self._guard(d)
        node = self._unary(d + 1)
        while self._peek()[0] == "op" and self._peek()[1] in "*/":
            op = self._next()[1]
            node = self._node(("bin", op, node, self._unary(d + 1)))
        return node

    def _unary(self, d: int):
        self._guard(d)
        if self._peek() == ("op", "-"):
            self._next()
            return self._node(("neg", self._unary(d + 1)))
        return self._power(d + 1)

    def _power(self, d: int):
        self._guard(d)
        node = self._primary(d + 1)
        if self._peek() == ("op", "^"):
            self._next()
            node = self._node(("bin", "^", node, self._unary(d + 1)))  # правоассоциативно
        return node

    def _primary(self, d: int):
        self._guard(d)
        kind, value = self._next()
        if kind == "num":
            return self._node(("num", Decimal(value)))
        if kind == "ident":
            if self._peek()[0] == "lparen":
                self._next()
                args = []
                if self._peek()[0] != "rparen":
                    args.append(self._cmp(d + 1))
                    while self._peek()[0] == "comma":
                        self._next()
                        args.append(self._cmp(d + 1))
                self._expect("rparen", "«)»")
                return self._node(("call", value, args))
            return self._node(("ident", value))
        if kind == "lparen":
            node = self._cmp(d + 1)
            self._expect("rparen", "«)»")
            return node
        raise FormulaError(f"Неожиданный элемент «{value or 'конец формулы'}»")


def parse(text: str):
    """Разобрать формулу в AST (с лимитами длины/узлов/глубины)."""
    if not text or not text.strip():
        raise FormulaError("Пустая формула")
    return _Parser(_tokenize(text)).parse()
