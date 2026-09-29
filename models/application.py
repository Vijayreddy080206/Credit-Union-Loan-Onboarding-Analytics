"""
Application & ApplicationDocument models.

TABLE: applications
-------------------
The central record per loan application. One row = one applicant's request.

Key design choices:
- `id` is a UUID, not a serial integer. UUIDs are safe to expose in URLs
  (no sequential enumeration attacks) and can be generated client-side
  (useful for idempotency: client sets the ID before POSTing).
- `idempotency_key` is a separate column, unique-indexed. It lets the API
  detect re-submissions without relying on the UUID matching.
- `status` is an enum stored as a VARCHAR. Using a Python Enum for the column
  type means SQLAlchemy validates values before they hit the DB.
- `extraction_result` and `rules_result` are JSONB. Finance systems store
  intermediate pipeline outputs so you can re-run later rules without
  re-calling the LLM. JSONB is indexed and queryable in Postgres.
- Timestamps: `created_at` is set once; `updated_at` is auto-bumped on every
  UPDATE via `onupdate=func.now()`. Never trust the application layer to set
  these — let the DB do it.

TABLE: application_documents
-----------------------------
Each submitted document is a separate row linked by FK to the application.
Why not store docs in the application row? Because an applicant can upload
multiple documents of different types (ID, income, address), and the number
is variable. A separate child table avoids messy nullable columns.
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
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class ApplicationStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    EXTRACTING = "EXTRACTING"
    RULES_CHECK = "RULES_CHECK"
    AUTO_APPROVED = "AUTO_APPROVED"
    AUTO_REJECTED = "AUTO_REJECTED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    MANUALLY_APPROVED = "MANUALLY_APPROVED"
    MANUALLY_REJECTED = "MANUALLY_REJECTED"
    INFO_REQUESTED = "INFO_REQUESTED"
    ERROR = "ERROR"


class DocumentType(str, enum.Enum):
    GOVERNMENT_ID = "GOVERNMENT_ID"
    PROOF_OF_INCOME = "PROOF_OF_INCOME"
    ADDRESS_PROOF = "ADDRESS_PROOF"


class Application(Base):
    __tablename__ = "applications"

    # Primary key: UUID generated at the application layer so clients can
    # know their ID before the DB round-trip completes.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Idempotency key: caller generates this once; subsequent retries send
    # the same key, and we detect duplicates before creating new DB rows.
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )

    # Applicant-supplied fields (from the web form)
    applicant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    applicant_email: Mapped[str] = mapped_column(String(200), nullable=False)
    applicant_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    requested_loan_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    loan_purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Pipeline state
    # SQLAlchemy's `default=` fires at INSERT time, not object construction.
    # We also set `insert_default` so the in-memory object has the right value
    # immediately — important for audit log entries written before the first flush.
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status_enum"),
        default=ApplicationStatus.SUBMITTED,
        nullable=False,
        index=True,
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("status", ApplicationStatus.SUBMITTED)
        super().__init__(**kwargs)

    # LLM extraction output — stored raw so we can audit or re-run
    extraction_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Rules engine output — which rules passed/failed and why
    rules_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Final decision metadata
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # CRM foreign key (set after successful sync)
    crm_contact_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crm_deal_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps — DB-managed, not app-managed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    documents: Mapped[list["ApplicationDocument"]] = relationship(
        "ApplicationDocument", back_populates="application", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="application", cascade="all, delete-orphan"
    )
    review_decision: Mapped["ReviewDecision | None"] = relationship(
        "ReviewDecision", back_populates="application", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Application {self.id} status={self.status}>"


class ApplicationDocument(Base):
    __tablename__ = "application_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type_enum"), nullable=False
    )

    # Where the file lives (local path in dev, S3/GCS URI in prod)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)

    # MIME type for the extraction service to know how to process the file
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")

    # Extraction output for this specific document
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Minimum confidence across all fields in this document
    min_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    application: Mapped["Application"] = relationship(
        "Application", back_populates="documents"
    )

    # Composite index: look up all docs for an application by type quickly
    __table_args__ = (
        Index("ix_app_doc_app_type", "application_id", "document_type"),
    )

    def __repr__(self) -> str:
        return f"<ApplicationDocument {self.document_type} app={self.application_id}>"
