"""
Alembic env.py — the bridge between Alembic and our SQLAlchemy models.

Key decisions:
1. We import Base from core.database (the canonical, single Base instance).
   Alembic auto-generates migrations by comparing Base.metadata to the live DB.
2. We import ALL models before calling run_migrations so Alembic discovers
   every table. If a model is not imported, its table is invisible to Alembic.
3. We use settings.sync_database_url (psycopg2) not the async URL.
   Alembic's own migration runner is synchronous.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

# Project root on sys.path so we can import core & models
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import canonical Base (one object, one metadata registry)
from core.database import Base  # noqa: F401

# Import ALL models so Alembic registers their tables in Base.metadata
import models.application  # noqa: F401
import models.audit_log    # noqa: F401
import models.reviewer     # noqa: F401

from core.config import settings

# Alembic Config object
config = context.config

# Override the DB URL from our Settings (reads .env / env vars at runtime)
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

# Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to DB and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

