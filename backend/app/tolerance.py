"""尺寸公差链计算引擎（NumPy / SciPy）。

约定与前提
----------
封闭环方程（线性化）:
    X0 = Σ s_i · a_i
其中 a_i 为第 i 个组成环名义尺寸（已换算到尺寸链基准单位），
s_i = direction ∈ {+1, -1} 为该环方向（增环/减环）。

第 i 环实际尺寸在 [a_i + l_i, a_i + u_i] 内，l_i/u_i 为下/上偏差。
线性叠加时封闭环极值：
    X0_max = X0 + ES0,  ES0 = Σ(增环 u_i) + Σ(减环 -l_i)
    X0_min = X0 + EI0,  EI0 = Σ(增环 l_i) + Σ(减环 -u_i)

注意：Σ|T_i| 是封闭环公差带“宽度”，不是最终间隙本身。最终间隙是一个
带方向的区间 [X0_min, X0_max]，名义值 X0 可能不为零，单边偏差还会平移均值。

分布处理原则
- UNKNOWN（未知分布）：只参与最坏极值；RSS/MC 不自动套用正态，直接阻断并说明。
- NORMAL 为“一般截断正态”：偏差均值取带中点 m=(l+u)/2，σ=(u-l)/(2k)
  （默认 k=3），并在 [l,u] 物理边界截断。这样单边带（如 H7 的 [0,+T]）
  的均值如实取 +T/2，绝不被折叠成围绕名义值的 ±T/2 对称范围；同时给出
  明确的非阻断假设提示，要求登记依据 basis。
- 单边公差（l=0 或 u=0）也可用 UNIFORM / TRIANGULAR，同样保留非对称区间。
- DETERMINISTIC：零公差基准环，采样恒等于名义偏差 0。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

# 长度单位 -> mm 的换算系数
UNIT_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "um": 0.001,        # 微米
    "µm": 0.001,
    "inch": 25.4,
    "in": 25.4,
}

PREMISES = {
    "worst_case": (
        "最坏极值法前提：所有组成环同时取到对封闭环最不利的极限尺寸（完全相关、"
        "100% 互换）。结果给出理论保证的包络区间，不假设任何尺寸分布，"
        "未知分布与单边公差均可如实参与。代价是结果最保守。"
    ),
    "rss": (
        "均方根（RSS）法前提：各组成环相互独立，均值按各自显式分布假设传递，"
        "方差线性相加 σ0 = √Σσi²（线性传递，梯度为 ±1）。报告区间取 "
        "均值 ± kσ（k=3 时若封闭环近似正态约为 99.73%）；单边/非对称公差带"
        "导致的均值平移已计入。正态环按带内截断正态建模，截断会轻微降低"
        "真实标准差，故 RSS 对正态环略偏保守。存在未知分布时不予计算。"
    ),
    "monte_carlo": (
        "蒙特卡洛法前提：按每环显式登记的分布假设独立抽样（固定种子可复现），"
        "逐样本做线性叠加得到封闭环经验分布。它如实反映单边公差导致的均值平移"
        "与非正态封闭环；未知分布的环不臆造分布，整体阻断计算。"
        "经验最小/最大值是抽样结果，不替代解析极值保证。"
    ),
}

DISCLAIMER = (
    "本工具用于设计阶段的公差分析与方案比较，不替代首件检验、SPC、"
    "量具能力分析或按图纸/合同进行的制造验收判定。"
)


class ToleranceError(ValueError):
    """输入数据或前提不满足时抛出（由路由转成 422 可读信息）。"""


@dataclass(frozen=True)
class PreparedDim:
    key: str
    name: str
    direction: int
    nominal_mm: float
    lower_mm: float
    upper_mm: float
    source: str
    dist_kind: str
    dist_params: dict
    unit: str

    @property
    def band(self) -> float:
        return self.upper_mm - self.lower_mm

    @property
    def is_symmetric(self) -> bool:
        return np.isclose(self.lower_mm, -self.upper_mm)

    @property
    def is_one_sided(self) -> bool:
        return np.isclose(self.lower_mm, 0.0) ^ np.isclose(self.upper_mm, 0.0)


def _to_mm(value: float, unit: str, what: str) -> float:
    factor = UNIT_TO_MM.get(unit.lower())
    if factor is None:
        raise ToleranceError(f"{what} 使用了不支持的单位 '{unit}'，支持：mm / um / inch")
    return value * factor


def prepare(dims: list[dict]) -> list[PreparedDim]:
    """把 API/ORM 传入的组成环字典换算为基准单位（mm）下的 PreparedDim。"""
    prepared: list[PreparedDim] = []
    for i, d in enumerate(dims):
        name = d.get("name") or f"第{i + 1}环"
        unit = (d.get("dimension_unit") or "mm").strip()
        nom = _to_mm(float(d["nominal"]), unit, f"组成环 '{name}' 名义值")
        lo = _to_mm(float(d.get("lower_deviation", 0.0)), unit, f"'{name}' 下偏差")
        hi = _to_mm(float(d.get("upper_deviation", 0.0)), unit, f"'{name}' 上偏差")
        direction = int(d.get("direction", 1))
        if direction not in (1, -1):
            raise ToleranceError(f"组成环 '{name}' 的 direction 只能是 +1 或 -1，收到 {direction}")
        if hi < lo and not np.isclose(hi, lo):
            raise ToleranceError(
                f"组成环 '{name}' 上偏差({d.get('upper_deviation')}{unit}) 小于"
                f"下偏差({d.get('lower_deviation')}{unit})，公差带非法。"
            )
        prepared.append(
            PreparedDim(
                key=f"dim_{d.get('id') or i}",
                name=name,
                direction=direction,
                nominal_mm=nom,
                lower_mm=lo,
                upper_mm=hi,
                source=str(d.get("source", "design")),
                dist_kind=str(d.get("distribution_kind", "unknown")),
                dist_params=dict(d.get("distribution_params") or {}),
                unit=unit,
            )
        )
    if not prepared:
        raise ToleranceError("尺寸链至少需要一个组成环。")
    return prepared


def _statistical_blockers(dims: list[PreparedDim]) -> list[str]:
    """返回 RSS/MC 不应计算的硬性原因（未知分布等）。"""
    reasons: list[str] = []
    for d in dims:
        if d.dist_kind == "unknown":
            reasons.append(
                f"组成环 '{d.name}' 的分布为“未知”：不能自动假设正态。"
                "请显式登记分布（normal/uniform/triangular）后再做 RSS/蒙特卡洛；"
                "最坏极值法不受影响。"
            )
        elif d.dist_kind == "normal" and np.isclose(d.band, 0.0):
            reasons.append(f"组成环 '{d.name}' 为零公差却登记为正态分布，请改用 deterministic。")
        elif d.dist_kind not in ("normal", "uniform", "triangular", "deterministic"):
            reasons.append(f"组成环 '{d.name}' 的分布类型 '{d.dist_kind}' 不受支持。")
    return reasons


def _assumption_notes(dims: list[PreparedDim]) -> list[str]:
    """非阻断提示：把建模假设讲清楚（单边正态、缺少依据等）。"""
    notes: list[str] = []
    for d in dims:
        if d.dist_kind == "normal" and not np.isclose(d.band, 0.0) and not d.is_symmetric:
            kind = "单边" if d.is_one_sided else "非对称双边"
            k = float(d.dist_params.get("sigma_side", 3.0))
            notes.append(
                f"组成环 '{d.name}' 是{kind}公差带 [{d.lower_mm:+.6g}, {d.upper_mm:+.6g}] mm。"
                f"按显式登记的截断正态建模：偏差均值取带中点 "
                f"{(d.lower_mm + d.upper_mm) / 2:.6g} mm、σ=带宽/(2k)、k={k:g}，"
                "并在带内截断。这不是把单边带对称化（±T/2），也不是缺省结论；"
                "有实测数据时应以拟合分布替换。"
            )
        if d.dist_kind in ("normal", "uniform", "triangular") and not d.dist_params.get("basis"):
            notes.append(
                f"组成环 '{d.name}' 的 {d.dist_kind} 分布未在 distribution_params.basis "
                "中写明依据（工艺能力/实测/经验值），请在发布结论前补充。"
            )
    return notes


def worst_case(dims: list[PreparedDim]) -> dict:
    """解析极值法：名义值、上下偏差、极值区间与各环对总带宽的贡献。"""
    nominal = sum(d.direction * d.nominal_mm for d in dims)
    es = 0.0  # 封闭环上偏差
    ei = 0.0  # 封闭环下偏差
    for d in dims:
        if d.direction == 1:
            es += d.upper_mm
            ei += d.lower_mm
        else:
            # 减环：被减尺寸取最大时封闭环最小
            es += -d.lower_mm
            ei += -d.upper_mm

    x_max = nominal + es
    x_min = nominal + ei
    span = x_max - x_min
    total_abs_tol = sum(d.band for d in dims)

    contributions = [
        {
            "key": d.key,
            "name": d.name,
            "direction": d.direction,
            # 对总带宽的贡献即各自带宽；方向影响区间位置，不影响带宽
            "band_width_mm": d.band,
            "share": (d.band / total_abs_tol) if total_abs_tol > 0 else 0.0,
        }
        for d in dims
    ]
    contributions.sort(key=lambda c: c["band_width_mm"], reverse=True)

    return {
        "nominal_mm": nominal,
        "upper_deviation_mm": es,
        "lower_deviation_mm": ei,
        "maximum_mm": x_max,
        "minimum_mm": x_min,
        "tolerance_span_mm": span,
        "sum_absolute_tolerances_mm": total_abs_tol,
        "absolute_sum_note": (
            f"Σ|Tᵢ| = {total_abs_tol:.6g} mm 是各环公差绝对值之和，"
            f"即封闭环公差带宽度，不是最终间隙。最终封闭区间为 "
            f"[{x_min:.6g}, {x_max:.6g}] mm，名义值 {nominal:.6g} mm；"
            "若组成环方向或封闭环正方向定义改变，数值与过盈/间隙含义都会改变。"
        ),
        "contributors": contributions,
        "premises": PREMISES["worst_case"],
    }


def _normal_k(d: PreparedDim) -> float:
    k = float(d.dist_params.get("sigma_side", 3.0))
    if k <= 0:
        raise ToleranceError(f"正态环 '{d.name}' 的 sigma_side(k) 必须为正数。")
    return k


def _dim_mean_std(d: PreparedDim) -> tuple[float, float]:
    """组成环偏差（相对名义值）的均值与标准差，单位 mm。

    正态环按未截断矩给出 σ=带宽/(2k)，与 RSS 的经典解析公式一致；
    截断效应（k=3 时约 −2.7%）在前提中说明，MC 结果展示真实截断矩。
    """
    l, u = d.lower_mm, d.upper_mm
    if d.dist_kind == "deterministic" or np.isclose(d.band, 0.0):
        return 0.0, 0.0
    if d.dist_kind == "uniform":
        return (l + u) / 2.0, (u - l) / np.sqrt(12.0)
    if d.dist_kind == "triangular":
        mode = float(d.dist_params.get("mode_offset", (l + u) / 2.0))
        if not (l - 1e-12 <= mode <= u + 1e-12):
            raise ToleranceError(f"三角分布环 '{d.name}' 的众数 {mode} 超出公差带 [{l},{u}]。")
        mean = (l + u + mode) / 3.0
        var = (l**2 + u**2 + mode**2 - l * u - l * mode - mode * u) / 18.0
        return mean, float(np.sqrt(max(var, 0.0)))
    if d.dist_kind == "normal":
        k = _normal_k(d)
        return (l + u) / 2.0, (u - l) / (2.0 * k)
    raise ToleranceError(f"环 '{d.name}' 分布 {d.dist_kind} 无法计算 RSS 矩。")


def rss(dims: list[PreparedDim], k_sigma: float = 3.0) -> dict:
    """均方根法：均值传递 + √Σσ²，区间取 ±kσ。"""
    nominal = sum(d.direction * d.nominal_mm for d in dims)
    mean_offset = 0.0
    var = 0.0
    for d in dims:
        mu_i, sd_i = _dim_mean_std(d)
        mean_offset += d.direction * mu_i  # 非对称带导致的均值平移按方向传递
        var += sd_i**2                     # 方差与方向无关（系数 ±1，平方为 1）

    std = float(np.sqrt(var))
    mean = nominal + mean_offset
    contributors = []
    for d in dims:
        _, sd_i = _dim_mean_std(d)
        contributors.append(
            {
                "key": d.key,
                "name": d.name,
                "direction": d.direction,
                "variance_mm2": sd_i**2,
                "std_mm": sd_i,
                "share": (sd_i**2 / var) if var > 0 else 0.0,
            }
        )
    contributors.sort(key=lambda c: c["variance_mm2"], reverse=True)

    return {
        "mean_mm": mean,
        "std_mm": std,
        "k_sigma": k_sigma,
        "lower_mm": mean - k_sigma * std,
        "upper_mm": mean + k_sigma * std,
        "mean_shift_from_nominal_mm": mean_offset,
        "contributors": contributors,
        "premises": PREMISES["rss"],
    }


def _sample_dim(rng: np.random.Generator, d: PreparedDim, n: int) -> np.ndarray:
    """按登记分布对第 i 环偏差（相对名义值）抽样，单位 mm。"""
    l, u = d.lower_mm, d.upper_mm
    if d.dist_kind == "deterministic" or np.isclose(d.band, 0.0):
        return np.zeros(n)
    if d.dist_kind == "uniform":
        return rng.uniform(l, u, n)
    if d.dist_kind == "triangular":
        mode = float(d.dist_params.get("mode_offset", (l + u) / 2.0))
        c = (mode - l) / (u - l)
        return stats.triang.rvs(c, loc=l, scale=(u - l), size=n, random_state=rng)
    if d.dist_kind == "normal":
        k = _normal_k(d)
        sd = (u - l) / (2.0 * k)
        # 截断点相对“带中点均值”的标准化坐标恒为 (-k, k)
        trunc = stats.truncnorm(-k, k, loc=(l + u) / 2.0, scale=sd)
        return trunc.rvs(size=n, random_state=rng)
    raise ToleranceError(f"环 '{d.name}' 分布 {d.dist_kind} 无法抽样。")


def monte_carlo(
    dims: list[PreparedDim],
    n_samples: int,
    seed: int,
    acceptance: tuple[float | None, float | None] | None = None,
) -> dict:
    """固定种子蒙特卡洛：封闭环经验分布、解析极值核对与主导环（Spearman）。"""
    if n_samples <= 0:
        raise ToleranceError("蒙特卡洛抽样数必须为正整数。")
    nominal = sum(d.direction * d.nominal_mm for d in dims)
    rng = np.random.default_rng(seed)

    samples = np.empty((len(dims), n_samples))
    for i, d in enumerate(dims):
        samples[i, :] = _sample_dim(rng, d, n_samples)

    signs = np.array([d.direction for d in dims], dtype=float)
    y = nominal + signs @ samples  # 逐样本线性叠加

    pct = np.percentile(y, [0.1, 1, 5, 50, 95, 99, 99.9])
    counts, edges = np.histogram(y, bins=60)
    result = {
        "n_samples": n_samples,
        "seed": seed,
        "mean_mm": float(np.mean(y)),
        "std_mm": float(np.std(y, ddof=1)),
        "p0_1_mm": float(pct[0]),
        "p1_mm": float(pct[1]),
        "p5_mm": float(pct[2]),
        "p50_mm": float(pct[3]),
        "p95_mm": float(pct[4]),
        "p99_mm": float(pct[5]),
        "p99_9_mm": float(pct[6]),
        "sample_min_mm": float(np.min(y)),
        "sample_max_mm": float(np.max(y)),
        "histogram": {
            "bin_edges": [float(x) for x in edges],
            "counts": [int(x) for x in counts],
        },
    }

    # 与解析极值核对：样本不得落在物理可行域之外
    wc = worst_case(dims)
    lo_bad = int(np.count_nonzero(y < wc["minimum_mm"] - 1e-9))
    hi_bad = int(np.count_nonzero(y > wc["maximum_mm"] + 1e-9))
    result["analytical_extreme_check"] = {
        "wc_min_mm": wc["minimum_mm"],
        "wc_max_mm": wc["maximum_mm"],
        "samples_below_wc_min": lo_bad,
        "samples_above_wc_max": hi_bad,
        "within_physical_envelope": lo_bad == 0 and hi_bad == 0,
        "note": (
            "解析极值是保证包络；若有样本越界说明抽样/模型有缺陷。"
            "样本极值通常比解析极值更靠近中心，不能用样本极值代替保证。"
        ),
    }

    # 主导环：各环样本与封闭环的 Spearman 等级相关。相关符号本身携带方向
    # 信息（增环为正相关、减环为负相关），绝对值归一化为贡献占比。
    rho_rows = []
    for d, row in zip(dims, samples):
        rho = 0.0 if (np.isclose(d.band, 0.0) or np.std(row) == 0.0) else float(
            stats.spearmanr(row, y).statistic
        )
        rho_rows.append((d, rho))
    total_abs = sum(abs(r) for _, r in rho_rows)
    contributors = [
        {
            "key": d.key,
            "name": d.name,
            "direction": d.direction,
            "spearman_with_closing": r,
            "share": (abs(r) / total_abs) if total_abs > 0 else 0.0,
        }
        for d, r in rho_rows
    ]
    contributors.sort(key=lambda c: abs(c["spearman_with_closing"]), reverse=True)
    result["contributors"] = contributors

    if acceptance and (acceptance[0] is not None or acceptance[1] is not None):
        a_lo, a_hi = acceptance
        mask = np.ones(n_samples, dtype=bool)
        if a_lo is not None:
            mask &= y >= a_lo
        if a_hi is not None:
            mask &= y <= a_hi
        result["acceptance_estimate"] = {
            "lower_mm": a_lo,
            "upper_mm": a_hi,
            "fraction_within": float(np.mean(mask)),
            "fraction_outside": float(1.0 - np.mean(mask)),
            "note": "基于经验分布的估计比例，不是合格判定，不构成制造验收。",
        }

    result["premises"] = PREMISES["monte_carlo"]
    return result


def analyze(
    dims: list[dict],
    *,
    n_samples: int,
    seed: int,
    k_sigma: float = 3.0,
    expected_closing_nominal: float | None = None,
    acceptance: tuple[float | None, float | None] | None = None,
    base_unit: str = "mm",
) -> dict:
    """完整分析：校验 → 极值 →（可阻断的）RSS/MC → 方向单位核对与前提说明。"""
    prepared = prepare(dims)
    blockers = _statistical_blockers(prepared)
    notes = _assumption_notes(prepared)

    wc = worst_case(prepared)

    used_units = sorted({d.unit for d in prepared})
    warnings: list[str] = []
    unit_conversions: list[dict] = []
    if len(used_units) > 1 or used_units[0].lower() != base_unit.lower():
        warnings.append(
            f"组成环使用了混合/非基准单位 {used_units}，已全部换算到基准单位 "
            f"{base_unit} 后才参与运算；禁止跨单位直接相加。"
        )
        base_factor = UNIT_TO_MM[base_unit.lower()]
        for d in prepared:
            if d.unit.lower() != base_unit.lower():
                unit_conversions.append(
                    {
                        "name": d.name,
                        "from_unit": d.unit,
                        "factor_to_base": UNIT_TO_MM[d.unit.lower()] / base_factor,
                    }
                )

    # 方向 / 名义值核对
    nominal_residual = None
    if expected_closing_nominal is not None:
        nominal_residual = wc["nominal_mm"] - float(expected_closing_nominal)
        tol = 1e-9 + 1e-9 * max(1.0, abs(float(expected_closing_nominal)))
        if abs(nominal_residual) > tol:
            warnings.append(
                f"方向/名义核对：按各环 direction 叠加的封闭环名义值 "
                f"{wc['nominal_mm']:.6g} mm 与登记的目标名义值 "
                f"{float(expected_closing_nominal):.6g} mm 不一致，残差 "
                f"{nominal_residual:+.3g} mm。请核对增环/减环方向或目标定义，"
                "不要通过修改公差来抵消方向错误。"
            )

    if wc["minimum_mm"] < 0.0 < wc["maximum_mm"]:
        warnings.append(
            "封闭环极值区间跨越 0：同一线性模型下既可能出现间隙也可能出现过盈，"
            "请在图纸上明确配合性质与验收边界。"
        )
    elif wc["maximum_mm"] <= 0.0:
        warnings.append("按当前方向定义，封闭环极值区间 ≤ 0：对“间隙”而言属于过盈。")

    rss_result = None
    mc_result = None
    cross_check = None
    if not blockers:
        rss_result = rss(prepared, k_sigma=k_sigma)
        mc_result = monte_carlo(
            prepared, n_samples=n_samples, seed=seed, acceptance=acceptance
        )
        # RSS（未截断矩）与 MC（截断抽样）交叉核对
        cross_check = {
            "mean_abs_diff_mm": abs(rss_result["mean_mm"] - mc_result["mean_mm"]),
            "std_relative_diff": (
                abs(rss_result["std_mm"] - mc_result["std_mm"]) / mc_result["std_mm"]
                if mc_result["std_mm"] > 0 else 0.0
            ),
            "note": (
                "固定种子下两种方法均值应几乎一致；RSS 标准差按未截断正态解析矩，"
                "MC 为截断后样本估计，k=3 截断使 MC 的 σ 略小（约 2.7%），属预期。"
            ),
        }
    else:
        warnings.append("统计方法未执行：" + "；".join(blockers))

    if acceptance and mc_result and "acceptance_estimate" in mc_result:
        est = mc_result["acceptance_estimate"]
        if est["fraction_outside"] > 0:
            warnings.append(
                f"蒙特卡洛估计有 {est['fraction_outside'] * 100:.3f}% 样本位于"
                f"验收区间 [{est['lower_mm']}, {est['upper_mm']}] 之外（仅设计参考）。"
            )

    leading_wc = wc["contributors"][0] if wc["contributors"] else None
    summary = {
        "tolerance_band_dominator": leading_wc,
        "variance_dominator": (
            rss_result["contributors"][0] if rss_result and rss_result["contributors"] else None
        ),
        "sampling_dominator": (
            mc_result["contributors"][0] if mc_result and mc_result["contributors"] else None
        ),
    }

    return {
        "base_unit": "mm",
        "worst_case": wc,
        "rss": rss_result,
        "monte_carlo": mc_result,
        "statistical_blockers": blockers,
        "assumption_notes": notes,
        "warnings": warnings,
        "unit_conversions": unit_conversions,
        "nominal_residual_mm": nominal_residual,
        "cross_check": cross_check,
        "dominance_summary": summary,
        "disclaimer": DISCLAIMER,
    }


def thermal_expansion_term(
    *,
    alpha_per_c: float,
    length_mm: float,
    delta_t_c: float,
    delta_t_lower_c: float | None = None,
    delta_t_upper_c: float | None = None,
    uncertainty_kind: str = "uniform",
    name: str = "热膨胀线性项 ΔL=α·L·ΔT",
) -> dict:
    """生成热膨胀简化线性项组成环字典（可直接 POST 进尺寸链）。

    - 名义项 ΔL = α·L·ΔT，冷缩时 ΔT 传负号，而不是改 direction；
    - 温度不确定区间 [ΔT_lo, ΔT_ub]（相对名义 ΔT 的增量）换算为 ΔL 偏差，
      支持单边（其一为 0），如实保留非对称；
    - 仅一阶线性近似，不含温度梯度、约束应力与材料非线性。
    """
    nominal = alpha_per_c * length_mm * delta_t_c
    lower = upper = 0.0
    params: dict = {
        "alpha": alpha_per_c,
        "length_mm": length_mm,
        "delta_t_c": delta_t_c,
    }
    if delta_t_lower_c is not None or delta_t_upper_c is not None:
        if delta_t_lower_c is None or delta_t_upper_c is None:
            raise ToleranceError("温度不确定区间必须同时给出上下界，单边时令其中一个为 0。")
        if delta_t_upper_c < delta_t_lower_c:
            raise ToleranceError("温度不确定上界小于下界。")
        k = alpha_per_c * length_mm
        lower, upper = sorted((k * delta_t_lower_c, k * delta_t_upper_c))
        params["delta_t_uncertainty_c"] = [delta_t_lower_c, delta_t_upper_c]

    if np.isclose(lower, upper):
        kind = "deterministic"
    else:
        kind = {"uniform": "uniform", "triangular": "triangular", "unknown": "unknown"}.get(
            uncertainty_kind
        )
        if kind is None:
            raise ToleranceError("热膨胀温度不确定只支持 uniform / triangular / unknown。")

    return {
        "name": name,
        "nominal": nominal,
        "lower_deviation": lower,
        "upper_deviation": upper,
        "dimension_unit": "mm",
        "direction": 1,
        "source": "thermal_expansion",
        "source_detail": (
            f"简化线性项 α={alpha_per_c:g}/°C, L={length_mm:g} mm, "
            f"ΔT={delta_t_c:g}°C（相对装配基准温度 20°C，一阶近似）"
        ),
        "distribution_kind": kind,
        "distribution_params": params,
    }
