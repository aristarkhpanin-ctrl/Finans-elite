"""ORM-модели (SQLAlchemy 2.0).

6.1 — проекты; 6.2 — мультиарендность (организации, пользователи, членство; проекты
привязаны к организации). Изоляция данных — по ``organization_id`` (ARCHITECTURE §4).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    JSON,
    String,
    UniqueConstraint,
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
    """Арендатор (компания-клиент)."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    """Пользователь. ``hashed_password`` отсутствует у приглашённых (без входа) до активации."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    """Членство пользователя в организации с ролью (роли — RBAC, 6.4)."""

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


class Subscription(Base):
    """Подписка организации на тариф (одна на организацию)."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
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
    """Проект финансовой модели (замена файла ``.pex``), принадлежит организации."""

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
