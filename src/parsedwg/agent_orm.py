"""ORM models for agent jobs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .orm import Base
from .settings import settings


def _get_now() -> datetime:
    return datetime.now(settings.tz)


class AgentJob(Base):
    __tablename__ = "agent_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile: Mapped[str] = mapped_column(String(64), nullable=False)
    input_ref: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    options_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_get_now,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["AgentJobStep"]] = relationship(
        "AgentJobStep",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="AgentJobStep.step_order",
    )


class AgentJobStep(Base):
    __tablename__ = "agent_job_step"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent_job.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    target_file_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="steps")