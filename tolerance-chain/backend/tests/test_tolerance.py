"""核对测试：解析极值、固定种子复现、方向/单位/单边/未知分布前提。"""
import math

import numpy as np
import pytest

from app import tolerance as T


# --------------------------------------------------------------------------- #
# 1. 轴孔配合 50H8/f7：解析极限 [0.025, 0.089]
# --------------------------------------------------------------------------- #
SHAFT_HOLE = [
    {"key": "bore", "name": "孔 Φ50H8", "source": "图纸", "direction": 1,
     "nominal": 50.0, "es": 0.039, "ei": 0.0, "unit": "mm",
     "distribution": "halfnormal", "dist_params": {"sigma": 0.013}},
    {"key": "shaft", "name": "轴 Φ50f7", "source": "图纸", "direction": -1,
     "nominal": 50.0, "es": -0.025, "ei": -0.050, "unit": "mm",
     "distribution": "normal", "dist_params": {"sigma": 0.0083}},
]


def test_shaft_hole_worst_case_analytic_extremes():
    res = T.analyze(SHAFT_HOLE, "mm", methods=("worst_case",))["results"]["worst_case"]
    assert res["nominal"] == pytest.approx(0.0, abs=1e-12)
    assert res["gap_min"] == pytest.approx(0.025, abs=1e-12)
    assert res["gap_max"] == pytest.approx(0.089, abs=1e-12)
    # 公称间隙为 0，但中心因单边/不对称公差移动到 0.057
    assert res["gap_center"] == pytest.approx(0.057, abs=1e-12)
    assert res["interference_possible"] is False
    # 主导环：孔的单边公差带 0.039 比轴的 0.025 宽
    assert res["dominant_key"] == "bore"


def test_naive_absolute_sum_flagged_wrong():
    res = T.analyze(SHAFT_HOLE, "mm", methods=("worst_case",))["results"]["worst_case"]
    # 朴素绝对值求和 = 0.039+0.050 = 0.089，恰好等于 gap_max 但不是“最终间隙”
    assert res["naive_absolute_sum"] == pytest.approx(0.089)
    assert res["naive_absolute_sum_correct"] is False
    assert res["naive_warning"] is not None


# --------------------------------------------------------------------------- #
# 2. 热膨胀案例：mm/µm 混单位换算，解析极限手算
#    公称: (80-79.85) + (0.1104-0.0576) = 0.2028
#    偏差叠加（带方向）:
#      bore_nom(+)  ∈ [0, 0.05]
#      shaft_nom(-) ∈ [-0.02, +0.035]   （减环取反）
#      bore_th(+)   ∈ [-0.008, +0.008]
#      shaft_th(-)  ∈ [-0.015, +0.015]  （15 µm 换算后取反）
#    => min = 0.2028 + 0 - 0.02 - 0.008 - 0.015 = 0.1598
#       max = 0.2028 + 0.05 + 0.035 + 0.008 + 0.015 = 0.3108
#    （shaft_nom 为不对称公差 −0.035/+0.02，是极值带宽的主要来源）
# --------------------------------------------------------------------------- #
THERMAL = [
    {"key": "bore_nom", "name": "孔", "source": "图纸", "direction": 1,
     "nominal": 80.0, "es": 0.05, "ei": 0.0, "unit": "mm",
     "distribution": "triangular"},
    {"key": "shaft_nom", "name": "轴", "source": "图纸", "direction": -1,
     "nominal": 79.85, "es": 0.02, "ei": -0.035, "unit": "mm",
     "distribution": "triangular"},
    {"key": "bore_thermal", "name": "孔热膨胀", "source": "材料手册", "direction": 1,
     "nominal": 0.1104, "es": 0.008, "ei": -0.008, "unit": "mm",
     "distribution": "triangular"},
    {"key": "shaft_thermal", "name": "轴热膨胀", "source": "材料手册", "direction": -1,
     "nominal": 57.6, "es": 15.0, "ei": -15.0, "unit": "um",
     "distribution": "triangular"},
]


def test_thermal_linear_term_with_unit_conversion():
    res = T.analyze(THERMAL, "mm", methods=("worst_case",))["results"]["worst_case"]
    assert res["nominal"] == pytest.approx(0.2028, abs=1e-12)
    assert res["gap_min"] == pytest.approx(0.1598, abs=1e-12)
    assert res["gap_max"] == pytest.approx(0.3108, abs=1e-12)
    # 对称三角分布，带宽 = 0.05+0.055+0.016+0.030 = 0.151
    assert res["total_span"] == pytest.approx(0.151, abs=1e-12)


def test_triangular_monte_carlo_inside_extremes_fixed_seed():
    out = T.analyze(THERMAL, "mm", mc_samples=200_000, seed=42,
                    methods=("worst_case", "monte_carlo"))
    wc, mc = out["results"]["worst_case"], out["results"]["monte_carlo"]
    # 有界分布：任何样本都不能超出解析极值
    assert mc["samples_outside_extremes"] == 0
    assert mc["sample_min"] >= wc["gap_min"] - 1e-12
    assert mc["sample_max"] <= wc["gap_max"] + 1e-12
    # 固定种子完全复现
    mc2 = T.analyze(THERMAL, "mm", mc_samples=200_000, seed=42,
                    methods=("monte_carlo",))["results"]["monte_carlo"]
    assert mc["sample_mean"] == mc2["sample_mean"]
    assert mc["sample_min"] == mc2["sample_min"]
    # 不同种子结果可能不同（防止“固定种子”退化为常量）
    mc3 = T.analyze(THERMAL, "mm", mc_samples=200_000, seed=7,
                    methods=("monte_carlo",))["results"]["monte_carlo"]
    assert mc3["sample_mean"] != mc["sample_mean"]


def test_monte_carlo_dominance_traceable():
    mc = T.analyze(THERMAL, "mm", mc_samples=100_000, seed=1,
                   methods=("monte_carlo",))["results"]["monte_carlo"]
    shares = {r["key"]: r["variance_share"] for r in mc["per_ring"]}
    assert mc["dominant_key"] == max(shares, key=shares.get)
    # shaft_nom 公差带 0.055 最宽，应为方差主导
    assert mc["dominant_key"] == "shaft_nom"
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# 3. 零公差基准
# --------------------------------------------------------------------------- #
ZERO = [
    {"key": "housing", "name": "腔深", "source": "图纸", "direction": 1,
     "nominal": 40.0, "es": 0.10, "ei": 0.0, "unit": "mm",
     "distribution": "uniform"},
    {"key": "spacer", "name": "零公差基准", "source": "检定", "direction": -1,
     "nominal": 15.0, "es": 0.0, "ei": 0.0, "unit": "mm",
     "distribution": "unknown"},
    {"key": "step", "name": "轴段", "source": "图纸", "direction": -1,
     "nominal": 25.0, "es": 0.0, "ei": -0.05, "unit": "mm",
     "distribution": "uniform"},
]


def test_zero_tolerance_datum():
    out = T.analyze(ZERO, "mm", mc_samples=50_000, seed=99,
                    methods=("worst_case", "rss", "monte_carlo"))
    wc, rss, mc = (out["results"]["worst_case"], out["results"]["rss"],
                   out["results"]["monte_carlo"])
    # 公称 40-15-25=0。housing∈[40,40.1]、spacer=15、step∈[24.95,25]
    # => 间隙 [0, 0.15]，中心 0.075（两个单边公差共同平移）
    assert wc["gap_min"] == pytest.approx(0.0, abs=1e-12)
    assert wc["gap_max"] == pytest.approx(0.15, abs=1e-12)
    # 公差半宽 housing 0.05、step 0.025
    by_key = {r["key"]: r for r in wc["per_ring"]}
    assert by_key["spacer"]["dominance_share"] == 0.0
    assert by_key["housing"]["dominance_share"] == pytest.approx(2 / 3, abs=1e-9)
    # 蒙特卡洛里零公差环样本标准差为 0，主导是 housing（均匀宽度 0.10）
    mc_by_key = {r["key"]: r for r in mc["per_ring"]}
    assert mc_by_key["spacer"]["sample_sd"] == 0.0
    assert mc["dominant_key"] == "housing"
    assert mc["samples_outside_extremes"] == 0


# --------------------------------------------------------------------------- #
# 4. 未知分布：统计方法拒绝，但极值法照常
# --------------------------------------------------------------------------- #
UNKNOWN = [
    {"key": "slot", "name": "槽", "source": "供应商", "direction": 1,
     "nominal": 10.0, "es": 0.10, "ei": 0.0, "unit": "mm",
     "distribution": "unknown"},
    {"key": "tab", "name": "卡扣", "source": "供应商", "direction": -1,
     "nominal": 9.6, "es": 0.05, "ei": -0.05, "unit": "mm",
     "distribution": "unknown"},
]


def test_unknown_distribution_rejected_for_stats_ok_for_extremes():
    out = T.analyze(UNKNOWN, "mm", seed=3)
    assert "worst_case" in out["results"]
    wc = out["results"]["worst_case"]
    # 公称 10-9.6=0.4；min: slot ei=0 且 tab 反向 es=-(-?): 减环最小贡献 = -0.05
    # => 0.4 + 0 - 0.05 = 0.35；max: 0.4 + 0.10 + 0.05 = 0.55
    assert wc["gap_min"] == pytest.approx(0.35, abs=1e-12)
    assert wc["gap_max"] == pytest.approx(0.55, abs=1e-12)
    assert "rss" not in out["results"] and "monte_carlo" not in out["results"]
    assert "unknown" in out["method_errors"]["rss"]
    assert "unknown" in out["method_errors"]["monte_carlo"]


def test_halfnormal_requires_explicit_sigma():
    bad = [{**SHAFT_HOLE[0], "dist_params": {}},
           {**SHAFT_HOLE[1]}]
    with pytest.raises(T.ToleranceError, match="sigma"):
        T.normalize_rings(bad, "mm")


def test_halfnormal_rejects_symmetric_range():
    bad = [{**SHAFT_HOLE[0], "es": 0.039, "ei": -0.039},
           {**SHAFT_HOLE[1]}]
    with pytest.raises(T.ToleranceError, match="单边"):
        T.normalize_rings(bad, "mm")


# --------------------------------------------------------------------------- #
# 5. 方向 / 单位 / 闭合性检查
# --------------------------------------------------------------------------- #
def test_unclosed_chain_rejected():
    only_pos = [
        {"key": "a", "name": "A", "source": "x", "direction": 1,
         "nominal": 10, "es": 0.1, "ei": 0.0, "unit": "mm"},
        {"key": "b", "name": "B", "source": "x", "direction": 1,
         "nominal": 5, "es": 0.05, "ei": -0.05, "unit": "mm"},
    ]
    with pytest.raises(T.ToleranceError, match="闭合"):
        T.normalize_rings(only_pos, "mm")


def test_mixed_dimension_family_rejected():
    bad = [
        {"key": "a", "name": "A", "source": "x", "direction": 1,
         "nominal": 10, "es": 0.1, "ei": 0.0, "unit": "mm"},
        {"key": "b", "name": "B", "source": "x", "direction": -1,
         "nominal": 0.01, "es": 0.001, "ei": -0.001, "unit": "rad"},
    ]
    with pytest.raises(T.ToleranceError, match="量纲"):
        T.normalize_rings(bad, "mm")


def test_angle_chain_with_mrad_conversion():
    rings = [
        {"key": "a", "name": "角度增环", "source": "图纸", "direction": 1,
         "nominal": 10.0, "es": 2.0, "ei": -2.0, "unit": "mrad",
         "distribution": "uniform"},
        {"key": "b", "name": "角度减环", "source": "图纸", "direction": -1,
         "nominal": 0.0, "es": 0.001, "ei": -0.001, "unit": "rad",
         "distribution": "uniform"},
    ]
    wc = T.analyze(rings, "rad", methods=("worst_case",))["results"]["worst_case"]
    # 2 mrad = 0.002 rad 公差；b 0.001 rad。公称 0.010，中心 0.010
    assert wc["nominal"] == pytest.approx(0.010, abs=1e-15)
    assert wc["gap_min"] == pytest.approx(0.007, abs=1e-15)
    assert wc["gap_max"] == pytest.approx(0.013, abs=1e-15)


# --------------------------------------------------------------------------- #
# 6. RSS 矩与 MC 互核（均匀分布解析标准差 = 全宽/sqrt(12)）
# --------------------------------------------------------------------------- #
def test_rss_uniform_moments_match_monte_carlo():
    rings = [
        {"key": "a", "name": "A", "source": "x", "direction": 1,
         "nominal": 10.0, "es": 0.10, "ei": 0.0, "unit": "mm",
         "distribution": "uniform"},
        {"key": "b", "name": "B", "source": "x", "direction": -1,
         "nominal": 9.7, "es": 0.05, "ei": -0.05, "unit": "mm",
         "distribution": "uniform"},
    ]
    out = T.analyze(rings, "mm", mc_samples=400_000, seed=20261006)
    rss, mc = out["results"]["rss"], out["results"]["monte_carlo"]
    # 均值: 公称 0.3 + 0.05(A中点) = 0.35
    assert rss["gap_mean"] == pytest.approx(0.35, abs=1e-12)
    sd_exact = math.sqrt(0.10 ** 2 / 12 + 0.10 ** 2 / 12)
    assert rss["gap_sd"] == pytest.approx(sd_exact, rel=1e-12)
    # 大样本 MC 收敛到解析矩（0.2% 容差）
    assert mc["sample_mean"] == pytest.approx(rss["gap_mean"], abs=0.0005)
    assert mc["sample_sd"] == pytest.approx(rss["gap_sd"], rel=0.01)


def test_normal_can_exceed_extremes_but_uniform_cannot():
    # 正态无界：少量样本超出极值是允许且被标注的
    out = T.analyze(SHAFT_HOLE, "mm", mc_samples=500_000, seed=123,
                    methods=("monte_carlo",))
    mc = out["results"]["monte_carlo"]
    assert mc["samples_outside_extremes"] > 0
    assert "无界" in mc["outside_note"]
