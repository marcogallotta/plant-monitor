import pytest


def test_get_database_url_raises_when_env_not_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.database import get_database_url
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_database_url()
