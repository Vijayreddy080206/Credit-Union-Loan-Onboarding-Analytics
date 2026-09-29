"""
models/base.py — canonical re-export of Base and session factory.

We define Base *once* in core/database.py (where the engine lives).
This file re-exports it so model files can do `from models.base import Base`
which reads more naturally, while Alembic's env.py imports from core.database
to get the same object. A single Base object = a single metadata registry =
Alembic sees every table.
"""
# Re-export everything so existing imports stay valid
from core.database import Base, engine, AsyncSessionLocal  # noqa: F401

__all__ = ["Base", "engine", "AsyncSessionLocal"]

