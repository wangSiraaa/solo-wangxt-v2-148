"""演示案例种子数据：
1. 轴孔配合 φ50 H7/g6（解析极值可手算核对）
2. 热膨胀影响的简化线性项（含单边温度区间）
3. 零公差基准（确定性基准环不贡献带宽）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _chains_payload() -> list[dict]:
    return [
        # ---------- 案例 1：轴孔配合 ----------
        {
            "name": "轴孔配合 φ50 H7/g6（间隙配合）",
            "description": (
                "封闭环 G = D_孔 - d_轴。孔 φ50H7(+0.025/0)，轴 φ50g6(-0.009/-0.025)，"
                "单位均为 mm。解析极值：最小间隙 0.009，最大间隙 0.050。"
                "分布假设为教学示例（公差带中点为均值、带宽=±3σ），不是默认结论。"
            ),
            "base_unit": "mm",
            "closing_name": "装配间隙 G",
            "closing_positive_direction": "G = 孔径 − 轴径；G>0 为间隙，G<0 为过盈",
            "expected_closing_nominal": 0.0,
            "acceptance_lower": 0.009,
            "acceptance_upper": 0.050,
            "dimensions": [
                {
                    "name": "孔 φ50H7",
                    "nominal": 50.0, "lower_deviation": 0.0, "upper_deviation": 0.025,
                    "dimension_unit": "mm", "direction": 1,
                    "source": "design",
                    "source_detail": "φ50 H7：EI=0, ES=+25 µm",
                    "distribution_kind": "normal",
                    "distribution_params": {"sigma_side": 3, "basis": "教学假设：均值取偏差带中点，±3σ 覆盖公差带"},
                },
                {
                    "name": "轴 φ50g6",
                    "nominal": 50.0, "lower_deviation": -0.025, "upper_deviation": -0.009,
                    "dimension_unit": "mm", "direction": -1,
                    "source": "design",
                    "source_detail": "φ50 g6：es=−9 µm, ei=−25 µm",
                    "distribution_kind": "normal",
                    "distribution_params": {"sigma_side": 3, "basis": "教学假设：均值取偏差带中点，±3σ 覆盖公差带"},
                },
            ],
        },
        # ---------- 案例 2：热膨胀线性项（单边温升区间） ----------
        {
            "name": "导轨间隙受热膨胀影响（简化线性项，单边温升）",
            "description": (
                "冷态装配间隙 0.50 +0.04/−0.02 mm；钢件 L=500 mm、α=12e-6/°C，"
                "名义温升 40°C，实际温升只在 40~50°C（单边 +10°C 不确定，均匀分布）。"
                "热项名义收缩 αLΔT=0.24 mm，偏差 [0, 0.06] mm 为单边，"
                "不得按 ±0.03 对称处理。"
            ),
            "base_unit": "mm",
            "closing_name": "热态间隙 G_hot",
            "closing_positive_direction": "G_hot = 冷态间隙 − 热膨胀量；正值为间隙",
            "expected_closing_nominal": 0.26,
            "acceptance_lower": 0.0,
            "acceptance_upper": None,
            "dimensions": [
                {
                    "name": "冷态装配间隙",
                    "nominal": 0.50, "lower_deviation": -0.02, "upper_deviation": 0.04,
                    "dimension_unit": "mm", "direction": 1,
                    "source": "measured",
                    "source_detail": "装配后实测分布，示例按均匀分布登记",
                    "distribution_kind": "uniform",
                    "distribution_params": {},
                },
                {
                    "name": "热膨胀线性项 αLΔT",
                    "nominal": 0.24, "lower_deviation": 0.0, "upper_deviation": 0.06,
                    "dimension_unit": "mm", "direction": -1,
                    "source": "thermal_expansion",
                    "source_detail": "α=12e-6/°C, L=500 mm, ΔT=40°C 且 ΔT∈[40,50]°C（单边）",
                    "distribution_kind": "uniform",
                    "distribution_params": {
                        "alpha": 12e-6, "length_mm": 500.0,
                        "delta_t_c": 40.0, "delta_t_uncertainty_c": [0.0, 10.0],
                    },
                },
            ],
        },
        # ---------- 案例 3：零公差基准 ----------
        {
            "name": "台阶定位尺寸链（零公差基准）",
            "description": (
                "封闭环 G = 基准 B0 − L1 − L2。B0=60 mm 为零公差基准（确定性），"
                "不贡献公差带宽；L1=30 ±0.03、L2=30 ±0.05 均为均匀分布。"
                "解析极值 G ∈ [−0.08, +0.08]，带宽 0.16，零公差环贡献为 0。"
            ),
            "base_unit": "mm",
            "closing_name": "台阶末端间隙 G",
            "closing_positive_direction": "G = B0 − L1 − L2；正为间隙、负为干涉",
            "expected_closing_nominal": 0.0,
            "dimensions": [
                {
                    "name": "基准尺寸 B0（零公差）",
                    "nominal": 60.0, "lower_deviation": 0.0, "upper_deviation": 0.0,
                    "dimension_unit": "mm", "direction": 1,
                    "source": "datum",
                    "source_detail": "零公差基准（量块/对刀基准），按确定性常数",
                    "distribution_kind": "deterministic",
                    "distribution_params": {},
                },
                {
                    "name": "台阶长度 L1",
                    "nominal": 30.0, "lower_deviation": -0.03, "upper_deviation": 0.03,
                    "dimension_unit": "mm", "direction": -1,
                    "source": "design",
                    "distribution_kind": "uniform",
                    "distribution_params": {},
                },
                {
                    "name": "台阶长度 L2",
                    "nominal": 30.0, "lower_deviation": -0.05, "upper_deviation": 0.05,
                    "dimension_unit": "mm", "direction": -1,
                    "source": "design",
                    "distribution_kind": "uniform",
                    "distribution_params": {},
                },
            ],
        },
    ]


@router.post("/seed", status_code=201)
def seed_demo(db: Session = Depends(get_db)) -> dict:
    """（重新）写入三个演示案例。已存在同名案例会先删除。"""
    created = []
    for payload in _chains_payload():
        existing = db.scalar(
            select(models.DimensionChain).where(models.DimensionChain.name == payload["name"])
        )
        if existing is not None:
            db.delete(existing)
            db.flush()

        chain = models.DimensionChain(
            name=payload["name"],
            description=payload["description"],
            base_unit=payload["base_unit"],
            closing_name=payload["closing_name"],
            closing_positive_direction=payload["closing_positive_direction"],
            expected_closing_nominal=payload.get("expected_closing_nominal"),
            acceptance_lower=payload.get("acceptance_lower"),
            acceptance_upper=payload.get("acceptance_upper"),
        )
        for i, d in enumerate(payload["dimensions"]):
            chain.dimensions.append(
                models.Dimension(
                    position=i,
                    name=d["name"],
                    nominal=d["nominal"],
                    lower_deviation=d["lower_deviation"],
                    upper_deviation=d["upper_deviation"],
                    dimension_unit=d["dimension_unit"],
                    direction=d["direction"],
                    source=models.DimensionSource(d["source"]),
                    source_detail=d.get("source_detail"),
                    distribution_kind=models.DistributionKind(d["distribution_kind"]),
                    distribution_params=d.get("distribution_params", {}),
                )
            )
        db.add(chain)
        db.flush()
        created.append({"id": chain.id, "name": chain.name})
    db.commit()
    return {"created": created}
