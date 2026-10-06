"""引擎层核对：解析极值 + 固定种子蒙特卡洛 + 前提阻断。"""
from __future__ import annotations

import numpy as np
import pytest

from app import tolerance


SEED = 20260601
NORMAL3 = {"sigma_side": 3}


# ---------- 案例 1：轴孔配合 φ50H7/g6 ----------
HOLE_SHAFT = [
    dict(name="孔 φ50H7", nominal=50.0, lower_deviation=0.0, upper_deviation=0.025,
         dimension_unit="mm", direction=1, source="design",
         distribution_kind="normal", distribution_params=NORMAL3),
    dict(name="轴 φ50g6", nominal=50.0, lower_deviation=-0.025, upper_deviation=-0.009,
         dimension_unit="mm", direction=-1, source="design",
         distribution_kind="normal", distribution_params=NORMAL3),
]


def test_hole_shaft_worst_case_analytical_extremes():
    """手算：G = D - d ∈ [0 −(−0.009), 0.025 −(−0.025)] = [0.009, 0.050]。"""
    res = tolerance.analyze(HOLE_SHAFT, n_samples=200_000, seed=SEED)
    wc = res["worst_case"]
    assert wc["nominal_mm"] == pytest.approx(0.0, abs=1e-12)
    assert wc["minimum_mm"] == pytest.approx(0.009, abs=1e-12)
    assert wc["maximum_mm"] == pytest.approx(0.050, abs=1e-12)
    assert wc["lower_deviation_mm"] == pytest.approx(0.009)
    assert wc["upper_deviation_mm"] == pytest.approx(0.050)
    # 带宽 = Σ|T| = 0.025 + 0.016 = 0.041，但绝不是间隙本身
    assert wc["tolerance_span_mm"] == pytest.approx(0.041)
    assert wc["sum_absolute_tolerances_mm"] == pytest.approx(0.041)
    assert "不是最终间隙" in wc["absolute_sum_note"]


def test_hole_shaft_rss_moments():
    """孔 σ=0.025/6，轴 σ=0.016/6；σ0=√(σh²+σs²)，均值=0.0295。"""
    res = tolerance.analyze(HOLE_SHAFT, n_samples=50_000, seed=SEED)
    r = res["rss"]
    sig_h = 0.025 / 6
    sig_s = 0.016 / 6
    assert r["mean_mm"] == pytest.approx(0.0295, abs=1e-12)  # (0.0125) −(−0.017)
    assert r["std_mm"] == pytest.approx(np.hypot(sig_h, sig_s), rel=1e-9)
    assert r["contributors"][0]["name"] == "孔 φ50H7"  # 大方差主导


def test_fixed_seed_monte_carlo_is_reproducible_and_within_envelope():
    a = tolerance.analyze(HOLE_SHAFT, n_samples=100_000, seed=SEED)["monte_carlo"]
    b = tolerance.analyze(HOLE_SHAFT, n_samples=100_000, seed=SEED)["monte_carlo"]
    assert a["mean_mm"] == b["mean_mm"]
    assert a["std_mm"] == b["std_mm"]
    assert a["p1_mm"] == b["p1_mm"]
    assert a["seed"] == SEED
    # 另一粒种子允许不同
    c = tolerance.analyze(HOLE_SHAFT, n_samples=100_000, seed=SEED + 1)["monte_carlo"]
    assert c["sample_min_mm"] != a["sample_min_mm"] or c["sample_max_mm"] != a["sample_max_mm"]
    # 对称截断不改变均值
    assert abs(a["mean_mm"] - 0.0295) < 1e-4
    # 样本必须落在解析极值内
    chk = a["analytical_extreme_check"]
    assert chk["within_physical_envelope"] is True
    assert chk["samples_below_wc_min"] == 0
    assert chk["samples_above_wc_max"] == 0
    # MC 与 RSS 交叉核对：±3σ 截断正态的实际 σ 约为未截断的 0.973 倍
    rss_std = np.hypot(0.025 / 6, 0.016 / 6)
    assert 0.95 * rss_std < a["std_mm"] <= rss_std * 1.001
    # 主导环可追溯
    names = {x["name"] for x in a["contributors"]}
    assert names == {"孔 φ50H7", "轴 φ50g6"}
    assert abs(sum(x["share"] for x in a["contributors"]) - 1.0) < 1e-9


# ---------- 未知分布：不自动设正态 ----------
def test_unknown_distribution_blocks_statistics_but_keeps_worst_case():
    dims = [
        dict(name="A", nominal=10.0, lower_deviation=-0.05, upper_deviation=0.05,
             dimension_unit="mm", direction=1, source="measured",
             distribution_kind="unknown", distribution_params={}),
        dict(name="B", nominal=10.0, lower_deviation=-0.02, upper_deviation=0.02,
             dimension_unit="mm", direction=-1, source="design",
             distribution_kind="uniform", distribution_params={}),
    ]
    res = tolerance.analyze(dims, n_samples=10_000, seed=SEED)
    assert res["rss"] is None
    assert res["monte_carlo"] is None
    assert len(res["statistical_blockers"]) == 1
    assert "不能自动假设正态" in res["statistical_blockers"][0]
    wc = res["worst_case"]
    assert wc["minimum_mm"] == pytest.approx(-0.07)
    assert wc["maximum_mm"] == pytest.approx(0.07)


# ---------- 单边公差：不能按对称范围处理 ----------
def test_one_sided_tolerance_mean_shift_not_symmetrized():
    dims = [
        dict(name="冷态间隙", nominal=0.5, lower_deviation=-0.02, upper_deviation=0.04,
             dimension_unit="mm", direction=1, source="measured",
             distribution_kind="uniform", distribution_params={}),
        dict(name="热膨胀", nominal=0.24, lower_deviation=0.0, upper_deviation=0.06,
             dimension_unit="mm", direction=-1, source="thermal_expansion",
             distribution_kind="uniform", distribution_params={}),
    ]
    res = tolerance.analyze(dims, n_samples=200_000, seed=SEED)
    wc = res["worst_case"]
    # G = 0.50(+0.04/-0.02) - 0.24(+0.06/0)
    assert wc["minimum_mm"] == pytest.approx(0.50 - 0.02 - 0.24 - 0.06)  # 0.18
    assert wc["maximum_mm"] == pytest.approx(0.50 + 0.04 - 0.24 - 0.00)  # 0.30
    assert wc["nominal_mm"] == pytest.approx(0.26)
    r = res["rss"]
    # 非对称均匀分布：均值平移 (+0.01) 与 (-0.03 经减环) = 0.01-0.03 = -0.02
    assert r["mean_shift_from_nominal_mm"] == pytest.approx(-0.02)
    assert r["mean_mm"] == pytest.approx(0.24)
    # 若错误地对称化成 ±0.03，均值平移将为 0 —— 这里必须不为 0
    assert abs(r["mean_shift_from_nominal_mm"]) > 1e-9


def test_one_sided_normal_keeps_mean_shift_not_symmetrized():
    """单边带 [0,+0.05] 登记正态：均值必须是 +0.025，而非围绕名义值的对称 ±0.025。"""
    dims = [
        dict(name="轴台阶", nominal=20.0, lower_deviation=0.0, upper_deviation=0.05,
             dimension_unit="mm", direction=1, source="design",
             distribution_kind="normal", distribution_params={**NORMAL3, "basis": "实测CMM"}),
    ]
    res = tolerance.analyze(dims, n_samples=200_000, seed=SEED)
    assert not res["statistical_blockers"]
    assert res["rss"] is not None and res["monte_carlo"] is not None
    r, mc = res["rss"], res["monte_carlo"]
    assert r["mean_mm"] == pytest.approx(20.025)
    assert r["mean_shift_from_nominal_mm"] == pytest.approx(0.025)  # 不能为 0
    assert r["lower_mm"] == pytest.approx(20.025 - 3 * 0.05 / 6)
    # 假设提示必须点明单边带与带中点建模
    assert any("单边" in n for n in res["assumption_notes"])
    # 极值仍然成立：[20, 20.05]
    assert res["worst_case"]["minimum_mm"] == pytest.approx(20.0)
    assert res["worst_case"]["maximum_mm"] == pytest.approx(20.05)
    # MC 样本严格落在带内，均值同样平移
    assert mc["analytical_extreme_check"]["within_physical_envelope"]
    assert mc["mean_mm"] == pytest.approx(20.025, abs=1e-4)
    assert mc["sample_min_mm"] >= 20.0 - 1e-12


# ---------- 零公差基准 ----------
def test_zero_tolerance_datum_deterministic():
    dims = [
        dict(name="B0", nominal=60.0, lower_deviation=0.0, upper_deviation=0.0,
             dimension_unit="mm", direction=1, source="datum",
             distribution_kind="deterministic", distribution_params={}),
        dict(name="L1", nominal=30.0, lower_deviation=-0.03, upper_deviation=0.03,
             dimension_unit="mm", direction=-1, source="design",
             distribution_kind="uniform", distribution_params={}),
        dict(name="L2", nominal=30.0, lower_deviation=-0.05, upper_deviation=0.05,
             dimension_unit="mm", direction=-1, source="design",
             distribution_kind="uniform", distribution_params={}),
    ]
    res = tolerance.analyze(dims, n_samples=100_000, seed=SEED)
    wc = res["worst_case"]
    assert wc["minimum_mm"] == pytest.approx(-0.08)
    assert wc["maximum_mm"] == pytest.approx(0.08)
    assert wc["tolerance_span_mm"] == pytest.approx(0.16)
    datum = next(c for c in wc["contributors"] if c["name"] == "B0")
    assert datum["band_width_mm"] == 0.0 and datum["share"] == 0.0
    mc = res["monte_carlo"]
    datum_mc = next(c for c in mc["contributors"] if c["name"] == "B0")
    assert datum_mc["spearman_with_closing"] == 0.0
    assert mc["analytical_extreme_check"]["within_physical_envelope"]
    # L2 带宽最大，为最坏情况主导；方差贡献也最大
    assert wc["contributors"][0]["name"] == "L2"
    assert res["rss"]["contributors"][0]["name"] == "L2"


# ---------- 单位与方向 ----------
def test_mixed_units_are_converted_not_added_directly():
    dims = [
        dict(name="孔", nominal=50_000.0, lower_deviation=0.0, upper_deviation=25.0,
             dimension_unit="um", direction=1, source="design",
             distribution_kind="normal", distribution_params=NORMAL3),
        dict(name="轴", nominal=50.0, lower_deviation=-0.025, upper_deviation=-0.009,
             dimension_unit="mm", direction=-1, source="design",
             distribution_kind="normal", distribution_params=NORMAL3),
    ]
    res = tolerance.analyze(dims, n_samples=50_000, seed=SEED)
    assert res["worst_case"]["maximum_mm"] == pytest.approx(0.050)
    assert res["worst_case"]["minimum_mm"] == pytest.approx(0.009)
    assert res["unit_conversions"] and res["unit_conversions"][0]["name"] == "孔"
    assert res["unit_conversions"][0]["factor_to_base"] == pytest.approx(0.001)
    assert any("换算" in w for w in res["warnings"])


def test_wrong_direction_is_flagged_against_expected_nominal():
    # 孔、轴都按减环（典型的方向录入错误），名义叠加值由 0 变成 -100
    dims = [
        dict(name="孔", nominal=50.0, lower_deviation=0.0, upper_deviation=0.025,
             dimension_unit="mm", direction=-1, source="design",
             distribution_kind="uniform", distribution_params={"basis": "x"}),
        dict(name="轴", nominal=50.0, lower_deviation=-0.025, upper_deviation=-0.009,
             dimension_unit="mm", direction=-1, source="design",
             distribution_kind="uniform", distribution_params={"basis": "x"}),
    ]
    res = tolerance.analyze(dims, n_samples=5_000, seed=SEED,
                            expected_closing_nominal=0.0)
    assert res["nominal_residual_mm"] == pytest.approx(-100.0)
    assert any("方向" in w for w in res["warnings"])


def test_invalid_unit_and_band_raise():
    with pytest.raises(tolerance.ToleranceError, match="单位"):
        tolerance.analyze(
            [dict(name="X", nominal=1, lower_deviation=0, upper_deviation=0.01,
                  dimension_unit="cm", direction=1, source="design",
                  distribution_kind="uniform", distribution_params={})],
            n_samples=100, seed=SEED,
        )
    with pytest.raises(tolerance.ToleranceError, match="公差带非法"):
        tolerance.analyze(
            [dict(name="X", nominal=1, lower_deviation=0.02, upper_deviation=0.0,
                  dimension_unit="mm", direction=1, source="design",
                  distribution_kind="uniform", distribution_params={})],
            n_samples=100, seed=SEED,
        )


# ---------- 热膨胀线性项工具 ----------
def test_thermal_term_nominal_and_one_sided_band():
    term = tolerance.thermal_expansion_term(
        alpha_per_c=12e-6, length_mm=500.0, delta_t_c=40.0,
        delta_t_lower_c=0.0, delta_t_upper_c=10.0, uncertainty_kind="uniform",
    )
    assert term["nominal"] == pytest.approx(0.24)
    assert term["lower_deviation"] == pytest.approx(0.0, abs=1e-15)
    assert term["upper_deviation"] == pytest.approx(0.06)
    assert term["source"] == "thermal_expansion"
    assert term["distribution_kind"] == "uniform"
