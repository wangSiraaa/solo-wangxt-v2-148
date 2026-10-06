"""测试在 SQLite 下运行（CI/本地无 PostgreSQL）。

通过 TC_DATABASE_URL 在导入应用前覆盖数据库连接。
"""
import os
import sys
import tempfile

import pytest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["TC_DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["TC_CORS_ORIGINS"] = '["*"]'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
