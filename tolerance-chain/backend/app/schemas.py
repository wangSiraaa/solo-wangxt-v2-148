"""请求/响应模型。"""
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RingIn(BaseModel):
    key: str = Field(..., description="组成环稳定标识，链内唯一")
    name: str
    source: str = "未注明来源"
    direction: Literal[1, -1] = Field(..., description="+1 增环，-1 减环")
    nominal: float = Field(..., description="公称尺寸（按 unit）")
    es: float = Field(..., description="上偏差（按 unit）")
    ei: float = Field(..., description="下偏差（按 unit）")
    unit: str = "mm"
    distribution: Literal["unknown", "normal", "uniform", "triangular", "halfnormal"] = "unknown"
    dist_params: dict[str, float] = Field(
        default_factory=dict,
        description="分布参数：normal/halfnormal 需 sigma；均为 ring 自身单位")
    note: str = ""

    @field_validator("es", "ei")
    @classmethod
    def _dev_order(cls, v: float) -> float:
        return v

    def validate_pair(self) -> "RingIn":
        if self.es < self.ei:
            raise ValueError(f"尺寸 {self.name}：上偏差 es 不能小于下偏差 ei")
        if self.distribution in ("normal", "halfnormal"):
            sig = self.dist_params.get("sigma")
            if sig is None or sig <= 0:
                raise ValueError(
                    f"尺寸 {self.name}：{self.distribution} 必须显式给出正的 sigma")
        if self.distribution == "halfnormal":
            tol = max(abs(self.es), abs(self.ei))
            if not (abs(self.ei) <= 1e-12 * max(1.0, tol) and self.es > 0):
                raise ValueError(
                    f"尺寸 {self.name}：halfnormal 仅支持 [0, T] 形式的单边正公差，"
                    "单边公差不能按对称范围处理")
        return self


class ChainIn(BaseModel):
    code: str
    name: str
    description: str = ""
    closed_unit: str = "mm"
    closed_name: str = "封闭环（间隙）"
    rings: list[RingIn] = Field(..., min_length=1)


class ChainOut(BaseModel):
    id: int
    code: str
    name: str
    description: str
    closed_unit: str
    closed_name: str
    rings: list[dict[str, Any]]


class AnalyzeIn(BaseModel):
    seed: int = 20261006
    n_samples: int = Field(100_000, ge=1, le=5_000_000)
    k_sigma: float = Field(3.0, gt=0, le=10)
    methods: list[Literal["worst_case", "rss", "monte_carlo"]] = Field(
        default_factory=lambda: ["worst_case", "rss", "monte_carlo"])


class RunOut(BaseModel):
    id: int
    chain_id: int
    seed: int
    n_samples: int
    k_sigma: float
    result: dict[str, Any]
