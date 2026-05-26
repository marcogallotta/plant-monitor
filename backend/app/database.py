import os

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
