"""ORM-модели (SQLAlchemy 2.0).

6.1 — хранение проектов. Привязка к организации/пользователю (organization_id) добавляется
в 6.2 (мультиарендность).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# JSONB на PostgreSQL, JSON на остальных (SQLite).
JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """Проект финансовой модели (замена файла ``.pex``)."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная ProjectModel (mode="json": Decimal → строка, даты → ISO).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
