"""尺寸公差链计算内核（纯函数，不依赖 Web/DB）。

关键工程原则（对应需求）：
1. 封闭环按组成环的 *方向* 做带符号叠加，绝不能把所有公差的绝对值直接相加：
   绝对值求和只在「全部为对称双向公差」时碰巧等于极值带宽，单边/不对称公差会
   得到错误的封闭环中心。
2. 单位与量纲在进入计算前统一：长度与角度两个量纲族，混用直接报错。
3. 三种结果前提不同：
   - worst_case（极值法）：100% 互换，不依赖分布，所有组成环同时达到极限；
   - rss（均方根/统计法）：独立、过程受控、需要显式分布假设，正态按 ±kσ 解释；
   - monte_carlo：按各自分布 *显式抽样*，固定种子可复现；未知分布一律拒绝，
     不会偷偷假设正态。
4. 单边公差（如孔 H8 的 +0.039/0）不按对称区间处理：统计法要求 halfnormal
   等单边分布并计入均值移动；极值法按真实的 es/ei 平移封闭环。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from scipy import stats as sstats


# --------------------------------------------------------------------------- #
# 单位处理：长度族与角度族。转换为该量纲的内部基准（mm / rad）。
# --------------------------------------------------------------------------- #
LENGTH_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "um": 1e-3,
    "µm": 1e-3,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "mil": 0.0254,  # 千分之一英寸
}
ANGLE_TO_RAD: dict[str, float] = {
    "rad": 1.0,
    "mrad": 1e-3,
    "deg": math.pi / 180.0,
}


class UnitFamily(str, Enum):
    LENGTH = "length"
    ANGLE = "angle"


def unit_family(unit: str) -> UnitFamily:
    u = unit.strip()
    if u in LENGTH_TO_MM:
        return UnitFamily.LENGTH
    if u in ANGLE_TO_RAD:
        return UnitFamily.ANGLE
    raise ToleranceError(f"未知单位 '{unit}'，支持的长度单位：{sorted(set(LENGTH_TO_MM))}；"
                         f"角度单位：{sorted(ANGLE_TO_RAD)}")


def conversion_factor(unit: str, family: UnitFamily) -> float:
    """把该单位的数值换算成内部基准单位（长度 mm / 角度 rad）。"""
    if family == UnitFamily.LENGTH:
        return LENGTH_TO_MM[unit]
    return ANGLE_TO_RAD[unit]


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #
class ToleranceError(ValueError):
    """输入或假设不满足计算前提（HTTP 层映射为 422）。"""


# --------------------------------------------------------------------------- #
# 分布定义
# --------------------------------------------------------------------------- #
class Distribution(str, Enum):
    UNKNOWN = "unknown"        # 未知：仅允许极值法
    NORMAL = "normal"          # 正态 N(中点, sigma)，sigma 必须显式给出
    UNIFORM = "uniform"        # 均匀 [ei, es]
    TRIANGULAR = "triangular"  # 三角分布 [ei, es]，众数取中点
    HALFNORMAL = "halfnormal"  # 半正态，仅允许单边公差 ei==0


# --------------------------------------------------------------------------- #
# 内部数据结构：所有数值已换算到封闭环单位
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Ring:
    key: str                 # 稳定标识，供结果追溯
    name: str
    source: str              # 尺寸来源（图纸/实测/供应商...）
    direction: int           # +1 增环 / -1 减环
    nominal: float           # 基本尺寸（封闭环单位）
    es: float                # 上偏差（封闭环单位），es >= ei
    ei: float                # 下偏差
    distribution: Distribution
    dist_params: dict[str, float] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        """偏差区间中点。单边公差时中点不为 0 —— 这就是不能对称化的原因。"""
        return (self.es + self.ei) / 2.0

    @property
    def half_width(self) -> float:
        """相对区间中点的半宽，恒 >= 0。"""
        return (self.es - self.ei) / 2.0

    @property
    def one_sided(self) -> bool:
        tol = max(abs(self.es), abs(self.ei))
        eps = 1e-12 * max(1.0, tol)
        return abs(self.ei) <= eps or abs(self.es) <= eps

    @property
    def zero_tolerance(self) -> bool:
        return abs(self.es - self.ei) <= 1e-15


# --------------------------------------------------------------------------- #
# 校验与归一化
# --------------------------------------------------------------------------- #
def _check_distribution(ring: Ring) -> None:
    """分布与公差形态的一致性检查。"""
    d = ring.distribution
    if d == Distribution.NORMAL:
        sig = ring.dist_params.get("sigma")
        if sig is None or sig <= 0:
            raise ToleranceError(
                f"尺寸 '{ring.name}' 声明为正态分布，必须显式给出正的 sigma "
                f"（与尺寸同单位，换算后使用）；系统不会自动假设正态。")
    if d == Distribution.HALFNORMAL:
        tol = max(abs(ring.es), abs(ring.ei))
        eps = 1e-12 * max(1.0, tol)
        # 半正态锚定在 0 偏差上，只用于 [0, T] 形式的单边公差
        if not (abs(ring.ei) <= eps and ring.es > 0):
            raise ToleranceError(
                f"尺寸 '{ring.name}' 的半正态分布只允许 [0, T] 形式的单边正公差"
                f"（当前 es={ring.es:g}, ei={ring.ei:g}）。单边公差不能按对称范围处理。")
        scale = ring.dist_params.get("sigma")
        if scale is None or scale <= 0:
            raise ToleranceError(
                f"尺寸 '{ring.name}' 的半正态分布必须显式给出 scale(sigma)>0。")
    if d in (Distribution.UNIFORM, Distribution.TRIANGULAR) and ring.zero_tolerance:
        raise ToleranceError(f"尺寸 '{ring.name}' 公差为 0，无法构造 {d.value} 分布。")


def normalize_rings(raw_rings: list[dict], closed_unit: str) -> list[Ring]:
    """把 API 输入（自带单位）换算到封闭环单位，并做全部前置校验。"""
    if not raw_rings:
        raise ToleranceError("尺寸链至少需要一个组成环。")

    closed_family = unit_family(closed_unit)

    rings: list[Ring] = []
    for i, r in enumerate(raw_rings):
        name = str(r.get("name") or f"尺寸{i + 1}")
        unit = str(r.get("unit") or "mm")
        family = unit_family(unit)
        if family != closed_family:
            raise ToleranceError(
                f"尺寸 '{name}' 的单位 {unit} 属于{family.value}量纲，"
                f"与封闭环单位 {closed_unit}（{closed_family.value}）不一致，"
                f"长度与角度不能混入同一条尺寸链。")

        factor = conversion_factor(unit, family)
        closed_factor = conversion_factor(closed_unit, closed_family)
        k = factor / closed_factor  # ring 单位 -> 封闭环单位

        direction = r.get("direction")
        if direction not in (1, -1, "+1", "-1"):
            raise ToleranceError(
                f"尺寸 '{name}' 的方向必须是 +1（增环）或 -1（减环），"
                f"收到 {direction!r}。")
        direction = int(direction)

        nominal = float(r["nominal"]) * k
        es = float(r["es"]) * k
        ei = float(r["ei"]) * k
        if es < ei:
            raise ToleranceError(
                f"尺寸 '{name}' 的上偏差 es({es:g}) 不能小于下偏差 ei({ei:g})。")

        dist_value = r.get("distribution", "unknown")
        try:
            dist = Distribution(dist_value)
        except ValueError:
            raise ToleranceError(
                f"尺寸 '{name}' 的分布 '{dist_value}' 不支持；"
                f"可选：{[d.value for d in Distribution]}")
        params_in = r.get("dist_params") or {}
        dist_params = {p: float(v) * k for p, v in params_in.items()}

        ring = Ring(
            key=str(r.get("key") or f"ring-{i + 1}"),
            name=name,
            source=str(r.get("source") or "未注明来源"),
            direction=direction,
            nominal=nominal,
            es=es,
            ei=ei,
            distribution=dist,
            dist_params=dist_params,
        )
        _check_distribution(ring)
        rings.append(ring)

    # 封闭尺寸链必须既有增环又有减环
    signs = {r.direction for r in rings}
    if signs != {1, -1}:
        raise ToleranceError(
            "尺寸链未闭合：封闭环检查要求组成环中同时存在增环(+1)与减环(-1)，"
            f"当前方向集合为 {sorted(signs)}。请核对每个尺寸的正负方向，"
            "例如轴孔配合间隙 = 孔径(+1) − 轴径(−1)。")

    # 键名唯一，方便追溯
    keys = [r.key for r in rings]
    if len(set(keys)) != len(keys):
        raise ToleranceError("组成环 key 必须唯一，否则无法追溯主导尺寸。")

    return rings


# --------------------------------------------------------------------------- #
# 极值法（worst case）—— 不需要分布
# --------------------------------------------------------------------------- #
def _signed_extremes(r: Ring) -> tuple[float, float]:
    """返回 (该环对封闭环偏差的最小贡献, 最大贡献)，已带方向符号。"""
    if r.direction == 1:
        return r.ei, r.es
    return -r.es, -r.ei  # 减环取反


def worst_case(rings: list[Ring]) -> dict:
    """极值法：所有组成环同时到达最不利极限（100% 互换前提）。"""
    nominal_gap = sum(r.direction * r.nominal for r in rings)

    per_ring = []
    g_min = nominal_gap
    g_max = nominal_gap
    total_half_width = 0.0
    for r in rings:
        lo, hi = _signed_extremes(r)
        g_min += lo
        g_max += hi
        total_half_width += r.half_width
        per_ring.append({
            "key": r.key,
            "name": r.name,
            "direction": r.direction,
            "min_contribution": r.direction * r.nominal + lo,
            "max_contribution": r.direction * r.nominal + hi,
            "half_width": r.half_width,
        })

    # 主导性：每个环的公差半宽占极值带宽的比例（零公差基准环贡献为 0）
    for item in per_ring:
        item["dominance_share"] = (
            item["half_width"] / total_half_width if total_half_width > 0 else 0.0)
    dominant = max(per_ring, key=lambda x: x["dominance_share"]) if per_ring else None

    # “绝对值直接相加”的朴素算法：把每环最大偏差绝对值求和。
    # 只有所有公差都关于公称尺寸对称（单边公差除外）时，它才与极值带宽相同；
    # 即使带宽碰巧相同，它也给不出封闭环中心的平移。
    naive_abs_total = sum(max(abs(r.es), abs(r.ei)) for r in rings)
    asym_rings = [r.name for r in rings if abs(r.mid) > 1e-15]
    span = g_max - g_min
    naive_correct = abs(naive_abs_total - span) <= 1e-12 * max(1.0, span) and not asym_rings

    return {
        "method": "worst_case",
        "premise": "假设所有组成环同时达到最不利极限，保证100%互换；不使用任何分布假设。",
        "nominal": nominal_gap,
        "gap_min": g_min,
        "gap_max": g_max,
        "gap_center": (g_min + g_max) / 2.0,
        "total_span": span,
        "naive_absolute_sum": naive_abs_total,
        "naive_absolute_sum_correct": naive_correct,
        "naive_warning": (
            None if naive_correct else
            "把所有公差绝对值直接相加只能得到带宽近似，封闭环中心被忽略："
            f"单边/不对称公差环 {asym_rings} 会平移封闭环中心；"
            "正确做法是按方向带符号叠加 es/ei，见 gap_min/gap_max。"),
        "interference_possible": bool(g_min < 0),
        "per_ring": per_ring,
        "dominant_key": dominant["key"] if dominant else None,
        "dominant_name": dominant["name"] if dominant else None,
    }


# --------------------------------------------------------------------------- #
# 均方根（RSS / 统计公差）—— 需要显式分布
# --------------------------------------------------------------------------- #
def _rss_moments(r: Ring) -> tuple[float, float]:
    """返回该环 *偏差* 的 (均值, 标准差)。未知分布直接拒绝。"""
    if r.zero_tolerance:
        # 零公差基准：统计法中退化为位于公称尺寸的常数
        return 0.0, 0.0
    d = r.distribution
    w = r.es - r.ei
    if d == Distribution.NORMAL:
        # 简化约定：正态中心取公差带中点，sigma 必须显式提供
        return r.mid, r.dist_params["sigma"]
    if d == Distribution.UNIFORM:
        return r.mid, w / math.sqrt(12.0)
    if d == Distribution.TRIANGULAR:
        # 三角分布，众数=中点：均值=中点，标准差 = 全宽/sqrt(24)
        return r.mid, w / math.sqrt(24.0)
    if d == Distribution.HALFNORMAL:
        scale = r.dist_params["sigma"]
        mean_dev = scale * math.sqrt(2.0 / math.pi)
        sd_dev = scale * math.sqrt(1.0 - 2.0 / math.pi)
        return mean_dev, sd_dev
    raise ToleranceError(
        f"尺寸 '{r.name}' 的分布假设为 unknown，不能进行统计/RSS 计算。"
        f"请先在数据中明确其分布（normal/uniform/triangular/halfnormal），"
        f"系统不会自动套用正态分布。极值法仍可使用。")


def rss(rings: list[Ring], k_sigma: float = 3.0) -> dict:
    """均方根法：组成环相互独立、过程受控且分布已知。"""
    nominal_gap = sum(r.direction * r.nominal for r in rings)
    mean_shift = 0.0
    per_ring = []
    variances: list[float] = []

    for r in rings:
        m, sd = _rss_moments(r)
        variances.append(sd ** 2)
        mean_shift += r.direction * m
        per_ring.append({
            "key": r.key,
            "name": r.name,
            "direction": r.direction,
            "distribution": r.distribution.value,
            "dev_mean": m,
            "dev_sd": sd,
        })

    gap_mean = nominal_gap + mean_shift
    gap_sd = math.sqrt(sum(variances))
    total_var = sum(variances)

    for item, v in zip(per_ring, variances):
        item["variance_share"] = v / total_var if total_var > 0 else 0.0
    dominant = max(per_ring, key=lambda x: x["variance_share"]) if per_ring else None

    wc = worst_case(rings)
    low = gap_mean - k_sigma * gap_sd
    high = gap_mean + k_sigma * gap_sd

    bounded = all(
        r.zero_tolerance
        or r.distribution in (Distribution.UNIFORM, Distribution.TRIANGULAR)
        for r in rings)
    return {
        "method": "rss",
        "premise": (
            "假设各组成环相互独立、过程处于统计受控状态，且每个环都有显式分布假设；"
            f"结果按 ±{k_sigma:g}σ 解释，不是保证界限。"),
        "k_sigma": k_sigma,
        "nominal": nominal_gap,
        "gap_mean": gap_mean,
        "gap_sd": gap_sd,
        "gap_low_k_sigma": low,
        "gap_high_k_sigma": high,
        "bounded_within_extremes": bounded,
        "bounded_note": (
            "所有环均为有界分布(uniform/triangular)，±kσ 区间落在极值界限内。"
            if bounded else
            "存在正态/半正态等无界分布：±kσ 区间不是硬界限，抽样可能少量超出极值范围，"
            "但这不代表极值法失效。"),
        "worst_gap_min": wc["gap_min"],
        "worst_gap_max": wc["gap_max"],
        "per_ring": per_ring,
        "dominant_key": dominant["key"] if dominant else None,
        "dominant_name": dominant["name"] if dominant else None,
    }


# --------------------------------------------------------------------------- #
# 蒙特卡洛 —— 固定种子，显式抽样
# --------------------------------------------------------------------------- #
def _sample_deviations(r: Ring, n: int, rng: np.random.Generator) -> np.ndarray:
    """按该环声明的分布抽样偏差；未知分布拒绝，零公差返回全 0。"""
    if r.zero_tolerance:
        return np.zeros(n)
    d = r.distribution
    if d == Distribution.NORMAL:
        return rng.normal(loc=r.mid, scale=r.dist_params["sigma"], size=n)
    if d == Distribution.UNIFORM:
        return rng.uniform(low=r.ei, high=r.es, size=n)
    if d == Distribution.TRIANGULAR:
        return rng.triangular(left=r.ei, mode=r.mid, right=r.es, size=n)
    if d == Distribution.HALFNORMAL:
        # |N(0, scale)|，锚定在零偏差
        return np.abs(rng.standard_normal(n)) * r.dist_params["sigma"]
    raise ToleranceError(
        f"尺寸 '{r.name}' 的分布假设为 unknown，不能进行蒙特卡洛抽样。"
        f"请先明确分布；系统不会把未知分布默认成正态。")


def monte_carlo(rings: list[Ring], n_samples: int = 100_000,
                seed: int = 20261006) -> dict:
    if n_samples <= 0:
        raise ToleranceError("蒙特卡洛样本数必须为正整数。")

    rng = np.random.default_rng(seed)
    nominal_gap = sum(r.direction * r.nominal for r in rings)
    gap = np.full(n_samples, nominal_gap, dtype=float)

    per_ring: list[dict] = []
    signed_samples: list[np.ndarray] = []
    for r in rings:
        dev = _sample_deviations(r, n_samples, rng)
        signed = r.direction * dev
        gap += signed
        signed_samples.append(signed)
        per_ring.append({
            "key": r.key,
            "name": r.name,
            "direction": r.direction,
            "distribution": r.distribution.value if not r.zero_tolerance else "degenerate_at_nominal",
            "sample_mean": float(np.mean(signed)),
            "sample_sd": float(np.std(signed, ddof=1)),
        })

    wc = worst_case(rings)
    lo, hi = wc["gap_min"], wc["gap_max"]
    span = max(hi - lo, 1e-300)
    exceed = int(np.sum((gap < lo) | (gap > hi)))

    # 主导性：用样本协方差解释封闭环方差的来源（可追溯到具体尺寸）
    gap_var = float(np.var(gap, ddof=1))
    for item, signed in zip(per_ring, signed_samples):
        item["variance_share"] = (
            float(np.cov(signed, gap, ddof=1)[0, 1]) / gap_var if gap_var > 0 else 0.0)
    dominant = max(per_ring, key=lambda x: x["variance_share"]) if per_ring else None

    p05, p50, p95 = np.percentile(gap, [5, 50, 95])
    return {
        "method": "monte_carlo",
        "premise": (
            f"按各组成环 *显式声明* 的分布独立抽样 {n_samples} 次"
            f"（numpy Generator, seed={seed}，结果可复现）。"
            "代表过程按假设运行时的频率分布，不是保证界限；分布假设错误结果就错误。"),
        "seed": seed,
        "n_samples": n_samples,
        "nominal": nominal_gap,
        "sample_mean": float(np.mean(gap)),
        "sample_sd": float(np.std(gap, ddof=1)),
        "p05": float(p05),
        "p50": float(p50),
        "p95": float(p95),
        "sample_min": float(np.min(gap)),
        "sample_max": float(np.max(gap)),
        "worst_gap_min": lo,
        "worst_gap_max": hi,
        "samples_outside_extremes": exceed,
        "outside_fraction": exceed / n_samples,
        "outside_note": (
            "有界分布抽样应全部落在解析极值内（0 超出）。"
            if exceed == 0 else
            f"有 {exceed} 个样本（{exceed / n_samples:.4%}）超出解析极值范围："
            "正态/半正态无界时这是正常现象，说明统计分布与极值法前提不同。"),
        "interference_fraction": float(np.mean(gap <= 0)),
        "per_ring": per_ring,
        "dominant_key": dominant["key"] if dominant else None,
        "dominant_name": dominant["name"] if dominant else None,
    }


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def analyze(raw_rings: list[dict], closed_unit: str,
            mc_samples: int = 100_000, seed: int = 20261006,
            k_sigma: float = 3.0,
            methods: tuple[str, ...] = ("worst_case", "rss", "monte_carlo")) -> dict:
    rings = normalize_rings(raw_rings, closed_unit)
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}

    if "worst_case" in methods:
        results["worst_case"] = worst_case(rings)
    if "rss" in methods:
        try:
            results["rss"] = rss(rings, k_sigma=k_sigma)
        except ToleranceError as e:
            errors["rss"] = str(e)
    if "monte_carlo" in methods:
        try:
            results["monte_carlo"] = monte_carlo(
                rings, n_samples=mc_samples, seed=seed)
        except ToleranceError as e:
            errors["monte_carlo"] = str(e)

    return {
        "closed_unit": closed_unit,
        "rings_used": [
            {
                "key": r.key, "name": r.name, "source": r.source,
                "direction": r.direction, "nominal": r.nominal,
                "es": r.es, "ei": r.ei,
                "one_sided": r.one_sided,
                "zero_tolerance": r.zero_tolerance,
                "distribution": r.distribution.value,
            } for r in rings
        ],
        "results": results,
        "method_errors": errors,
        "disclaimer": (
            "本计算仅用于设计阶段的公差分析与方案比较；"
            "固定种子抽样和解析结果可用于核对模型，但模型不替代制造验收、"
            "首件检验或按图纸/标准进行的合格判定。"),
    }
