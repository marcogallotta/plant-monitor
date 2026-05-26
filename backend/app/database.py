import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def build_engine():
    return create_engine(get_database_url())


def build_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


_session_factory = None


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = build_session_factory(build_engine())
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    db = _get_session_factory()()
    try:
        yield db
    finally:
        db.close()
