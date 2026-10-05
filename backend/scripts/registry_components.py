"""Перечень сторонних компонентов для заявки в реестр российского ПО (пакет L, L10).

Собирается **из зависимостей**, а не пишется руками: перечень, который ведут руками,
отстаёт от кода с первой же новой зависимостью, а заявка с неполным перечнем хуже, чем
без него. Свежесть стережёт ``tests/test_registry_components.py``: сверяется **состав**
(имена прямых зависимостей, образов и шрифтов) — лицензии и установленные версии в
сверку не входят, они читаются из того, что установлено на машине сборки.

Источники: ``backend/pyproject.toml`` (лицензия — из метаданных установленного пакета),
``frontend/package.json`` (лицензия — из ``node_modules``), ``docker-compose.yml`` и
Dockerfile (образы), ``frontend/src/assets/fonts`` (шрифт в сборке).

Запуск: ``python backend/scripts/registry_components.py`` — пишет
``docs/registry/05-components.md``; ``--check`` — только сверка состава.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "registry" / "05-components.md"
PYPROJECT = ROOT / "backend" / "pyproject.toml"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
NODE_MODULES = ROOT / "frontend" / "node_modules"
COMPOSE = ROOT / "docker-compose.yml"
DOCKERFILES = (ROOT / "backend" / "Dockerfile", ROOT / "frontend" / "Dockerfile")
FONTS = ROOT / "frontend" / "src" / "assets" / "fonts"

#: Лицензии образов контейнеров: метаданных у образа нет, поэтому строка — здесь. Новый
#: образ без строки роняет тест — лицензию называют до того, как образ попадёт в поставку.
IMAGE_LICENSES: dict[str, tuple[str, str]] = {
    "postgres": ("PostgreSQL License", ""),
    "redis": ("BSD-3-Clause до 7.2; RSALv2 / SSPLv1 с 7.4",
              "тег «7-alpine» плавающий и ведёт на 7.4+ — решение до подачи, см. README"),
    "python": ("PSF-2.0", "основа образа сервера"),
    "nginx": ("BSD-2-Clause", "раздача интерфейса"),
    "node": ("MIT", "только сборка интерфейса; в работающую установку не входит"),
}
#: Образы, которые нужны только при сборке и в работающую установку не входят.
BUILD_ONLY_IMAGES = frozenset({"node"})

#: Шрифты в сборке — не пакеты, поэтому названы здесь (лицензия — `fonts/README.md`).
FONT_LICENSES: dict[str, tuple[str, str]] = {
    "satoshi": ("Шрифт Satoshi (Indian Type Foundry)", "ITF Free Font License"),
}

#: Пакеты, которых нет на машине сборки перечня (ставятся только в продакшене):
#: лицензия названа здесь, а не угадана, — и только для таких.
NOT_INSTALLED_HERE = {"psycopg": "LGPL-3.0-only"}

#: Примечания к компонентам поставки, лицензия которых требует слов: копилефт или
#: несвободная. Без примечания такой компонент роняет тест.
NOTES = {
    "psycopg": "драйвер PostgreSQL; подключается как библиотека без изменений — "
               "условия LGPL это допускают",
}


@dataclass(frozen=True)
class Component:
    name: str
    #: Что требует код (``>=2.6``, ``^5.59.0``, тег образа) и что стоит на машине сборки.
    version: str
    license: str
    #: «сервер» · «интерфейс» · «развёртывание».
    where: str
    #: Входит в работающую установку; ``False`` — только разработка, проверки, сборка.
    shipped: bool
    note: str = ""


def _requirement(spec: str) -> tuple[str, str]:
    """``uvicorn[standard]>=0.27`` → (``uvicorn``, ``>=0.27``)."""
    m = re.match(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$", spec)
    if not m:
        raise ValueError(f"не разобрана зависимость: {spec!r}")
    return m.group(1), m.group(3).strip()


def _python_license(name: str) -> tuple[str, str]:
    """Лицензия и установленная версия пакета Python — из его метаданных."""
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        fallback = NOT_INSTALLED_HERE.get(name.lower())
        return (fallback or "не определена — пакет не установлен на машине сборки"), ""
    lic = (meta.get("License-Expression") or "").strip()
    if not lic:
        raw = (meta.get("License") or "").strip().splitlines()
        lic = raw[0][:60] if raw else ""
    if not lic:
        classifiers = [c.rsplit("::", 1)[-1].strip() for c in meta.get_all("Classifier") or []
                       if c.startswith("License ::")]
        lic = classifiers[0] if classifiers else "не определена — проверить"
    return lic, meta.get("Version") or ""


def _python_components() -> list[Component]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    groups = [(project.get("dependencies", []), True)]
    extras = project.get("optional-dependencies", {})
    groups.append((extras.get("prod", []), True))
    groups.append((extras.get("dev", []), False))
    seen: dict[str, Component] = {}
    for specs, shipped in groups:
        for spec in specs:
            name, required = _requirement(spec)
            key = name.lower()
            if key in seen:                  # httpx есть и в основных, и в dev
                continue
            lic, installed = _python_license(name)
            version = required + (f" (проверено на {installed})" if installed else "")
            seen[key] = Component(name, version.strip(), lic, "сервер", shipped,
                                  NOTES.get(key, ""))
    return list(seen.values())


def _npm_components() -> list[Component]:
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    out: list[Component] = []
    for block, shipped in (("dependencies", True), ("devDependencies", False)):
        for name, required in sorted(package.get(block, {}).items()):
            manifest = NODE_MODULES / name / "package.json"
            lic, installed = "не определена — пакеты интерфейса не установлены", ""
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                raw = data.get("license") or data.get("licenses")
                if isinstance(raw, list):
                    raw = " / ".join(str(x.get("type", x)) if isinstance(x, dict) else str(x)
                                     for x in raw)
                elif isinstance(raw, dict):
                    raw = raw.get("type")
                lic = str(raw or "не определена — проверить")
                installed = str(data.get("version") or "")
            version = required + (f" (проверено на {installed})" if installed else "")
            out.append(Component(name, version, lic, "интерфейс", shipped,
                                 NOTES.get(name.lower(), "")))
    return out


def images() -> dict[str, str]:
    """Образы контейнеров: имя → тег. Из ``image:`` композиции и ``FROM`` Dockerfile."""
    found: dict[str, str] = {}
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    for path in DOCKERFILES:
        lines += path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        m = re.match(r"^\s*(?:image:|FROM)\s+([a-z0-9._/\-]+):([A-Za-z0-9._\-]+)", line)
        if m:
            found[m.group(1).rsplit("/", 1)[-1]] = m.group(2)
    return found


def fonts() -> list[str]:
    """Семейства шрифтов в сборке — по именам файлов (``satoshi-400.woff2`` → satoshi)."""
    return sorted({p.name.split("-")[0].lower() for p in FONTS.glob("*.woff2")})


def _image_components() -> list[Component]:
    out = []
    for name, tag in sorted(images().items()):
        lic, note = IMAGE_LICENSES.get(name, ("не определена — назвать в IMAGE_LICENSES", ""))
        out.append(Component(f"{name} (образ)", tag, lic, "развёртывание",
                             name not in BUILD_ONLY_IMAGES, note))
    return out


def _font_components() -> list[Component]:
    out = []
    for family in fonts():
        title, lic = FONT_LICENSES.get(family, (family, "не определена — назвать в FONT_LICENSES"))
        out.append(Component(title, "в сборке", lic, "интерфейс", True,
                             "лежит в сборке, а не грузится со стороннего сервера"))
    return out


def components() -> list[Component]:
    return (_python_components() + _npm_components() + _image_components()
            + _font_components())


def _row(c: Component) -> str:
    cells = [c.name, c.version, c.license, c.where, c.note]
    return "| " + " | ".join(x.replace("|", "\\|") for x in cells) + " |"


def render(items: list[Component]) -> str:
    shipped = [c for c in items if c.shipped]
    dev = [c for c in items if not c.shipped]
    counts = Counter(c.license for c in shipped)
    summary = ", ".join(f"{lic} — {n}" for lic, n in counts.most_common())
    head = "| Компонент | Версия | Лицензия | Где | Примечание |\n|---|---|---|---|---|"
    parts = [
        "# Сторонние компоненты",
        "",
        "> Собрано командой `python backend/scripts/registry_components.py` из "
        "`backend/pyproject.toml`, `frontend/package.json`, `docker-compose.yml`, "
        "Dockerfile и `frontend/src/assets/fonts`. Руками не правится: правится код, файл "
        "пересобирается. Состав сверяет тест `test_registry_components.py`; лицензии и "
        "версии «проверено на» — с машины, где файл собран.",
        "",
        f"Входят в работающую установку: **{len(shipped)}** компонентов. Лицензии: {summary}.",
        f"Только разработка, проверки и сборка: {len(dev)} — в поставку не входят.",
        "",
        "Что из этого следует для заявки — в `README.md` этого каталога, раздел "
        "«Сторонние компоненты».",
        "",
        "## Входят в поставку",
        "",
        head,
        *(_row(c) for c in shipped),
        "",
        "## Только разработка, проверки и сборка",
        "",
        head,
        *(_row(c) for c in dev),
        "",
    ]
    return "\n".join(parts)


def listed_names(text: str) -> set[str]:
    """Имена компонентов из готового файла — для сверки состава."""
    names = set()
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith("| Компонент") \
                and not line.startswith("|---"):
            names.add(line.split("|")[1].strip())
    return names


def main(argv: list[str]) -> int:
    items = components()
    if "--check" in argv:
        expected = {c.name for c in items}
        actual = listed_names(OUT.read_text(encoding="utf-8")) if OUT.exists() else set()
        if expected != actual:
            print("перечень устарел: python backend/scripts/registry_components.py\n"
                  f"нет в файле: {sorted(expected - actual)}\n"
                  f"лишние в файле: {sorted(actual - expected)}")
            return 1
        print("перечень свежий")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(items), encoding="utf-8")
    print(f"перечень → {OUT.relative_to(ROOT)} ({len(items)} компонентов)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
