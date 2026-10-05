"""Перечень обрабатываемых персональных данных (пакет L, L11) — из кода, а не по памяти.

Политика обработки ПД (L5) называет **категории** (`legal.PD_CATEGORIES`): что, зачем,
на каком основании и сколько хранится. Здесь — **где именно** это лежит: каждый столбец
базы, в котором бывают персональные данные, отнесён к категории политики. Перечень
стережёт тест в обе стороны: столбец с «подозрительным» именем, не названный ни здесь,
ни в :data:`NOT_PD` с причиной, роняет его — как и строка о столбце, которого нет, или о
категории, которой нет в политике. Документ `docs/PD-INVENTORY.md` собирается отсюда
(`scripts/pd_inventory.py`) — основа для уведомления Роскомнадзора об обработке ПД.

Свободный текст (названия проектов, модели, реплики) отнесён к персональным данным
**возможным**: платформа не знает, что в нём, и честнее назвать его, чем пообещать, что
там ничего нет.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import legal

ACCOUNT = "Учётная запись"
MEMBERSHIP = "Участие в организациях"
SESSIONS = "Входы в учётную запись"
JOURNAL = "Журнал действий организации"
COMMENTS = "Обсуждения"
EVENTS = "События пользования"
PAYMENTS = "Платежи"
CONTENT = "Данные, которые вы вводите в модели"
STAFF = "Сотрудники платформы"

#: Категории вне публичной политики — с причиной, почему их там нет.
INTERNAL_CATEGORIES: dict[str, str] = {
    STAFF: "служебный журнал и признаки сотрудников самой платформы: их данные "
           "обрабатываются в рамках трудовых отношений, а не договора с клиентом, и в "
           "политику для клиентов не входят",
}


@dataclass(frozen=True)
class PdField:
    #: «таблица.столбец».
    column: str
    category: str
    note: str = ""


FIELDS: tuple[PdField, ...] = (
    # Учётная запись
    PdField("users.email", ACCOUNT),
    PdField("users.full_name", ACCOUNT),
    PdField("users.hashed_password", ACCOUNT, "отпечаток пароля (argon2), сам пароль не хранится"),
    PdField("users.created_at", ACCOUNT),
    PdField("users.email_verified_at", ACCOUNT),
    PdField("users.totp_secret", ACCOUNT, "секрет второго фактора, если включён"),
    PdField("users.totp_enabled_at", ACCOUNT),
    PdField("users.totp_recovery", ACCOUNT, "отпечатки резервных кодов"),
    PdField("users.totp_failures", ACCOUNT, "счётчик неверных кодов — защита от подбора"),
    PdField("users.totp_locked_until", ACCOUNT),
    PdField("users.comment_emails", ACCOUNT, "согласие на письма об обсуждениях"),
    PdField("users.pd_consent_at", ACCOUNT),
    PdField("users.pd_consent_edition", ACCOUNT),
    PdField("users.terms_accepted_at", ACCOUNT),
    PdField("users.terms_edition", ACCOUNT),
    PdField("users.blocked_at", ACCOUNT, "блокировка учётной записи платформой"),
    PdField("users.blocked_by", ACCOUNT, "кто заблокировал — адрес сотрудника платформы"),
    PdField("users.block_reason", ACCOUNT),
    # Участие в организациях
    PdField("memberships.user_id", MEMBERSHIP),
    PdField("memberships.role", MEMBERSHIP),
    PdField("memberships.created_at", MEMBERSHIP),
    PdField("memberships.last_seen_at", MEMBERSHIP, "не чаще раза в час"),
    PdField("memberships.blocked_at", MEMBERSHIP),
    PdField("memberships.blocked_by", MEMBERSHIP, "адрес администратора"),
    PdField("memberships.block_reason", MEMBERSHIP),
    # Входы
    PdField("user_sessions.user_id", SESSIONS),
    PdField("user_sessions.created_at", SESSIONS),
    PdField("user_sessions.last_seen_at", SESSIONS),
    PdField("user_sessions.expires_at", SESSIONS),
    PdField("user_sessions.revoked_at", SESSIONS),
    PdField("user_sessions.user_agent", SESSIONS, "как прислал браузер"),
    PdField("user_sessions.ip", SESSIONS, "IP-адрес, как его увидел сервер или прокси"),
    # Журнал и отметки автора у объектов
    PdField("audit_log.user_id", JOURNAL),
    PdField("audit_log.actor_email", JOURNAL, "остаётся и после ухода человека"),
    PdField("audit_log.entity_name", JOURNAL, "у действий над участником — его адрес"),
    PdField("audit_log.details", JOURNAL, "свободный текст действия"),
    PdField("audit_log.via_key", JOURNAL, "имя ключа API, через который сделана запись"),
    PdField("api_keys.created_by", JOURNAL, "кто выпустил ключ"),
    PdField("api_keys.created_by_id", JOURNAL),
    PdField("api_keys.revoked_by", JOURNAL),
    PdField("share_links.created_by", JOURNAL, "кто отправил план по ссылке"),
    PdField("share_links.revoked_by", JOURNAL),
    PdField("support_grants.granted_by", JOURNAL, "кто открыл доступ поддержке"),
    PdField("support_grants.granted_by_email", JOURNAL),
    PdField("org_branding.updated_by", JOURNAL, "кто поставил логотип"),
    PdField("audit_checklists.author_email", JOURNAL),
    PdField("billing_documents.created_by", JOURNAL, "кто запросил счёт"),
    # Обсуждения
    PdField("comments.author_id", COMMENTS),
    PdField("comments.author_email", COMMENTS),
    PdField("comments.author_name", COMMENTS),
    PdField("comments.body", COMMENTS, "текст реплики"),
    PdField("comments.mentions", COMMENTS, "адреса упомянутых коллег"),
    PdField("comments.resolved_by", COMMENTS),
    PdField("comments.deleted_by", COMMENTS),
    PdField("comment_subscriptions.user_id", COMMENTS, "отписка от ветки"),
    PdField("comment_subscriptions.muted_at", COMMENTS),
    PdField("comment_subscriptions.last_notified_at", COMMENTS, "пауза между письмами"),
    # События пользования
    PdField("usage_events.actor", EVENTS, "отпечаток адреса с солью, не сам адрес"),
    # Платежи и документы
    PdField("organizations.legal_name", PAYMENTS,
            "реквизиты покупателя; у индивидуального предпринимателя — его ФИО"),
    PdField("organizations.inn", PAYMENTS, "у ИП — его ИНН"),
    PdField("organizations.legal_address", PAYMENTS),
    PdField("subscriptions.payment_method_title", PAYMENTS,
            "подпись способа оплаты от провайдера (например, маска карты); номера карты нет"),
    PdField("billing_documents.buyer", PAYMENTS, "снимок реквизитов покупателя в счёте и акте"),
    # Свободный текст организации
    PdField("projects.name", CONTENT),
    PdField("projects.model", CONTENT),
    PdField("project_versions.label", CONTENT),
    PdField("project_versions.model", CONTENT),
    PdField("audit_subjects.name", CONTENT),
    PdField("audit_subjects.model", CONTENT, "в т. ч. подписанты заключения и реквизиты цели"),
    PdField("audit_subject_versions.label", CONTENT),
    PdField("audit_subject_versions.model", CONTENT),
    PdField("audit_groups.name", CONTENT),
    PdField("audit_groups.model", CONTENT),
    PdField("holdings.name", CONTENT),
    PdField("audit_checklists.name", CONTENT),
    PdField("audit_checklists.items", CONTENT),
    PdField("industry_benchmarks.source", CONTENT, "кто назвал ориентир"),
    PdField("share_links.label", CONTENT, "для кого ссылка — бывает имя человека"),
    PdField("organizations.name", CONTENT, "название организации — бывает ФИО"),
    PdField("org_branding.logo", CONTENT, "изображение, выбранное организацией"),
    # Сотрудники платформы
    PdField("users.is_staff", STAFF),
    PdField("users.staff_role", STAFF),
    PdField("staff_log.user_id", STAFF),
    PdField("staff_log.actor_email", STAFF),
    PdField("staff_log.details", STAFF),
    PdField("organizations.suspended_by", STAFF, "адрес сотрудника, приостановившего организацию"),
    PdField("organizations.suspend_reason", STAFF),
)

#: Столбцы с «подозрительным» именем, в которых персональных данных нет, — с причиной.
NOT_PD: dict[str, str] = {
    "users.is_demo": "признак демо-входа: учётная запись общая и человеку не принадлежит",
    "audit_log.entity_type": "вид объекта, не сведения о человеке",
    "billing_documents.seller": "реквизиты продавца — самой платформы",
    "staff_log.organization_name": "название организации-клиента в служебном журнале",
    "holdings.last_consolidation_npv": "число свода",
    "usage_events.context": "закрытый перечень ключей: продукт, шаблон, источник, тариф",
    "org_branding.logo_mime": "тип изображения",
    "api_keys.name": "название ключа, которое дала организация (служебное)",
    "subscriptions.renew_error": "текст ошибки провайдера оплаты",
    "support_grants.reason": "зачем открыт доступ (служебное)",
    "comments.anchor_label": "подпись места в продукте",
    "share_links.version_id": "ссылка на версию",
    "billing_documents.plan_name": "название тарифа",
    "org_branding.logo_width": "размер изображения",
    "org_branding.logo_height": "размер изображения",
    "organizations.is_demo": "признак демонстрационной организации",
    "payments.auto_renew_consent": "отметка согласия организации на автопродление (о платеже, не о человеке)",
}

#: Имена столбцов, в которых бывают персональные данные. Совпавший столбец обязан быть
#: назван в :data:`FIELDS` или :data:`NOT_PD`.
SUSPECT = re.compile(
    r"(email|name|_by$|author|actor|^ip$|user_agent|phone|address|^inn$|reason|label|"
    r"^body$|mentions|^model$|details|secret|password|recovery|consent|terms|seen_at|"
    r"user_id|logo|buyer|seller|^source$|^items$|payment_method_title|context|"
    r"is_staff|staff_role|is_demo|totp|via_key|comment_emails)")


def categories() -> dict[str, legal.PdCategory | None]:
    """Категории перечня: из политики (с её текстом) и служебные (``None``)."""
    out: dict[str, legal.PdCategory | None] = {c.what: c for c in legal.PD_CATEGORIES}
    out.update({name: None for name in INTERNAL_CATEGORIES})
    return out


def render() -> str:
    """Документ `docs/PD-INVENTORY.md`."""
    cats = categories()
    lines = [
        "# Перечень обрабатываемых персональных данных",
        "",
        "> Собрано командой `python backend/scripts/pd_inventory.py` из "
        "`backend/app/pd_inventory.py` и категорий политики обработки ПД "
        "(`backend/app/legal.py`). Руками не правится: правится код, файл пересобирается; "
        "свежесть сверяет тест `test_pd_inventory.py`, а столбец базы с персональными "
        "данными, не названный в перечне, роняет его.",
        "",
        "Где лежат данные: база PostgreSQL установки, резервные копии базы (том `backups`) "
        "и выгрузки, которые человек или организация забирает сами. Место размещения "
        "сервера — `[заполняет владелец установки]`; по ч. 5 ст. 18 152-ФЗ запись, "
        "систематизация, накопление и хранение ПД граждан РФ ведутся с использованием баз "
        "данных на территории РФ (`docs/HOSTING-CHECKLIST.md`).",
        "",
    ]
    for name, category in cats.items():
        fields = [f for f in FIELDS if f.category == name]
        lines += [f"## {name}", ""]
        if category is not None:
            lines += [
                f"- **Что:** {category.data}.",
                f"- **Зачем:** {category.purpose}.",
                f"- **Основание:** {category.basis}.",
                f"- **Срок:** {category.kept}.",
            ]
        else:
            lines += [f"- **Вне публичной политики:** {INTERNAL_CATEGORIES[name]}."]
        lines += ["", "| Столбец | Примечание |", "|---|---|"]
        lines += [f"| `{f.column}` | {f.note} |" for f in fields]
        lines.append("")
    lines += [
        "## Для уведомления Роскомнадзора",
        "",
        "Уведомление об обработке ПД (ст. 22 152-ФЗ) подаёт оператор — владелец установки — "
        "до начала обработки. Из перечня выше берутся категории данных, цели и основания; "
        "остальное:",
        "",
        "- **Категории субъектов:** пользователи — сотрудники организаций-клиентов; лица, "
        "чьи данные клиенты вводят в модели и дела (по поручению клиента, ч. 3 ст. 6).",
        "- **Действия с данными:** сбор, запись, систематизация, накопление, хранение, "
        "уточнение, извлечение, использование, передача (предоставление доступа "
        "участникам организации), обезличивание (события пользования, удаление учётной "
        "записи), блокирование, удаление, уничтожение.",
        "- **Способ обработки:** автоматизированный, с передачей по сети интернет "
        "(TLS на обратном прокси установки).",
        "- **Меры защиты, которые делает код:** пароли — отпечатки argon2; второй фактор "
        "(TOTP); реестр входов с отзывом; изоляция организаций на уровне строк базы "
        "(RLS) под ролью приложения без прав суперпользователя; журнал действий; "
        "вычистка персональных данных из отчётов об ошибках до отправки; согласие "
        "отдельной отметкой с редакцией и временем; выгрузка и удаление своих данных.",
        "- **Трансграничная передача:** по умолчанию нет. Включаемые владельцем службы: "
        "трекер ошибок (`SENTRY_DSN` — данные вычищаются до отправки; можно развернуть у "
        "себя), проверка пароля по утечкам (`PWNED_CHECK` — уходят 5 знаков хэша, не "
        "пароль и не адрес).",
        "- **Дата начала обработки, ответственный за организацию обработки, место "
        "размещения базы:** `[заполняет владелец установки]`.",
        "",
    ]
    return "\n".join(lines)
