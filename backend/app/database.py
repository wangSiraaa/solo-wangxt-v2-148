"""数据库连接与建表。

PostgreSQL 使用 JSONB 保存分布假设等结构化字段；其它方言（本地测试用 SQLite）
退化为通用 JSON。
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


# PG 用 JSONB，SQLite 用通用 JSON
JSONType = JSON().with_variant(JSONB(), "postgresql")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # 显式导入，确保模型已注册到 metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
