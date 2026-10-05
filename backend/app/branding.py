"""Логотип организации в документах (пакет L, L9).

Консультант отдаёт план клиенту под своим именем: титул DOCX и шапка печатного бланка
несут логотип организации, а не только марку платформы.

**Это не файловое хранилище**, и три вопроса памятки (OPEN-DECISIONS §6) отвечены для
этого узкого случая — одной картинки на организацию, а не папки файлов:

- **где байты** — в базе, строкой организации (``org_branding``): картинка одна, и
  внешнее хранилище ради неё было бы второй системой, которую надо беречь и чистить;
- **кто платит** — предел: :data:`MAX_LOGO_BYTES` на организацию, и больше одной картинки
  не бывает — новая заменяет прежнюю;
- **что при удалении** — уходит вместе с организацией (``PURGED_WITH_ORGANIZATION``), а до
  того попадает в её выгрузку. Человеку логотип не принадлежит: удаление учётной записи
  его не трогает, как не трогает проекты.

Правила загрузки — каждое с причиной, и причина доходит до человека в отказе:

- **только PNG и JPEG**, по сигнатуре файла, а не по имени или заявленному типу. **SVG
  не принимается**: это текст с разметкой, и в нём бывает исполняемый код, а логотип
  уходит в документы, которые открывают другие люди;
- **метаданные вычищаются**: в PNG — текстовые чанки, EXIF и время, в JPEG — сегменты
  APP1 (EXIF, XMP), APP13 (IPTC) и комментарии. Там бывают имя автора, программа и место
  съёмки, а документ с логотипом уходит третьим лицам;
- **размеры читаются тем же разбором, что у python-docx**: файл, который генератор
  документа не распознает, отклоняется при загрузке, а не роняет выгрузку потом; сторона
  больше :data:`MAX_LOGO_SIDE` пикселей отклоняется — на титуле она не нужна, а в
  браузере печатного бланка дорога.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

from docx.image.exceptions import UnrecognizedImageError
from docx.image.image import Image as DocxImage
from docx.shared import Cm, Length

#: Предел файла логотипа. Логотип едет в каждую копию документа и в каждый бланк печати —
#: тяжёлый файл платили бы все, кто их открывает.
MAX_LOGO_BYTES = 256 * 1024
#: Наибольшая сторона в пикселях.
MAX_LOGO_SIDE = 4000
#: Рамка логотипа на титуле DOCX: пропорции сохраняются, картинка вписывается.
DOCX_BOX = (Cm(5), Cm(2.5))

KINDS = {"image/png": "PNG", "image/jpeg": "JPEG"}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: Чанки PNG, в которых живут сведения о файле, а не картинка.
_PNG_METADATA = frozenset({b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"})
#: Сегменты JPEG со сведениями о файле: APP1 (EXIF, XMP), APP13 (IPTC), COM.
_JPEG_METADATA = frozenset({0xE1, 0xED, 0xFE})
#: Минимальный JFIF-заголовок (APP0, версия 1.1, без миниатюры). Ставится, если после
#: вычистки EXIF у файла не осталось ни JFIF, ни EXIF: без одного из них python-docx
#: JPEG не узнаёт — и документ не собрался бы.
_JFIF_APP0 = (b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")

#: Отказ для SVG — отдельный: «принимаются PNG и JPEG» человек с SVG прочтёт как придирку.
SVG_REFUSAL = ("SVG не принимается: это текст с разметкой, и в нём бывает исполняемый "
               "код, а логотип уходит в документы, которые открывают другие люди. "
               "Сохраните логотип как PNG.")


#: Правила — словами для экрана: экран их показывает, а не пересказывает своими словами
#: (вторая формулировка однажды разошлась бы с проверкой).
RULES = (
    f"PNG или JPEG до {MAX_LOGO_BYTES // 1024} КБ и не больше {MAX_LOGO_SIDE} px по "
    "стороне. SVG не принимается: в нём бывает исполняемый код, а логотип уходит в "
    "документы, которые открывают другие люди.",
    "Метаданные файла — автор, программа, место съёмки — удаляются при загрузке: "
    "документ с логотипом уходит третьим лицам.",
    "Логотип ставится на титул бизнес-плана и заключения (DOCX), в шапку печатного "
    "бланка и на план, открытый по ссылке. Без логотипа документы выходят с маркой "
    "платформы.",
    "Хранится в базе вместе с организацией — это не файловое хранилище: картинка одна, и "
    "новая заменяет прежнюю. Попадает в выгрузку организации и удаляется вместе с ней.",
)


class LogoError(ValueError):
    """Файл не годится в логотип; текст — причина для человека."""


@dataclass(frozen=True)
class Logo:
    """Принятый логотип: байты **после вычистки** и то, что о них нужно документу."""

    data: bytes
    mime: str
    width: int
    height: int

    @property
    def data_url(self) -> str:
        """Готовый адрес для ``<img src>``: картинка мала, и отдельный запрос за ней
        со своим входом стоил бы дороже, чем base64 в ответе."""
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode('ascii')}"


def _kib(size: int) -> str:
    return f"{(size + 1023) // 1024} КБ"


def decode(encoded: str) -> bytes:
    """Base64 из запроса → байты. Пробелы и переносы строк терпятся, остальное — нет."""
    try:
        return base64.b64decode("".join(encoded.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LogoError("Файл пришёл повреждённым: содержимое не читается как base64.") \
            from exc


def sniff(data: bytes) -> str | None:
    """Тип по сигнатуре файла. Имя и заявленный тип не спрашиваются: их задаёт отправитель."""
    if data.startswith(_PNG_SIGNATURE):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _looks_like_svg(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head


def _strip_png(data: bytes) -> bytes:
    """Блоки картинки — да, сведения о файле — нет. Всё после конца картинки (``IEND``)
    отбрасывается: так к логотипу прицепляют посторонние данные, и в документ третьим
    лицам они уехать не должны."""
    out = [_PNG_SIGNATURE]
    pos = len(_PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length                      # длина + тип + данные + CRC
        if end > len(data):
            raise LogoError("PNG обрезан: файл кончается посреди блока данных.")
        if kind not in _PNG_METADATA:
            out.append(data[pos:end])
        pos = end
        if kind == b"IEND":
            return b"".join(out)
    raise LogoError("PNG обрезан: у файла нет конца картинки.")


def _strip_jpeg(data: bytes) -> bytes:
    """Сегменты картинки — да, EXIF/XMP/IPTC и комментарии — нет; хвост после конца
    картинки (``EOI``) отбрасывается, как и у PNG."""
    out = [b"\xff\xd8"]
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise LogoError("JPEG повреждён: структура файла не читается.")
        marker = data[pos + 1]
        if marker == 0xFF:                          # байт-заполнитель перед маркером
            pos += 1
            continue
        if marker == 0xDA:                          # начало сжатых данных — дальше картинка
            eoi = data.rfind(b"\xff\xd9", pos)
            if eoi < 0:
                raise LogoError("JPEG обрезан: у файла нет конца картинки.")
            out.append(data[pos:eoi + 2])
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # маркеры без длины
            out.append(data[pos:pos + 2])
            pos += 2
            continue
        end = pos + 2 + int.from_bytes(data[pos + 2:pos + 4], "big")
        if end > len(data):
            raise LogoError("JPEG обрезан: файл кончается посреди заголовка.")
        if marker not in _JPEG_METADATA:
            out.append(data[pos:end])
        pos = end
    else:
        raise LogoError("JPEG обрезан: в файле нет самой картинки.")
    stripped = b"".join(out)
    if stripped[6:10] not in (b"JFIF", b"Exif"):
        stripped = stripped[:2] + _JFIF_APP0 + stripped[2:]
    return stripped


def accept(data: bytes) -> Logo:
    """Проверить файл и вернуть логотип, готовый к хранению. Отказ — :class:`LogoError`."""
    if not data:
        raise LogoError("Файл пуст.")
    if len(data) > MAX_LOGO_BYTES:
        raise LogoError(
            f"Логотип больше {_kib(MAX_LOGO_BYTES)} ({_kib(len(data))}). Уменьшите файл: "
            "логотип едет в каждую копию документа и в каждый бланк печати.")
    mime = sniff(data)
    if mime is None:
        if _looks_like_svg(data):
            raise LogoError(SVG_REFUSAL)
        raise LogoError("Принимаются PNG и JPEG — этот файл ни то ни другое "
                        "(тип определяется по содержимому, а не по имени файла).")
    clean = _strip_png(data) if mime == "image/png" else _strip_jpeg(data)
    try:
        image = DocxImage.from_blob(clean)
    except UnrecognizedImageError as exc:
        raise LogoError("Файл не читается как изображение: генератор документа его не "
                        "распознал, и логотип не встал бы на титул.") from exc
    except Exception as exc:  # noqa: BLE001 — сбой разбора повреждённого файла — отказ, а не 500
        raise LogoError("Файл не читается как изображение: генератор документа его не "
                        "распознал, и логотип не встал бы на титул.") from exc
    width, height = int(image.px_width), int(image.px_height)
    if width <= 0 or height <= 0:
        raise LogoError("У изображения нет размеров — файл повреждён.")
    if max(width, height) > MAX_LOGO_SIDE:
        raise LogoError(
            f"Изображение {width}×{height} px — больше {MAX_LOGO_SIDE} px по стороне. "
            "На титуле оно не нужно таким, а бланк печати открывался бы медленно.")
    return Logo(data=clean, mime=mime, width=width, height=height)


def docx_size(logo: Logo) -> tuple[Length, Length]:
    """Ширина и высота логотипа на титуле: вписать в :data:`DOCX_BOX`, сохранив пропорции.

    Только ширину python-docx пропорцию сохранил бы и сам, но высокий логотип тогда занял
    бы полстраницы: рамка ограничивает обе стороны."""
    box_w, box_h = DOCX_BOX
    scale = min(box_w / logo.width, box_h / logo.height)
    return Length(int(logo.width * scale)), Length(int(logo.height * scale))


def describe(logo: Logo) -> str:
    """«PNG, 12 КБ, 400×120 px» — для журнала и экрана."""
    return f"{KINDS[logo.mime]}, {_kib(len(logo.data))}, {logo.width}×{logo.height} px"
