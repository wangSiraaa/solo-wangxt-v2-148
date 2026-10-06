"""演示数据：四个用于核对的经典场景。

1. shaft_hole_50H8f7   轴孔配合 50H8/f7（孔单边正公差，必须非对称处理）
2. thermal_growth     热膨胀影响的简化线性项 ΔL = α·L·ΔT
3. zero_datum_stack  零公差基准（基准环零公差，主导性应落到有公差的环）
4. unknown_dist      分布未知：极值法可用，RSS/蒙特卡洛必须被拒绝
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Chain, RingRow

DEMO_CHAINS = [
    {
        "code": "shaft_hole_50H8f7",
        "name": "轴孔配合 50H8/f7（装配间隙）",
        "description": (
            "封闭环 = 孔径(+1) − 轴径(−1)。孔 50H8: +0.039/0 为单边正公差，"
            "轴 50f7: −0.025/−0.050。解析极限：[0.025, 0.089] mm，"
            "永远为间隙配合。孔按半正态、轴按正态，显式给出 sigma。"),
        "closed_unit": "mm",
        "closed_name": "装配间隙",
        "rings": [
            {
                "key": "bore", "position": 0,
                "name": "孔 Φ50H8", "source": "图纸 GB/T 1800.2（镗孔工序）",
                "direction": 1, "nominal": 50.0, "es": 0.039, "ei": 0.0,
                "unit": "mm", "distribution": "halfnormal",
                "dist_params": {"sigma": 0.013},
                "note": "H 基准孔，单边正公差，禁止按 ±0.0195 对称化",
            },
            {
                "key": "shaft", "position": 1,
                "name": "轴 Φ50f7", "source": "图纸 GB/T 1800.2（外圆磨削）",
                "direction": -1, "nominal": 50.0, "es": -0.025, "ei": -0.050,
                "unit": "mm", "distribution": "normal",
                "dist_params": {"sigma": 0.0083},
                "note": "公差带整体位于零线下方",
            },
        ],
    },
    {
        "code": "thermal_growth",
        "name": "热膨胀线性项影响的同轴间隙",
        "description": (
            "常温装配间隙 0.15 mm；温升 60°C 时铝壳体孔扩张比钢轴大。"
            "热膨胀采用简化线性项 ΔL=α·L·ΔT，忽略二阶项。"
            "所有组成环三角分布。含 mm 与 µm 混合单位输入。"),
        "closed_unit": "mm",
        "closed_name": "工作温度下的径向间隙",
        "rings": [
            {
                "key": "bore_nom", "position": 0,
                "name": "常温孔 Φ80", "source": "图纸（铝壳体）",
                "direction": 1, "nominal": 80.0, "es": 0.05, "ei": 0.0,
                "unit": "mm", "distribution": "triangular", "dist_params": {},
            },
            {
                "key": "shaft_nom", "position": 1,
                "name": "常温轴 Φ80", "source": "图纸（钢轴）",
                "direction": -1, "nominal": 79.85, "es": 0.02, "ei": -0.035,
                "unit": "mm", "distribution": "triangular", "dist_params": {},
                "note": "公称已含 0.15 mm 常温设计间隙（轴公称 79.85）",
            },
            {
                "key": "bore_thermal", "position": 2,
                "name": "孔热膨胀 α_Al·L·ΔT",
                "source": "材料手册 α=23e-6 /°C，ΔT=60°C（线性项）",
                "direction": 1, "nominal": 0.1104, "es": 0.008, "ei": -0.008,
                "unit": "mm", "distribution": "triangular", "dist_params": {},
                "note": "23e-6 × 80 × 60 = 0.1104 mm",
            },
            {
                "key": "shaft_thermal", "position": 3,
                "name": "轴热膨胀 α_钢·L·ΔT",
                "source": "材料手册 α=12e-6 /°C，ΔT=60°C（线性项）",
                "direction": -1, "nominal": 57.6, "es": 15.0, "ei": -15.0,
                "unit": "um", "distribution": "triangular", "dist_params": {},
                "note": "12e-6 × 80 × 60 = 0.0576 mm = 57.6 µm；偏差以 µm 登记，换算后使用",
            },
        ],
    },
    {
        "code": "zero_datum_stack",
        "name": "零公差基准叠加案例",
        "description": (
            "一个基准块按零公差制造（理想基准），间隙变化只能来自另外两个件。"
            "极值结果与该基准环无关；主导性分析中基准环份额为 0。"),
        "closed_unit": "mm",
        "closed_name": "端面间隙",
        "rings": [
            {
                "key": "housing", "position": 0,
                "name": "壳体腔深 40", "source": "图纸（机加工）",
                "direction": 1, "nominal": 40.0, "es": 0.10, "ei": 0.0,
                "unit": "mm", "distribution": "uniform", "dist_params": {},
            },
            {
                "key": "spacer", "position": 1,
                "name": "基准隔块 15（零公差）", "source": "检定基准（按标称使用）",
                "direction": -1, "nominal": 15.0, "es": 0.0, "ei": 0.0,
                "unit": "mm", "distribution": "unknown", "dist_params": {},
                "note": "零公差基准，统计法对其退化为常数，不需要分布",
            },
            {
                "key": "shaft_step", "position": 2,
                "name": "轴台阶段 25", "source": "图纸（磨削）",
                "direction": -1, "nominal": 25.0, "es": 0.0, "ei": -0.05,
                "unit": "mm", "distribution": "uniform", "dist_params": {},
            },
        ],
    },
    {
        "code": "unknown_dist",
        "name": "分布假设未知的冲压件",
        "description": (
            "供应商未提供过程数据，分布保持 unknown。极值法照常给出保证界限；"
            "RSS 与蒙特卡洛必须明确报错，系统不得自动套用正态。"),
        "closed_unit": "mm",
        "closed_name": "卡扣间隙",
        "rings": [
            {
                "key": "slot", "position": 0,
                "name": "卡槽宽 10", "source": "供应商图纸（无过程能力数据）",
                "direction": 1, "nominal": 10.0, "es": 0.10, "ei": 0.0,
                "unit": "mm", "distribution": "unknown", "dist_params": {},
            },
            {
                "key": "tab", "position": 1,
                "name": "卡扣厚 9.6", "source": "供应商图纸（无过程能力数据）",
                "direction": -1, "nominal": 9.6, "es": 0.05, "ei": -0.05,
                "unit": "mm", "distribution": "unknown", "dist_params": {},
            },
        ],
    },
]


def seed_demo_data(db: Session) -> int:
    """幂等写入演示数据，返回写入条数。"""
    created = 0
    for spec in DEMO_CHAINS:
        existing = db.scalar(select(Chain).where(Chain.code == spec["code"]))
        if existing:
            continue
        chain = Chain(
            code=spec["code"], name=spec["name"],
            description=spec["description"],
            closed_unit=spec["closed_unit"], closed_name=spec["closed_name"])
        chain.rings = [RingRow(**r) for r in spec["rings"]]
        db.add(chain)
        created += 1
    db.commit()
    return created
