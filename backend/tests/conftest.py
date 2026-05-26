import pytest
from alembic.config import Config
from alembic import command

from app.database import build_engine, build_session_factory
from app.models import Base


@pytest.fixture(scope="session")
def engine():
    engine = build_engine()

    assert "plantmonitoring" in str(engine.url), (
        f"Refusing to run tests against {engine.url} — expected a plantmonitoring database"
    )

    # Clean slate in case a previous run left tables behind
    Base.metadata.drop_all(engine)

    # Exercise the actual migration, not create_all
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    yield engine

    command.downgrade(alembic_cfg, "base")
    engine.dispose()


@pytest.fixture
def db_session(engine):
    session = build_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
