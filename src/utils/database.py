import uuid
from typing import Any, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import Column
from sqlalchemy.sql import func
from sqlalchemy.types import UUID, DateTime

from src.utils.config import settings

DATABASE_URL: str = settings.DATABASE_URL
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def db() -> Generator[Any, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db_and_tables() -> None:
    # Import all models so they are registered with SQLAlchemy's Base
    # flake8: noqa: F401
    from src.models import (job, job_execution, job_notification,  # noqa: F401
                            job_template, user, metric_temp, meter_usage)

    Base.metadata.create_all(bind=engine)


# Base schema for all models
class BaseSchema(Base):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
