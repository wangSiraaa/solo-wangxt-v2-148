"""辅助计算：热膨胀简化线性项。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import tolerance
from ..schemas import ThermalTermRequest

router = APIRouter(prefix="/api/utils", tags=["utils"])


@router.post("/thermal-expansion-term")
def thermal_term(payload: ThermalTermRequest) -> dict:
    """由 α/L/ΔT 生成可直接加入尺寸链的组成环。

    注意：这只是 ΔL=α·L·ΔT 的一阶线性近似，忽略温度梯度、装配约束与
    材料非线性；温度区间未知时 uncertainty_kind 不可被静默替换为正态。
    """
    try:
        term = tolerance.thermal_expansion_term(
            alpha_per_c=payload.alpha_per_c,
            length_mm=payload.length_mm,
            delta_t_c=payload.delta_t_c,
            delta_t_lower_c=payload.delta_t_lower_c,
            delta_t_upper_c=payload.delta_t_upper_c,
            uncertainty_kind=payload.uncertainty_kind,
            name=payload.name,
        )
    except tolerance.ToleranceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    term["linear_model_note"] = (
        "ΔL = α·L·ΔT 一阶近似；不含约束应力、温度梯度与材料温度依赖。"
        "温度分布登记为 unknown 时仅极值法可用，统计法会被阻断。"
    )
    return term
