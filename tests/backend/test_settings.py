"""Settings parsing that matters specifically for a real deployment (Render + Neon + Vercel)."""
from backend.app.settings import Settings
from tests.backend.helpers import TEST_KEY


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, policy_signing_key=TEST_KEY, payment_mode="simulated", **overrides)


def test_frontend_origins_parses_a_comma_separated_env_string():
    s = _settings(frontend_origins=" https://cover-xyz.vercel.app , http://localhost:5173 ,, ")
    assert s.frontend_origins == ["https://cover-xyz.vercel.app", "http://localhost:5173"]


def test_frontend_origins_default_is_unaffected():
    assert _settings().frontend_origins == ["http://localhost:5173"]


def test_frontend_origins_accepts_a_plain_list_too():
    s = _settings(frontend_origins=["https://a.example", "https://b.example"])
    assert s.frontend_origins == ["https://a.example", "https://b.example"]


def test_postgres_scheme_url_is_rewritten_for_sqlalchemy():
    s = _settings(database_url="postgres://user:pass@ep-foo.neon.tech/insurance")
    assert s.database_url == "postgresql+psycopg://user:pass@ep-foo.neon.tech/insurance"


def test_bare_postgresql_scheme_url_also_gets_the_driver_qualifier():
    s = _settings(database_url="postgresql://user:pass@ep-foo.neon.tech/insurance")
    assert s.database_url == "postgresql+psycopg://user:pass@ep-foo.neon.tech/insurance"


def test_sqlite_url_is_left_alone():
    s = _settings(database_url="sqlite:////tmp/whatever.db")
    assert s.database_url == "sqlite:////tmp/whatever.db"
