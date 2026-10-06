"""HTTP 层集成测试：CRUD、分析留痕、演示案例与前提阻断。"""
from __future__ import annotations

import pytest


def _seed(client) -> list[int]:
    r = client.post("/api/demo/seed")
    assert r.status_code == 201, r.text
    return [c["id"] for c in r.json()["created"]]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["fixed_seed"] == 20260601


def test_demo_seed_and_hole_shaft_analysis(client):
    ids = _seed(client)
    r = client.post(f"/api/chains/{ids[0]}/analyze", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    wc = data["worst_case"]
    assert wc["minimum_mm"] == 0.009
    assert wc["maximum_mm"] == 0.050
    assert "不是最终间隙" in wc["absolute_sum_note"]
    assert data["rss"] is not None and data["monte_carlo"] is not None
    assert data["monte_carlo"]["seed"] == 20260601
    assert data["monte_carlo"]["analytical_extreme_check"]["within_physical_envelope"]
    # 单边/非对称公差带的正态假设提示存在（H7 单边、g6 非对称）
    assert len(data["assumption_notes"]) >= 2
    assert data["disclaimer"].startswith("本工具")

    # 固定种子复现：第二次分析的统计字段完全一致
    r2 = client.post(f"/api/chains/{ids[0]}/analyze", json={}).json()
    a, b = data["monte_carlo"], r2["monte_carlo"]
    assert (a["p1_mm"], a["p99_mm"], a["mean_mm"]) == (b["p1_mm"], b["p99_mm"], b["mean_mm"])

    # 留痕：三种方法各一条
    runs = client.get(f"/api/chains/{ids[0]}/runs").json()
    methods = {x["method"] for x in runs}
    assert methods == {"worst_case", "rss", "monte_carlo"}
    mc_run = next(x for x in runs if x["method"] == "monte_carlo")
    assert mc_run["seed"] == 20260601 and mc_run["n_samples"] == 100_000


def test_demo_thermal_one_sided_and_zero_datum(client):
    ids = _seed(client)
    # 热膨胀案例
    hot = client.post(f"/api/chains/{ids[1]}/analyze", json={}).json()
    assert hot["worst_case"]["minimum_mm"] == pytest.approx(0.18)
    assert hot["worst_case"]["maximum_mm"] == pytest.approx(0.30)
    assert hot["rss"]["mean_shift_from_nominal_mm"] == pytest.approx(-0.02)

    # 零公差基准
    datum = client.post(f"/api/chains/{ids[2]}/analyze", json={}).json()
    wc = datum["worst_case"]
    assert wc["minimum_mm"] == pytest.approx(-0.08) and wc["maximum_mm"] == pytest.approx(0.08)
    b0 = next(c for c in wc["contributors"] if "B0" in c["name"])
    assert b0["band_width_mm"] == 0.0 and b0["share"] == 0.0
    assert datum["dominance_summary"]["tolerance_band_dominator"]["name"] == "台阶长度 L2"


def test_unknown_distribution_blocks_via_http(client):
    payload = {
        "name": "未知分布链",
        "closing_name": "间隙 X",
        "closing_positive_direction": "X = A − B，正为间隙",
        "expected_closing_nominal": 0.0,
        "dimensions": [
            {"name": "A", "nominal": 10.0, "lower_deviation": -0.05, "upper_deviation": 0.05,
             "direction": 1, "distribution_kind": "unknown", "dimension_unit": "mm"},
            {"name": "B", "nominal": 10.0, "lower_deviation": -0.02, "upper_deviation": 0.02,
             "direction": -1, "distribution_kind": "uniform", "dimension_unit": "mm"},
        ],
    }
    cid = client.post("/api/chains", json=payload).json()["id"]
    data = client.post(f"/api/chains/{cid}/analyze", json={}).json()
    assert data["rss"] is None and data["monte_carlo"] is None
    assert "不能自动假设正态" in data["statistical_blockers"][0]
    assert data["worst_case"]["minimum_mm"] == pytest.approx(-0.07)
    # 未知分布不写统计类留痕
    runs = client.get(f"/api/chains/{cid}/runs").json()
    assert [x["method"] for x in runs] == ["worst_case"]


def test_unit_mismatch_is_converted_and_persisted(client):
    payload = {
        "name": "单位混合链",
        "closing_name": "间隙 G",
        "closing_positive_direction": "G = 孔 − 轴",
        "expected_closing_nominal": 0.0,
        "dimensions": [
            {"name": "孔", "nominal": 50000, "lower_deviation": 0, "upper_deviation": 25,
             "dimension_unit": "um", "direction": 1,
             "distribution_kind": "normal",
             "distribution_params": {"sigma_side": 3, "basis": "教科书示例"}},
            {"name": "轴", "nominal": 50.0, "lower_deviation": -0.025, "upper_deviation": -0.009,
             "dimension_unit": "mm", "direction": -1,
             "distribution_kind": "normal",
             "distribution_params": {"sigma_side": 3, "basis": "教科书示例"}},
        ],
    }
    cid = client.post("/api/chains", json=payload).json()["id"]
    data = client.post(f"/api/chains/{cid}/analyze", json={}).json()
    assert data["worst_case"]["minimum_mm"] == pytest.approx(0.009)
    assert data["unit_conversions"][0]["from_unit"].lower() in ("um", "µm")
    # 重新读取，确认单位、方向、分布假设均已落库
    chain = client.get(f"/api/chains/{cid}").json()
    hole = next(d for d in chain["dimensions"] if d["name"] == "孔")
    assert hole["dimension_unit"].lower() in ("um", "µm")
    assert hole["distribution_kind"] == "normal"


def test_invalid_band_rejected_by_schema(client):
    payload = {
        "name": "坏链", "closing_name": "X", "closing_positive_direction": "X",
        "dimensions": [
            {"name": "A", "nominal": 10, "lower_deviation": 0.05, "upper_deviation": 0.0,
             "dimension_unit": "mm", "direction": 1, "distribution_kind": "unknown"},
        ],
    }
    r = client.post("/api/chains", json=payload)
    assert r.status_code == 422


def test_thermal_util_endpoint(client):
    r = client.post("/api/utils/thermal-expansion-term", json={
        "alpha_per_c": 12e-6, "length_mm": 500, "delta_t_c": 40,
        "delta_t_lower_c": 0, "delta_t_upper_c": 10, "uncertainty_kind": "uniform",
    })
    assert r.status_code == 200, r.text
    term = r.json()
    assert term["nominal"] == 0.24
    assert term["lower_deviation"] == 0.0 and term["upper_deviation"] == 0.06
    assert term["source"] == "thermal_expansion"
