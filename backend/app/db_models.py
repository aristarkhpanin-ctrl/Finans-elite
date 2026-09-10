"""ORM-модели (SQLAlchemy 2.0).

6.1 — проекты; 6.2 — мультиарендность (организации, пользователи, членство; проекты
привязаны к организации). Изоляция данных — по ``organization_id`` (ARCHITECTURE §4).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# JSONB на PostgreSQL, JSON на остальных (SQLite).
JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    """Арендатор (компания-клиент).

    **Приостановка организации — не конфискация данных** (ADMIN-DECOMPOSITION.md, B2).
    Приостановленная организация переходит в режим чтения и выгрузки: свои модели видны
    и выгружаются, новые не заводятся и старые не правятся. Отрезать клиента от
    собственных чисел за неоплату или разбирательство означало бы держать их в
    заложниках.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Когда организацию приостановил **оператор платформы** (нарушение, запрос,
    #: разбирательство). ``None`` — обычная работа. Это отдельное решение человека, а не
    #: следствие статуса подписки: неоплата ограничивает сама по себе и снимается
    #: оплатой, ручная приостановка — только тем, кто её поставил.
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Кто приостановил — текстом, без ссылки: сотрудника могут удалить, а ответ на
    #: вопрос «кто закрыл нам работу» обязан пережить его уход.
    suspended_by: Mapped[str] = mapped_column(String(255), default="", server_default="")
    #: Причина. Показывается **самой организации**: приостановка без объяснения
    #: неотличима от поломки, и клиент пойдёт не в поддержку, а в отзывы.
    suspend_reason: Mapped[str] = mapped_column(String(500), default="", server_default="")


class User(Base):
    """Пользователь. ``hashed_password`` отсутствует у приглашённых (без входа) до активации."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Сотрудник платформы (ADMIN-DECOMPOSITION.md, B1). **Не роль организации**: это
    #: другая ось власти. Роль отвечает на вопрос «что человеку можно в его компании»,
    #: признак сотрудника — «что нам можно у клиентов»; смешать их значило бы выдать
    #: владельцу организации доступ к чужим или наоборот.
    #:
    #: Признак не выдаётся через API — ни своим, ни чужим: маршрут, повышающий права,
    #: сам становится главной мишенью. Ставится скриптом ``scripts/set_staff.py`` тем,
    #: у кого есть доступ к базе.
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False,
                                           server_default=text("false"), nullable=False)
    #: Учётная запись заблокирована **оператором платформы** (B2). В отличие от
    #: приостановки членства (A1) действует сразу на все организации: это про человека,
    #: а не про его место в одной компании, — поэтому право только у оператора.
    #: Администратор организации такого сделать не может и не должен: человек состоит и
    #: в чужих организациях, которые ему не подчиняются.
    blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    blocked_by: Mapped[str] = mapped_column(String(255), default="", server_default="")
    block_reason: Mapped[str] = mapped_column(String(500), default="", server_default="")


class Membership(Base):
    """Членство пользователя в организации с ролью (роли — RBAC, 6.4).

    **Блокируется членство, а не учётная запись** (ADMIN-DECOMPOSITION.md, A1). Человек
    может состоять в двух организациях, и администратор одной не вправе отключать его в
    другой — тот же довод, по которому ему не выдают ссылку сброса пароля участнику
    нескольких организаций. Блокировка всей учётной записи — право оператора платформы.

    ``blocked_at is None`` — доступ обычный; поле пустое у всех существующих участников,
    поэтому изменение инертно. «Заблокирован» и «удалён» — **разные состояния**:
    удаление стирает связь и историю роли, блокировка приостанавливает доступ, называя
    автора, время и причину, и снимается одним действием.
    """

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Когда доступ приостановлен. ``None`` — участник работает как обычно.
    blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Кто приостановил. Ссылки на пользователя нет намеренно: администратора могут
    #: удалить, а ответ на вопрос «кто отстранил» обязан пережить его уход — так же,
    #: как почта актора в журнале.
    blocked_by: Mapped[str] = mapped_column(String(255), default="", server_default="")
    #: Причина. Приостановка без причины неотличима от ошибки администратора — и для
    #: самого участника, которому её покажут, и для того, кто будет её снимать.
    block_reason: Mapped[str] = mapped_column(String(500), default="", server_default="")
    #: Когда участник в последний раз обращался к данным **этой** организации (A3).
    #: Пишется не чаще раза в час: отметка на каждый запрос превратила бы таблицу
    #: членства в счётчик обращений и била бы по каждому чтению. ``None`` — не заходил
    #: ни разу с тех пор, как поле появилось: это «неизвестно», а не «никогда».
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Subscription(Base):
    """Подписка организации на тариф — **своя на каждый продукт платформы**.

    Продукты продаются порознь, поэтому уникальна пара «организация + продукт», а не
    одна организация: общая подписка означала бы, что цена «Аудита» меняется вместе с
    ценой «Элит» и наоборот.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("organization_id", "product", name="uq_org_product"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: "business" («Финанс-Элит») | "audit" («Финанс-Аудит»).
    product: Mapped[str] = mapped_column(String(16), default="business",
                                         server_default="business", nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), default="free")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active/trialing/past_due/canceled
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Payment(Base):
    """Платёж за смену тарифа (для интеграции с провайдером, 6.5b)."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), default="yookassa")
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_rub: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/succeeded/canceled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Holding(Base):
    """Холдинг: группа связанных проектов организации (PIC Holding, 9.3)."""

    __tablename__ = "holdings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Сводка последней консолидации (B3): NPV и ставка группы (строками, как model),
    # момент расчёта. NULL — консолидации ещё не было.
    last_consolidation_npv: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_consolidation_rate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_consolidation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class HoldingMember(Base):
    """Участник холдинга: проект с ролью (parent — головная компания, subsidiary — дочерняя)."""

    __tablename__ = "holding_members"
    __table_args__ = (UniqueConstraint("holding_id", "project_id", name="uq_holding_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    holding_id: Mapped[str] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="subsidiary")  # parent | subsidiary


class Project(Base):
    """Проект финансовой модели: входные данные и результат, принадлежит организации."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная ProjectModel (mode="json": Decimal → строка, даты → ISO).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    # Сводка последнего успешного расчёта (B1). Decimal хранится строкой —
    # как и в model (точность без плавающей запятой). NULL — расчёта не было.
    last_npv: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_irr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_pb_months: Mapped[int | None] = mapped_column(nullable=True)
    last_engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Финализация плана (Ф10, гейт ревью): "draft" | "finalized". Финализация возможна
    # только после ревью; risk-находки требуют явного подтверждения (acknowledge).
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft",
                                        nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SHA-256 канонического JSON модели на момент финализации — детект «дрейфа» (модель
    # изменили после финализации). Снимок ревью — для показа, чем план был подтверждён.
    finalized_model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finalized_review: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class ProjectVersion(Base):
    """Именованный снимок модели проекта (пакет №8, gap 4.4): версии + анализ изменений.

    Хранит полную модель на момент снимка + сводку расчёта (NPV/IRR/движок). Диф двух
    версий (или версии с текущей моделью) считается на лету. Изоляция — по
    ``organization_id`` (RLS + фильтр CRUD), каскадное удаление с проектом.
    """

    __tablename__ = "project_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Сводка расчёта на момент снимка (строки — точность без плавающей запятой); NULL — не считалось.
    npv: Mapped[str | None] = mapped_column(String(64), nullable=True)
    irr_annual: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class IndustryBenchmark(Base):
    """Отраслевой ориентир организации: её собственное число, а не рынок.

    Платформа не собирает статистику сделок и отраслевых медиан не знает — но у фонда
    есть своя история, и сравнить дело с ней честно, пока ориентир **подписан**: кто
    его назвал (``source``) и когда (``updated_at``). Без этих двух полей число на
    экране неотличимо от рыночного.

    Уникальна пара «организация + отрасль + метрика»: два ориентира на одно и то же
    означали бы, что платформа выбирает между ними сама.
    """

    __tablename__ = "industry_benchmarks"
    __table_args__ = (
        UniqueConstraint("organization_id", "industry", "metric", name="uq_org_industry_metric"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    #: ev_ebitda | ev_ebit | ev_revenue — метрика несёт базу, и сравнение идёт по ней.
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 onupdate=_now)


class AuditSubjectVersion(Base):
    """Именованный снимок модели дела: версии проверки и анализ изменений.

    Проверка идёт итерациями: пришли выписки — реестр обязательств изменился, вердикт
    уехал. Комитет спрашивает «что изменилось с прошлой недели» и «какая версия
    подписана», и ответить на это по одной рабочей модели нечем: заключение датировано,
    но воспроизвести его нельзя.

    Хранится **модель на момент снимка** плюс сводка того, что тогда показывал экран
    (вердикт, флаги риска, стоимость доли). Сводка именно хранится, а не пересчитывается:
    она описывает прошлое, и правило дела «числа всегда по текущей отчётности» здесь не
    работает — версия и есть слепок прошлого. Диф считается на лету по двум моделям.

    Изоляция — по ``organization_id`` (RLS + фильтр CRUD), каскад с делом.
    """

    __tablename__ = "audit_subject_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_id: Mapped[str] = mapped_column(
        ForeignKey("audit_subjects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Сводка на момент снимка (строки — точность без плавающей запятой); NULL — не считалось.
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_flags: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equity_value: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditSubject(Base):
    """Субъект анализа финансового состояния (Финанс-Аудит, продукт №2).

    Принадлежит организации; хранит модель субъекта (реквизиты, периоды, фактическая
    отчётность) как JSON — по образцу ``Project.model``. Изоляция арендатора — RLS +
    фильтр CRUD по ``organization_id`` (как projects/holdings).
    """

    __tablename__ = "audit_subjects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная AuditSubjectModel (mode="json": Decimal → строка).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditGroup(Base):
    """Сохранённая группа предприятий (Финанс-Аудит, v2): состав свода + исключения.

    Хранит **состав**, а не результат: свод пересчитывается по текущей отчётности
    участников при каждом анализе. Участник хранится как ``subject_id`` + имя на момент
    сохранения — имя нужно только чтобы назвать удалённого участника (у живых имя берётся
    из самого субъекта). Изоляция арендатора — RLS + фильтр CRUD по ``organization_id``.
    """

    __tablename__ = "audit_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная AuditGroupModel (участники + внутригрупповые обороты).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditLogEntry(Base):
    """Журнал действий: кто, что и когда сделал в организации (152-ФЗ, ARCHITECTURE §4).

    Запись делает тот же запрос, что выполнил действие, сразу после его успеха. Строгой
    атомарности с самим действием нет — CRUD фиксирует транзакцию сам, — и это записано
    здесь честно, а не выдано за гарантию: обещанная в комментарии неразрывность, которой
    в коде нет, опаснее отсутствующей, потому что на неё сошлются при разборе инцидента.

    ``actor_email`` продублирован текстом рядом с ``user_id`` намеренно. Участника можно
    удалить из организации, и тогда ссылка перестанет что-либо называть; журнал же обязан
    отвечать на вопрос «кто это сделал» и через год после увольнения. Тот же приём, что у
    имени участника в сохранённой группе, — «надгробие».

    Запись не редактируется и не удаляется: в API нет ни PUT, ни DELETE. Срок хранения
    (5 лет по ARCHITECTURE §4) — политика эксплуатации, а не логика приложения; чистка
    журнала кодом означала бы, что приложение умеет стирать собственные следы.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Кто. Ссылка обнуляется при удалении пользователя, ``actor_email`` остаётся.
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Что: машинный код действия («project.create», «member.role_change», …).
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Над чем: тип и идентификатор объекта плюс его имя на момент действия.
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Подробности, зависящие от действия (старая и новая роль, код тарифа и т. п.).
    details: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class UserSession(Base):
    """Сеанс входа: с какого устройства и адреса человек сейчас в системе (C1).

    **Это реестр входов, а не список отозванных токенов.** Отрицательный список
    («эти токены больше не годятся») план запрещал заводить без нужды — он ничего не
    даёт человеку и живёт только ради инфраструктуры. Реестр даёт прямо противоположное:
    пользователь **видит** свои входы и закрывает лишние сам, а платформа получает отзыв
    как побочный эффект, а не как отдельную машинерию.

    Один механизм вместо двух. План предлагал ещё и ``User.token_version``, но сеансы
    его покрывают целиком: «выйти на всех устройствах» — это отзыв всех строк, смена
    пароля — всех, кроме текущей. Держать оба значило бы завести два источника ответа на
    вопрос «действителен ли токен», и однажды они разошлись бы.

    ``id`` — он же ``jti`` токена: связь односторонняя и без хранения самого токена.
    Токен без ``jti`` (выпущенный до этой миграции) не принимается — все входят заново
    один раз; молчаливое исключение для таких токенов стало бы постоянной дырой.
    """

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Когда с этого сеанса последний раз обращались. Пишется не чаще раза в час — по
    #: тому же доводу, что и отметка присутствия участника (A3).
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Когда сеанс истекает сам. Совпадает со сроком токена: два разных срока однажды
    #: разошлись бы, и «активный» сеанс перестал бы работать без объяснения.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Когда сеанс закрыт (пользователем, сменой пароля или блокировкой). None — работает.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Строка браузера **как её прислал сам браузер**: подделать её может кто угодно,
    #: поэтому она подсказка для человека, а не удостоверение устройства.
    user_agent: Mapped[str] = mapped_column(String(255), default="", server_default="")
    #: Адрес, с которого вошли. Персональные данные (152-ФЗ): показываются **самому
    #: владельцу** и хранятся ради того, ради чего их и смотрят, — заметить чужой вход.
    ip: Mapped[str] = mapped_column(String(45), default="", server_default="")


class StaffLogEntry(Base):
    """Служебный журнал: что сотрудник платформы делал у клиентов (B1).

    Второй журнал заведён не ради симметрии. Журнал организации отвечает клиенту на
    вопрос «кто приходил ко мне», а этот — нам на вопрос «где сегодня был наш
    сотрудник»; собрать второй ответ из первого нельзя, не обойдя журналы всех
    организаций подряд.

    Организация названа **текстом рядом со ссылкой** и без внешнего ключа. Ключ с
    каскадом стирал бы след визита вместе с удалённой организацией — то есть ровно
    тогда, когда след нужнее всего. Тот же приём, что у почты актора в журнале
    организации.
    """

    __tablename__ = "staff_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    #: Кто из сотрудников. Ссылка обнуляется при удалении, почта остаётся.
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Что: «staff.orgs_list», «staff.org_view», «staff.audit_log_view», …
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    #: К кому приходили. Пусто — действие платформенное, а не в конкретной организации.
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    details: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class AnalysisJob(Base):
    """Фоновая задача анализа (Celery): реестр владения для изоляции арендатора.

    Статус и результат хранит бэкенд Celery; здесь — привязка ``job_id`` к организации
    (чтобы чужой арендатор не мог опросить задачу) и тип/время для аудита.
    """

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # = id задачи Celery
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # "monte_carlo"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
