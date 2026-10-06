"""请求/响应模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import DimensionSource, DistributionKind


class DimensionBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    nominal: float
    lower_deviation: float = 0.0
    upper_deviation: float = 0.0
    dimension_unit: str = "mm"
    direction: Literal[1, -1] = 1
    source: DimensionSource = DimensionSource.DESIGN
    source_detail: str | None = None
    distribution_kind: DistributionKind = DistributionKind.UNKNOWN
    distribution_params: dict = Field(default_factory=dict)
    position: int = 0

    @model_validator(mode="after")
    def _check_band(self) -> "DimensionBase":
        if self.upper_deviation < self.lower_deviation:
            raise ValueError(
                f"组成环 '{self.name}' 上偏差 {self.upper_deviation} 小于"
                f"下偏差 {self.lower_deviation}，公差带非法。"
            )
        if self.distribution_kind == DistributionKind.DETERMINISTIC and not (
            self.lower_deviation == self.upper_deviation == 0
        ):
            raise ValueError(f"确定性环 '{self.name}' 必须为零公差（上下偏差均为 0）。")
        return self

    @field_validator("dimension_unit")
    @classmethod
    def _unit(cls, v: str) -> str:
        from .tolerance import UNIT_TO_MM

        if v.lower() not in UNIT_TO_MM:
            raise ValueError(f"不支持的单位 '{v}'，支持 mm / um / inch")
        return v


class DimensionCreate(DimensionBase):
    pass


class DimensionOut(DimensionBase):
    id: int
    chain_id: int


class ChainBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    base_unit: str = "mm"
    closing_name: str = Field(min_length=1, max_length=200)
    closing_positive_direction: str = Field(min_length=1, max_length=400)
    expected_closing_nominal: float | None = None
    acceptance_lower: float | None = None
    acceptance_upper: float | None = None

    @model_validator(mode="after")
    def _acceptance(self) -> "ChainBase":
        if (
            self.acceptance_lower is not None
            and self.acceptance_upper is not None
            and self.acceptance_upper < self.acceptance_lower
        ):
            raise ValueError("验收区间上界小于下界。")
        return self


class ChainCreate(ChainBase):
    dimensions: list[DimensionCreate] = Field(default_factory=list)


class ChainOut(ChainBase):
    id: int
    dimensions: list[DimensionOut] = Field(default_factory=list)


class CalculateRequest(BaseModel):
    n_samples: int | None = Field(default=None, ge=1, le=10_000_000)
    # seed 可显式传入用于教学/复现；默认使用服务端固定种子
    seed: int | None = None


class ThermalTermRequest(BaseModel):
    alpha_per_c: float = Field(..., description="线膨胀系数，单位 1/°C，如 钢 1.2e-5")
    length_mm: float = Field(..., gt=0)
    delta_t_c: float = Field(..., description="名义温升（相对基准温度），可负")
    delta_t_lower_c: float | None = Field(default=None, description="温度不确定下界（增量），单边填 0")
    delta_t_upper_c: float | None = Field(default=None, description="温度不确定上界（增量）")
    uncertainty_kind: Literal["uniform", "triangular", "unknown"] = "uniform"
    name: str = "热膨胀线性项 ΔL=α·L·ΔT"
