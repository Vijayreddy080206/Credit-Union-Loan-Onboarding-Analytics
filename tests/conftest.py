"""
conftest.py — shared pytest fixtures.

Phase 1: just the settings override fixture.
Phase 5+: will add async DB session fixture and test client fixture.

Why override settings in tests? So unit tests don't accidentally connect to
a real DB or call a real LLM API. The pattern is the same as 12-factor app
config: test config is just another set of environment variables.

Why clear lru_cache? settings is a cached singleton. If we only set env vars,
the cache returns the old object. Clearing the cache forces a rebuild with the
patched values on the next get_settings() call.
"""
import pytest


@pytest.fixture(autouse=True)
def override_settings_for_tests(monkeypatch):
    """
    Override settings for every unit test.
    autouse=True means this runs automatically — no need to declare it.
    """
    from core import config as config_module

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-placeholder")

    # Clear the lru_cache so settings rebuild with patched env vars
    config_module.get_settings.cache_clear()

    yield

    # After the test: clear again so the next test starts clean
    config_module.get_settings.cache_clear()

