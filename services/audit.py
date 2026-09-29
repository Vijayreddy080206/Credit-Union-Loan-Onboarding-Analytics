"""
Audit log helper — every service uses this instead of writing raw ORM code.

Design: a single write_event() function enforces that every audit row has the
required fields. You can never forget to set actor or message. In a larger
team this is enforced by code review; in a solo project, isolating it here
means you only have one place to change if the schema evolves.

asynccontextmanager pattern: callers pass their existing DB session so all
writes in a request are part of the same transaction. If the request fails and
rolls back, the audit rows roll back too — which is correct (you don't want
audit rows claiming something happened that didn't).
"""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AuditEventType, AuditLog


async def write_event(
    session: AsyncSession,
    application_id: uuid.UUID,
    event_type: AuditEventType,
    actor: str,
    message: str,
    changed_from: str | None = None,
    changed_to: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Append one event to the audit log.

    This is an async function, but it does NOT commit — the caller's
    transaction boundary controls commit/rollback. This keeps audit writes
    atomic with the business operation they describe.
    """
    log_entry = AuditLog(
        application_id=application_id,
        event_type=event_type,
        actor=actor,
        message=message,
        changed_from=changed_from,
        changed_to=changed_to,
        details=details,
    )
    session.add(log_entry)
    await session.flush()   # assigns the DB-generated id without committing
    return log_entry
