"""Initial schema: applications, application_documents, audit_log, review_decisions

Revision ID: 0001
Revises:
Create Date: 2026-09-29

Design note: we write the initial migration by hand rather than using
--autogenerate because autogenerate needs a live DB connection. Hand-written
migrations are also easier to review in a pull request — a diff over plain
SQL is clearer than SQLAlchemy-generated op.create_table() calls.

However, we DO use op.create_table() (Alembic's DSL) instead of raw SQL so
the migration is cross-database compatible and reversible via downgrade().
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # TABLE: applications
    # ------------------------------------------------------------------
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("applicant_name", sa.String(200), nullable=False),
        sa.Column("applicant_email", sa.String(200), nullable=False),
        sa.Column("applicant_phone", sa.String(30), nullable=True),
        sa.Column("requested_loan_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("loan_purpose", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "SUBMITTED", "EXTRACTING", "RULES_CHECK",
                "AUTO_APPROVED", "AUTO_REJECTED",
                "HUMAN_REVIEW", "MANUALLY_APPROVED", "MANUALLY_REJECTED",
                "INFO_REQUESTED", "ERROR",
                name="application_status_enum",
            ),
            nullable=False,
            server_default="SUBMITTED",
        ),
        sa.Column("extraction_result", postgresql.JSONB(), nullable=True),
        sa.Column("rules_result", postgresql.JSONB(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("crm_contact_id", sa.String(100), nullable=True),
        sa.Column("crm_deal_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_idempotency_key", "applications", ["idempotency_key"], unique=True)
    op.create_index("ix_applications_status", "applications", ["status"])

    # Trigger to auto-update updated_at on row change
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    op.execute("""
        CREATE TRIGGER applications_updated_at
        BEFORE UPDATE ON applications
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # TABLE: application_documents
    # ------------------------------------------------------------------
    op.create_table(
        "application_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_type",
            sa.Enum(
                "GOVERNMENT_ID", "PROOF_OF_INCOME", "ADDRESS_PROOF",
                name="document_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="application/pdf"),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
        sa.Column("min_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_doc_application_id", "application_documents", ["application_id"])
    op.create_index("ix_app_doc_app_type", "application_documents", ["application_id", "document_type"])

    # ------------------------------------------------------------------
    # TABLE: audit_log  (append-only — no UPDATE trigger needed)
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "APPLICATION_SUBMITTED", "EXTRACTION_STARTED", "EXTRACTION_COMPLETED",
                "EXTRACTION_FAILED", "RULES_CHECK_STARTED", "RULES_CHECK_COMPLETED",
                "STATUS_CHANGED", "CRM_SYNC_ATTEMPTED", "CRM_SYNC_SUCCEEDED",
                "CRM_SYNC_FAILED", "NOTIFICATION_SENT", "NOTIFICATION_FAILED",
                "HUMAN_REVIEW_ASSIGNED", "HUMAN_REVIEW_DECISION",
                "N8N_WEBHOOK_TRIGGERED", "ERROR",
                name="audit_event_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("changed_from", sa.String(100), nullable=True),
        sa.Column("changed_to", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_application_id", "audit_log", ["application_id"])
    op.create_index("ix_audit_log_app_created", "audit_log", ["application_id", "created_at"])

    # ------------------------------------------------------------------
    # TABLE: review_decisions
    # ------------------------------------------------------------------
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_email", sa.String(200), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id"),
    )
    op.create_index("ix_review_decisions_application_id", "review_decisions", ["application_id"])


def downgrade() -> None:
    """Tear down in reverse order (children before parents, enums last)."""
    op.drop_table("review_decisions")
    op.drop_index("ix_audit_log_app_created", table_name="audit_log")
    op.drop_index("ix_audit_log_application_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_app_doc_app_type", table_name="application_documents")
    op.drop_index("ix_app_doc_application_id", table_name="application_documents")
    op.drop_table("application_documents")
    op.execute("DROP TRIGGER IF EXISTS applications_updated_at ON applications")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_idempotency_key", table_name="applications")
    op.drop_table("applications")
    # Drop enum types last
    sa.Enum(name="audit_event_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="document_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="application_status_enum").drop(op.get_bind(), checkfirst=True)
