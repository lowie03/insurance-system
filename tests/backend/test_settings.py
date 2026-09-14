"""Settings parsing that matters specifically for a real deployment (Render + Neon + Vercel).

Constructing Settings(field=...) directly as a kwarg goes through pydantic-settings'
InitSettingsSource, which is NOT what a real env var goes through (EnvSettingsSource) -- that
distinction is exactly what let the FRONTEND_ORIGINS bug (pydantic-settings tries to json.loads()
a "complex" field's env value before any validator runs, and crashes on a plain string) pass every
kwarg-based test here while still breaking the real deployment. Every field with a `mode="before"`
validator gets at least one test that sets a real environment variable, not just a kwarg, to
actually exercise that path.
"""
from backend.app.settings import Settings
from tests.backend.helpers import TEST_KEY


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, policy_signing_key=TEST_KEY, payment_mode="simulated", **overrides)


def test_frontend_origins_parses_a_comma_separated_value_via_a_real_env_var(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", " https://cover-xyz.vercel.app , http://localhost:5173 ,, ")
    monkeypatch.setenv("POLICY_SIGNING_KEY", TEST_KEY)
    monkeypatch.setenv("PAYMENT_MODE", "simulated")
    s = Settings(_env_file=None)
    assert s.frontend_origins == ["https://cover-xyz.vercel.app", "http://localhost:5173"]


def test_frontend_origins_parses_a_comma_separated_string_passed_directly():
    s = _settings(frontend_origins=" https://cover-xyz.vercel.app , http://localhost:5173 ,, ")
    assert s.frontend_origins == ["https://cover-xyz.vercel.app", "http://localhost:5173"]


def test_frontend_origins_default_is_unaffected():
    assert _settings().frontend_origins == ["http://localhost:5173"]


def test_frontend_origins_accepts_a_plain_list_too():
    s = _settings(frontend_origins=["https://a.example", "https://b.example"])
    assert s.frontend_origins == ["https://a.example", "https://b.example"]


def test_postgres_scheme_url_is_rewritten_via_a_real_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@ep-foo.neon.tech/insurance")
    monkeypatch.setenv("POLICY_SIGNING_KEY", TEST_KEY)
    monkeypatch.setenv("PAYMENT_MODE", "simulated")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://user:pass@ep-foo.neon.tech/insurance"


def test_postgres_scheme_url_is_rewritten_for_sqlalchemy():
    s = _settings(database_url="postgres://user:pass@ep-foo.neon.tech/insurance")
    assert s.database_url == "postgresql+psycopg://user:pass@ep-foo.neon.tech/insurance"


def test_bare_postgresql_scheme_url_also_gets_the_driver_qualifier():
    s = _settings(database_url="postgresql://user:pass@ep-foo.neon.tech/insurance")
    assert s.database_url == "postgresql+psycopg://user:pass@ep-foo.neon.tech/insurance"


def test_sqlite_url_is_left_alone():
    s = _settings(database_url="sqlite:////tmp/whatever.db")
    assert s.database_url == "sqlite:////tmp/whatever.db"
