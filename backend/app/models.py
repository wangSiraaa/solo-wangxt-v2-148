"""ORM 模型：尺寸链、组成环、计算记录。

建模要点
- 每个组成环保存自身单位 (mm/µm/inch)，计算时统一换算到尺寸链基准单位，
  避免不同单位被直接相加。
- direction = +1 / -1 表示该环在封闭环方程中的符号方向。
- distribution_kind + distribution_params 保存分布假设；“未知”是显式状态，
  绝不由后端静默改成正态。
- 单边公差 (lower_deviation / upper_deviation 之一为 0) 如实保存非对称区间，
  计算层按非对称分布处理，不会折叠成 ±T/2 对称范围。
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import JSONType, Base


class DistributionKind(str, enum.Enum):
    NORMAL = "normal"          # 正态（截断在允许偏差内，默认 ±3σ）
    UNIFORM = "uniform"        # 均匀分布
    TRIANGULAR = "triangular"  # 三角分布
    DETERMINISTIC = "deterministic"  # 零公差基准，确定性常数
    UNKNOWN = "unknown"        # 未知分布：不做统计假设


class DimensionSource(str, enum.Enum):
    DESIGN = "design"                    # 图纸/设计名义值
    MEASURED = "measured"                # 实测统计来源
    THERMAL_EXPANSION = "thermal_expansion"  # 热膨胀简化线性项
    DATUM = "datum"                      # 零公差基准
    OTHER = "other"


class DimensionChain(Base):
    __tablename__ = "dimension_chains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 尺寸链内部统一使用的基准单位（长度），如 "mm"
    base_unit: Mapped[str] = mapped_column(String(16), nullable=False, default="mm")

    # 封闭环（被决定尺寸）的信息
    closing_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 封闭环工程定义的正方向，例如 "孔尺寸方向为正"
    closing_positive_direction: Mapped[str] = mapped_column(String(400), nullable=False)
    # 设计给定的封闭环目标名义值（可选），用于方向/名义值核对
    expected_closing_nominal: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 判定：封闭环“合格间隙/过盈”方向上的允许区间（基准单位），可选
    acceptance_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    acceptance_upper: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    dimensions: Mapped[list["Dimension"]] = relationship(
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="Dimension.position",
    )
    runs: Mapped[list["CalculationRun"]] = relationship(
        back_populates="chain", cascade="all, delete-orphan"
    )


class Dimension(Base):
    __tablename__ = "dimensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_chains.id", ondelete="CASCADE"), index=True
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # 名义尺寸与双向偏差，均使用 dimension_unit 记录的单位
    nominal: Mapped[float] = mapped_column(Float, nullable=False)
    lower_deviation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    upper_deviation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dimension_unit: Mapped[str] = mapped_column(String(16), nullable=False, default="mm")

    # 在封闭环方程中的方向：+1 增环，-1 减环
    direction: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    source: Mapped[DimensionSource] = mapped_column(
        Enum(DimensionSource, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DimensionSource.DESIGN,
    )
    source_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    distribution_kind: Mapped[DistributionKind] = mapped_column(
        Enum(DistributionKind, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DistributionKind.UNKNOWN,
    )
    # 例：{"sigma_side": 3}（公差带半宽对应 ±kσ）、
    # 热膨胀项 {"alpha":..., "length":..., "delta_t":..., "uncertainty_direction":...}
    distribution_params: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    chain: Mapped[DimensionChain] = relationship(back_populates="dimensions")


class CalculationRun(Base):
    """每次统计/极值计算的留痕，支撑“追到哪个尺寸主导结果”。"""

    __tablename__ = "calculation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_chains.id", ondelete="CASCADE"), index=True
    )

    method: Mapped[str] = mapped_column(String(40), nullable=False)  # worst_case/rss/monte_carlo
    n_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    result: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    chain: Mapped[DimensionChain] = relationship(back_populates="runs")
