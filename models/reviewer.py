"""
ReviewDecision model — records what a human reviewer decided.

One-to-one with Application. We store this separately (not as a column
on Application) so we capture *who* reviewed, *when*, *what notes* they
left, and *what override reason* they gave. This is required for fair
lending compliance — you must be able to prove a human saw the case and
why they overrode (or confirmed) the automated recommendation.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one decision per application
        index=True,
    )

    # Reviewer identity — in a real system this is pulled from your IdP/SSO
    reviewer_email: Mapped[str] = mapped_column(String(200), nullable=False)

    # True = approved, False = rejected
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Free-text notes the reviewer wrote (required for compliance)
    notes: Mapped[str] = mapped_column(Text, nullable=False)

    # If the reviewer overrode the system recommendation, they must explain why
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    application: Mapped["Application"] = relationship(
        "Application", back_populates="review_decision"
    )

    def __repr__(self) -> str:
        return f"<ReviewDecision app={self.application_id} approved={self.approved}>"
