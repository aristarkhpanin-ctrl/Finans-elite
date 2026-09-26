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


#: Уровень поддержки: наблюдение и только оно (F5). Разбор обращения — это списки,
#: карточки и журнал; приостанавливать организацию и блокировать учётные записи для
#: этого не требуется, а «всё или ничего» выдавало именно такие права.
STAFF_SUPPORT = "support"
#: Уровень оператора: наблюдение плюс власть над клиентом. Перечень власти закрыт и
#: стережётся перечень-тестом — новый маршрут, меняющий что-то у клиента, обязан
#: пройти через него, а не появиться тихо между экранами наблюдения.
STAFF_OPERATOR = "operator"
#: Порядок здесь — от меньшего к большему, и он же порядок в интерфейсе.
STAFF_ROLES = (STAFF_SUPPORT, STAFF_OPERATOR)


#: Таблицы с ``organization_id``, у которых **нет** RLS-политики, — каждая с причиной.
#:
#: Изоляцию арендатора на PostgreSQL держит политика ``tenant_isolation``, и по умолчанию
#: её обязана иметь каждая таблица организации. Исключения есть, и причина у большинства
#: одна: **строку читают раньше, чем становится известен арендатор**. Под
#: ``FORCE ROW LEVEL SECURITY`` такое чтение вернуло бы пустоту — то есть сломало бы вход
#: в систему, — а политика с лазейкой («или арендатор не выставлен») дала бы контур, в
#: котором RLS не действует вовсе. Изоляцию в этих местах держит фильтр в CRUD.
#:
#: **Перечень сверяется с миграциями тестом** (`test_rls_policies.py`): новая таблица
#: организации либо получает политику, либо стоит здесь с причиной. Третьего нет — и
#: именно третье случилось в F2, где в докстринге `Payment` появилось «единственная
#: таблица без политики»: проверять это было нечем, и утверждение прожило две фазы.
NO_RLS_POLICY: dict[str, str] = {
    "memberships": "читается, чтобы узнать арендатора: до неё его не существует",
    "api_keys": "ключ сам называет свою организацию — его читают до входа в арендатора",
    "subscriptions": "режим доступа считается до входа в арендатора (B2)",
    "payments": "вебхук провайдера знает только свой идентификатор платежа (F2)",
    "analysis_jobs": "задача опрашивается по своему идентификатору, а видимость её "
                     "закрывает явная проверка организации в маршруте",
    "staff_log": "журнал платформы о себе: организация в нём — адресат визита, а не "
                 "владелец записи",
    "usage_events": "обезличенные события пользования — данные платформы о себе",
}


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
    #: Уровень внутри служебного контура (F5): ``support`` — наблюдение, ``operator`` —
    #: ещё и власть над клиентом (приостановка организации, блокировка учётной записи,
    #: сброс второго фактора, назначение тарифа).
    #:
    #: **Это не вторая правда, а дверь и уровень.** ``is_staff`` отвечает «пускать ли в
    #: контур вообще», ``staff_role`` — «что можно внутри». Слить их в одно поле значило
    #: бы либо потерять разделение, либо превратить снятие признака в правку строкового
    #: значения, где опечатка оставляет дверь открытой.
    #:
    #: Пусто у тех, кто не сотрудник. Пусто **у сотрудника** — состояние, которого
    #: :func:`crud.set_staff` не создаёт (уровень пишется вместе с признаком); появиться
    #: оно может только правкой базы руками, и власти такому не даётся: молча считать
    #: неназванный уровень высшим — выдать власть по опечатке, молча низшим — отнять её
    #: у того, кому её дали. Отказ называет причину.
    staff_role: Mapped[str] = mapped_column(String(20), default="", server_default="",
                                            nullable=False)
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
    #: Когда человек доказал, что ящик его: перешёл по ссылке, которая **ушла туда**.
    #: ``None`` — не доказал, и это не обвинение: до появления поля не доказывал никто.
    #:
    #: Подтверждение **ничего не запирает**. Оно решает одну задачу: информационные
    #: письма (вход с нового устройства, упоминание в обсуждении) не уходят на адрес,
    #: которого у человека может не быть, — чужая активность в чужом ящике это утечка,
    #: и опечатка в адресе превращает её в ежедневную. Дверные письма (приглашение,
    #: ссылка администратора, восстановление пароля) уходят всегда: они единственный
    #: способ войти, и запереть их значило бы запереть человека.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Секрет второго фактора (base32). Пусто — второй фактор не настраивался.
    #: Хранится как есть: это **общий** секрет, им проверяют код, и односторонний хэш
    #: тут не годится по устройству TOTP. Защита у него та же, что у хэшей паролей и
    #: моделей клиентов, — доступ к базе; притворяться, что она сильнее, не нужно.
    totp_secret: Mapped[str] = mapped_column(String(64), default="", server_default="")
    #: Когда второй фактор **включён**. Секрет есть, а это пусто — настройку начали и
    #: не подтвердили кодом: такой секрет ничего не защищает и на вход не влияет.
    totp_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Отпечатки резервных кодов (SHA-256). Почты у платформы нет, значит письма
    #: «восстановите доступ» не будет: без кодов потерянный телефон означал бы
    #: потерянную учётную запись. Использованный код удаляется из списка.
    totp_recovery: Mapped[list] = mapped_column(JSONType, default=list)
    #: Подряд идущие неудачные коды и до какого времени вход по второму фактору закрыт.
    #: Ограничение по адресу (`ratelimit`) от подбора шестизначного кода не спасает:
    #: адреса меняются, а учётная запись одна.
    totp_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    totp_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Приходят ли письма об обсуждениях (OPEN-DECISIONS §5). **Одна настройка, а не
    #: матрица «что и когда»**: матрицу заполняют один раз и больше не открывают, а
    #: человек, которому письма мешают, ищет один выключатель.
    #:
    #: Выключает **всё**, включая упоминание по имени: это последний рубеж «не пишите
    #: мне», и оставить в нём щель значило бы сделать его неправдой. Отписка от
    #: отдельной ветки устроена мягче — см. :class:`CommentSubscription`.
    comment_emails: Mapped[bool] = mapped_column(Boolean, default=True,
                                                 server_default=text("true"),
                                                 nullable=False)


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

    # --- Автопродление (пакет G, G5) ---
    #
    # Согласие клиента — это **тариф, сумма, срок и способ оплаты вместе**: списать другую
    # сумму или за другой тариф значило бы взять деньги, на которые согласия не давали.
    # Поэтому смена тарифа гасит согласие целиком (`crud.set_plan`), а рост цены
    # останавливает списание. Включается согласие только оплатой с отдельной отметкой.

    #: Включено ли автопродление. Без сохранённого способа оплаты не бывает.
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False,
                                             server_default=text("false"), nullable=False)
    #: Идентификатор сохранённого способа оплаты **у провайдера** (не карта: её платформа
    #: не видит). Наружу не отдаётся; при отключении стирается.
    payment_method_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Как способ назвать человеку («MasterCard *4444») — чтобы письмо о списании
    #: называло, откуда возьмут деньги.
    payment_method_title: Mapped[str] = mapped_column(String(120), default="",
                                                      server_default="")
    #: Сколько месяцев оплачивает каждое продление и на какую сумму дано согласие.
    renew_months: Mapped[int] = mapped_column(default=1, server_default="1")
    renew_amount_rub: Mapped[int] = mapped_column(default=0, server_default="0")
    #: Попытки списания за **текущий** конец периода: не больше одной в сутки и не
    #: больше трёх. Любая оплата, двигающая период, обнуляет счёт.
    renew_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    renew_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Почему последнее продление не состоялось — словами, для экрана и письма.
    renew_error: Mapped[str] = mapped_column(String(500), default="", server_default="")


class Payment(Base):
    """Платёж за смену тарифа (для интеграции с провайдером, 6.5b).

    **RLS-политики у этой таблицы нет, и это решение, а не упущение** (F2): вебхук
    провайдера приходит снаружи и знает только **свой** идентификатор платежа —
    организацию он не называет, она **выводится из найденной строки**. Под
    `FORCE ROW LEVEL SECURITY` такое чтение вернуло бы пустоту на PostgreSQL и молча
    потеряло бы оплату, а политика с лазейкой («или арендатор не выставлен») дала бы
    контур, в котором RLS не действует, — ровно то, что служебный контур отказался
    заводить в B1.

    Поэтому изоляцию здесь держит **фильтр CRUD**, и это не «как получится»: любое
    чтение платежей организации идёт через ``organization_id``, а единственное чтение
    без него — разбор вебхука по идентификатору провайдера. Перечень стережёт тест.

    .. note::
       В F2 здесь было написано «единственной среди таблиц с ``organization_id``».
       Это была неправда, и нашлась она в F3: таких таблиц семь, и у каждой своя
       причина — все они перечислены в :data:`NO_RLS_POLICY`. Утверждение
       «единственная» держалось на том, что его никто не проверял; теперь его
       проверяет тест, сверяющий перечень с самими миграциями.
    """

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
    #: Сколько месяцев оплачивает платёж (G5): годовая оплата — 12. Период по нему
    #: считает `billing.activate_paid_plan`, а не сумма: деление суммы на цену угадывало
    #: бы срок, как только появится скидка.
    months: Mapped[int] = mapped_column(default=1, server_default="1")
    #: Дал ли плательщик согласие на автопродление **этим** платежом. Сохранённый
    #: провайдером способ без нашей отметки согласия автопродления не включает.
    auto_renew_consent: Mapped[bool] = mapped_column(Boolean, default=False,
                                                     server_default=text("false"),
                                                     nullable=False)
    #: Автоматическое списание: какой конец периода оно продлевает. По нему же
    #: сверяется повтор — один конец периода не продлевается дважды.
    renews_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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


class SupportGrant(Base):
    """Доступ поддержки к моделям организации, открытый **самой организацией** (F4).

    Правило 6 («оператор видит метаданные, но не содержимое моделей клиентов») этой
    таблицей не отменяется, а получает дверь, ключ от которой **у клиента**. Форма
    принята целиком: выдаёт клиент, срок ограничен сверху, каждое чтение пишется в
    журнал организации. Подробности и отказы — ``app/support_access.py``.

    ``granted_by_email`` — «надгробие» рядом со ссылкой, как у автора записи в журнале:
    сотрудника могут удалить, а ответ на вопрос «кто открыл нам двери» обязан пережить
    его уход.

    Строка **не удаляется при закрытии доступа** — проставляется ``revoked_at``. История
    выданных доступов это и есть то, ради чего гарантия существует: «нам никто не
    открывал» должно быть проверяемым утверждением, а не отсутствием записи.
    """

    __tablename__ = "support_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Кто открыл — администратор или владелец организации (право ``org.manage``).
    granted_by: Mapped[str] = mapped_column(String(36), default="", server_default="")
    granted_by_email: Mapped[str] = mapped_column(String(320), default="",
                                                  server_default="")
    #: Зачем. Обязательна: доступ без причины через неделю неотличим от случайного.
    reason: Mapped[str] = mapped_column(String(500), default="", server_default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Когда клиент закрыл доступ досрочно. ``None`` — не закрывал.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    #: Сделано **через ключ доступа** — имя ключа и его открытая часть (OPEN-DECISIONS §3).
    #: Пусто — человек работал руками.
    #:
    #: Отдельное поле, а не приписка к ``details``: там лежат подробности действия, и
    #: дописанная к ним пометка либо затёрла бы их, либо потерялась бы среди них. Отдельным
    #: полем на вопрос «что у нас делают ключами» отвечает отбор, а не чтение глазами.
    #: Подмены автора при этом нет: ``actor_email`` — человек, выпустивший ключ, и в
    #: записи видно **обоих**.
    via_key: Mapped[str] = mapped_column(String(255), nullable=False, default="",
                                         server_default="")
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


class Comment(Base):
    """Обсуждение рядом с числами: комментарий к проекту или к делу (D3).

    **Комментарий привязан к месту, а не к сущности целиком.** «Обсуждение проекта» —
    это чат, из которого через месяц не понять, о какой строке шла речь. ``anchor`` —
    стабильный ключ места (вкладка, строка отчёта, продукт, этап), ``anchor_label`` —
    его подпись **на момент написания**: продукт переименуют или удалят, а разговор
    обязан остаться понятным. Молча перевесить обсуждение на другой объект нельзя, и
    «надгробие» подписи — та же машинерия, что у почты в журнале.

    **Одна таблица на оба продукта.** У проекта и у дела обсуждение устроено одинаково;
    вторая таблица разошлась бы с первой ровно так же, как разошлись бы два конвейера
    разбора. Продукт выводится из ``subject_type`` — отдельным полем он мог бы с ним
    поспорить.

    **Текст не правится.** Отредактированная реплика, на которую уже ответили,
    переписывает историю: спор становится непонятным, а согласие — приписанным. Удалить
    свою реплику можно, но на её месте остаётся «надгробие» (``deleted_at``): пропавшая
    без следа строка читается как не сказанная никогда.
    """

    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: "project" | "case" — из него же выводится продукт (тариф у них разный).
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    #: Место внутри сущности: "tab:sales", "line:income:I5", "product:<id>", "" — общее.
    anchor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: Подпись места на момент написания — чтобы разговор остался понятным после правок.
    anchor_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    author_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: Почта автора текстом: участника удалят, а разговор обязан отвечать «кто это сказал».
    author_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    author_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    #: Кого упомянули (почты через запятую). Упоминание **не даёт прав** — только зовёт.
    mentions: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    #: Обсуждение закрыто: кем и когда. NULL — открыто.
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Реплика удалена: текст стёрт, «надгробие» осталось. ``deleted_by`` — почта того,
    #: кто её убрал: «удалена автором» под чужим удалением было бы неправдой.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class CommentSubscription(Base):
    """Состояние писем **одного человека об одной ветке** обсуждения (OPEN-DECISIONS §5).

    **Подписки здесь нет — есть исключения из неё.** Подписан тот, кто участвует: написал
    реплику или был в ней упомянут. Это выводится из самих реплик и потому не может
    разойтись с разговором; хранить отдельный список «кто подписан» значило бы завести
    вторую правду, которую кто-то должен поддерживать (и которая молча отстанет, как
    только человек напишет в ветку с телефона). В таблице живёт только то, чего из реплик
    не вывести:

    * ``muted_at`` — человек сказал «не пишите мне об этой ветке». Отписка обязана
      переживать перезапуск: «я же отписался» — худшее, что можно услышать об уведомлениях;
    * ``last_notified_at`` — когда ему в последний раз написали **об этой ветке**. Отсюда
      пауза: одно письмо и тишина, а не письмо на каждую реплику. Ограничитель в памяти
      процесса здесь не годится — он обнуляется на выкатке, а получатель этого не знает.

    Ветка — это ``(subject_type, subject_id, anchor)``: место, а не сущность целиком.
    Обсуждение строки I5 и обсуждение вкладки «Сбыт» — разные разговоры, и человек,
    ушедший из одного, не переставал следить за другим.

    **Организации у строки нет — и это не упущение.** Это личная настройка человека, как
    и реестр входов (:class:`UserSession`): она про него, а не про содержимое организации.
    Отсюда и то, что ссылка «отписаться» из письма работает **без входа и без арендатора**:
    RLS здесь нечему защищать, а требовать пароль ради «перестаньте мне писать» — способ
    заставить человека отправить письмо в спам вместо отписки.
    """

    __tablename__ = "comment_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "subject_type", "subject_id", "anchor",
                         name="uq_comment_subscription_thread"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Ветка: "project" | "case", сущность и место внутри неё (пусто — общее обсуждение).
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    anchor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: Когда человек отписался от ветки. None — письма о ней идут как обычно.
    muted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Когда ему в последний раз написали об этой ветке — начало паузы.
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditChecklist(Base):
    """Свой чек-лист организации: набор процедур, который она применяет к делам (D4).

    **Отраслевого каталога у платформы по-прежнему нет** — он утверждал бы, что именно
    проверяют в конкретной отрасли, а такой методики у платформы нет (см.
    ``CustomProcedure``). Здесь другое: чек-лист принадлежит **организации** и написан её
    аналитиками — тот же приём, что с отраслевыми ориентирами, где отказ от рыночных
    медиан стал функцией «ваш ориентир, а не рынок».

    Ценность простая: одни и те же пятнадцать процедур перестают перепечатываться в
    каждое новое дело. Платформа их **не выполняет** — применённые к делу, они попадают в
    ``custom_procedures`` со статусом «не начата», как и любая процедура аналитика.

    Уникальна пара «организация + имя»: два чек-листа с одним названием означали бы, что
    выбирать между ними будет платформа.
    """

    __tablename__ = "audit_checklists"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_checklist_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Для какой отрасли/случая — свободный текст: это подпись автора, а не классификатор.
    scope: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: Пункты — список строк. Порядок сохраняется: чек-лист читают сверху вниз.
    items: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    author_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 onupdate=_now)


class ApiKey(Base):
    """Ключ доступа к API организации (D5).

    Ключ принадлежит **организации**, а не человеку: он живёт в чужом сервере (BI, 1С,
    скрипт выгрузки) и обязан пережить увольнение того, кто его завёл. Кто завёл — всё
    равно записано: без имени в списке через год никто не скажет, что это за ключ.

    Хранится только **отпечаток** секрета: украденная база не даёт ключей, и «покажите
    ещё раз» невозможно ни для кого, включая платформу. Открытый префикс лежит рядом —
    по нему ключ находят и узнают в списке.

    Отзыв мгновенный по тому же устройству, что у сеансов (C1): состояние читается из
    базы на каждом запросе, а не живёт в самом ключе.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Человеческое имя: «Выгрузка в 1С», «Дашборд финдиректора».
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: Открытая часть — не секрет: по ней ищут строку и узнают ключ в списке.
    prefix: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    #: SHA-256 полной строки ключа. Самого ключа платформа не хранит.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Кто выпустил — **ссылкой**, а не только почтой (OPEN-DECISIONS §3). Почта рядом
    #: осталась «надгробием» для списка; ссылка нужна для другого: автор ключа — это
    #: автор его записей в журнале, и ключ работает, **пока работает он**.
    #:
    #: ``None`` — автора не найти (ключ старше механизма и выпущен тем, кого в базе уже
    #: нет). Такой ключ не пишет и не читает: доверенность без доверителя не бывает, —
    #: и отказ называет причину, а не «недействительный ключ».
    created_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: Права, выбранные при выпуске (значения `Perm`). Чтение в них не обязано быть — оно
    #: есть у ключа всегда; список отвечает на вопрос «что ему **добавили**».
    #: Пустой список — ключ, выпущенный до выбора прав: он читает (`apikeys.effective_perms`).
    scopes: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Когда ключом пользовались последний раз. ``None`` — **ни разу**, и это другое
    #: состояние, чем «давно»: неиспользованный ключ обычно забыт, а не бережём.
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class UsageEvent(Base):
    """Событие пользования продуктом (E2) — **не журнал**.

    Журнал отвечает клиенту «кто это сделал», не пишет чтение и хранится долго. События
    отвечают платформе «как пользуются», пишут именно чтение и живут ровно столько,
    сколько нужно для ответа. Одна таблица на два вопроса означала бы, что в журнале
    тонет сигнал, а в событиях появляются персональные данные.

    Участник **обезличен**: вместо почты — её отпечаток с солью установки. Для когорт
    («тот же человек вернулся») этого достаточно, для «кто именно» — нет.

    Содержимого моделей клиента здесь нет и быть не может: ключи контекста перечислены
    (`usage.CONTEXT_KEYS`), значения обрезаны до 64 знаков.
    """

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    #: Код из закрытого перечня `usage.EVENTS`.
    event: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    #: Отпечаток участника; пусто — системное событие, за которым нет человека.
    actor: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    context: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
