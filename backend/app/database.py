import time

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_database(attempts: int = 30) -> None:
    from . import models  # noqa: F401

    for attempt in range(attempts):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(1)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
