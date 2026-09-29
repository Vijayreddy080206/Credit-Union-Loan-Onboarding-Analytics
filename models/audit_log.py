"""
AuditLog model — the immutable event ledger.

Design principle: append-only.
Every step in the pipeline writes one row here and never updates it.
The `changed_from` / `changed_to` columns capture the state transition
for status-change events. `actor` identifies whether the action was taken
by the system (service name) or a human (reviewer email).

Why JSONB for `details`? The extra context per event is highly variable:
an extraction event might store confidence scores, a rules event might store
which rules failed. JSONB lets us store all of it without a schema migration
every time we add a new event type.

Why not use the application's `updated_at`? That timestamp is overwritten
every time the row changes. The audit log preserves EVERY intermediate state
including failed attempts, retries, and partial results.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class AuditEventType(str, enum.Enum):
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    EXTRACTION_STARTED = "EXTRACTION_STARTED"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    RULES_CHECK_STARTED = "RULES_CHECK_STARTED"
    RULES_CHECK_COMPLETED = "RULES_CHECK_COMPLETED"
    RULES_EVALUATED = "RULES_EVALUATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    AUTO_APPROVED = "AUTO_APPROVED"
    AUTO_REJECTED = "AUTO_REJECTED"
    ROUTED_TO_HUMAN = "ROUTED_TO_HUMAN"
    MANUALLY_APPROVED = "MANUALLY_APPROVED"
    MANUALLY_REJECTED = "MANUALLY_REJECTED"
    CRM_SYNC_ATTEMPTED = "CRM_SYNC_ATTEMPTED"
    CRM_SYNC_SUCCEEDED = "CRM_SYNC_SUCCEEDED"
    CRM_SYNC_FAILED = "CRM_SYNC_FAILED"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED"
    HUMAN_REVIEW_ASSIGNED = "HUMAN_REVIEW_ASSIGNED"
    HUMAN_REVIEW_DECISION = "HUMAN_REVIEW_DECISION"
    N8N_WEBHOOK_TRIGGERED = "N8N_WEBHOOK_TRIGGERED"
    ERROR = "ERROR"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(AuditEventType, name="audit_event_type_enum"), nullable=False
    )

    # Who triggered this event: "extraction_service", "rules_engine",
    # "crm_service", "reviewer@creditunion.com", etc.
    actor: Mapped[str] = mapped_column(String(200), nullable=False)

    # For status-change events: the before and after values
    changed_from: Mapped[str | None] = mapped_column(String(100), nullable=True)
    changed_to: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Human-readable summary of what happened (for the dashboard timeline)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Machine-readable extras: confidence scores, rule names, error codes, etc.
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Immutable timestamp — set by DB, never by app code
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    application: Mapped["Application"] = relationship(
        "Application", back_populates="audit_logs"
    )

    # Query pattern: "give me all audit events for application X, newest first"
    __table_args__ = (
        Index("ix_audit_log_app_created", "application_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.event_type} app={self.application_id}>"
