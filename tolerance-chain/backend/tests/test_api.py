"""API 集成测试：建表、演示数据、分析落库、422 拒绝。

默认用内存 SQLite（TOLERANCE_DB 环境变量可覆盖为 PostgreSQL）。
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 在导入 app 之前切换数据库
_tmp = Path(tempfile.gettempdir()) / "tol_test.db"
if _tmp.exists():
    _tmp.unlink()
os.environ["TOLERANCE_DB"] = f"sqlite:///{_tmp}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_demo_data  # noqa: E402
from app.database import SessionLocal  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    seed_demo_data(db)
    db.close()
    with TestClient(app) as c:
        yield c


def test_health_and_demo_seed(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    chains = client.get("/api/chains").json()
    codes = {c["code"] for c in chains}
    assert {"shaft_hole_50H8f7", "thermal_growth",
            "zero_datum_stack", "unknown_dist"} <= codes


def test_analyze_shaft_hole_and_persist(client):
    chains = {c["code"]: c for c in client.get("/api/chains").json()}
    cid = chains["shaft_hole_50H8f7"]["id"]
    resp = client.post(f"/api/chains/{cid}/analyze",
                       json={"seed": 20261006, "n_samples": 50000,
                             "k_sigma": 3.0})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    r = body["result"]["results"]
    wc = r["worst_case"]
    assert wc["gap_min"] == pytest.approx(0.025)
    assert wc["gap_max"] == pytest.approx(0.089)
    mc = r["monte_carlo"]
    assert mc["seed"] == 20261006 and mc["n_samples"] == 50000
    # 主导可追溯
    assert wc["dominant_key"] == "bore"
    assert "disclaimer" in body["result"]

    # 运行记录已落库
    runs = client.get(f"/api/chains/{cid}/runs").json()
    assert any(run["id"] == body["id"] for run in runs)


def test_unknown_distribution_chain_analysis_explains_block(client):
    chains = {c["code"]: c for c in client.get("/api/chains").json()}
    cid = chains["unknown_dist"]["id"]
    body = client.post(f"/api/chains/{cid}/analyze", json={}).json()
    res = body["result"]["results"]
    assert "worst_case" in res
    assert "rss" not in res and "monte_carlo" not in res
    assert "正态" in body["result"]["method_errors"]["rss"]


def test_create_chain_validates_direction_and_closure(client):
    # 缺减环 -> 计算时 422
    payload = {
        "code": "bad_chain", "name": "不闭合",
        "closed_unit": "mm",
        "rings": [
            {"key": "a", "name": "A", "source": "x", "direction": 1,
             "nominal": 10, "es": 0.1, "ei": 0, "unit": "mm"},
            {"key": "b", "name": "B", "source": "x", "direction": 1,
             "nominal": 5, "es": 0.05, "ei": -0.05, "unit": "mm"},
        ],
    }
    r = client.post("/api/chains", json=payload)
    assert r.status_code == 201
    cid = r.json()["id"]
    err = client.post(f"/api/chains/{cid}/analyze", json={})
    assert err.status_code == 422
    assert "闭合" in err.json()["detail"]


def test_halfnormal_symmetric_input_rejected(client):
    payload = {
        "code": "bad_half", "name": "误用半正态",
        "rings": [
            {"key": "a", "name": "A", "source": "x", "direction": 1,
             "nominal": 10, "es": 0.1, "ei": -0.1, "unit": "mm",
             "distribution": "halfnormal", "dist_params": {"sigma": 0.03}},
            {"key": "b", "name": "B", "source": "x", "direction": -1,
             "nominal": 9, "es": 0.0, "ei": 0.0, "unit": "mm"},
        ],
    }
    r = client.post("/api/chains", json=payload)
    assert r.status_code == 422
    assert "单边" in r.json()["detail"]
