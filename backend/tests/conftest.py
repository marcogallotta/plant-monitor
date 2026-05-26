import pytest
from alembic.config import Config
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import build_engine, build_session_factory, get_db
from app.main import app, PHOTOS_DIR
from app.models import Base


@pytest.fixture(scope="session")
def engine():
    engine = build_engine()

    assert "plantmonitoring" in str(engine.url), (
        f"Refusing to run tests against {engine.url} — expected a plantmonitoring database"
    )

    Base.metadata.drop_all(engine)

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


@pytest.fixture(autouse=True)
def clean_tables(engine):
    yield
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE photo_notes, photos RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.fixture(autouse=True)
def isolated_photos_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.PHOTOS_DIR", tmp_path)
    yield tmp_path


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
