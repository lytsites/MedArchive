from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE IF EXISTS price_documents "
                "ADD COLUMN IF NOT EXISTS archive_id UUID NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE IF EXISTS price_documents "
                "ADD COLUMN IF NOT EXISTS source_path VARCHAR(1000) NULL"
            )
        )
