"""数据库连接。默认 PostgreSQL；设置 TOLERANCE_DB=sqlite:///... 可用于轻量测试。

生产/演示连接：postgresql+psycopg2://tolerance@localhost:5433/tolerance_db
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_URL = os.environ.get(
    "TOLERANCE_DB",
    "postgresql+psycopg2://tolerance@localhost:5433/tolerance_db",
)

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
