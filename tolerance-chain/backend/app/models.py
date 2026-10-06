"""ORM 模型：尺寸链、组成环（含来源/方向/分布假设）、分析运行记录。"""
from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Chain(Base):
    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # 封闭环单位（方向与单位检查均基于它）
    closed_unit: Mapped[str] = mapped_column(String(16), default="mm")
    closed_name: Mapped[str] = mapped_column(String(120), default="封闭环（间隙）")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    rings: Mapped[list["RingRow"]] = relationship(
        back_populates="chain", cascade="all, delete-orphan",
        order_by="RingRow.position")
    runs: Mapped[list["RunRow"]] = relationship(
        back_populates="chain", cascade="all, delete-orphan")


class RingRow(Base):
    """组成环：保存尺寸来源、正负方向与分布假设。"""
    __tablename__ = "rings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(200), default="未注明来源")

    # 正负方向：+1 增环（使封闭环增大），-1 减环（使封闭环减小）
    direction: Mapped[int] = mapped_column(Integer)

    nominal: Mapped[float] = mapped_column(Float)
    es: Mapped[float] = mapped_column(Float)   # 上偏差
    ei: Mapped[float] = mapped_column(Float)   # 下偏差
    unit: Mapped[str] = mapped_column(String(16), default="mm")

    # 分布假设必须显式登记；unknown 表示拒绝自动假设正态
    distribution: Mapped[str] = mapped_column(String(32), default="unknown")
    dist_params: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")

    chain: Mapped[Chain] = relationship(back_populates="rings")

    __table_args__ = (
        CheckConstraint("direction IN (1, -1)", name="ck_ring_direction"),
        CheckConstraint("es >= ei", name="ck_ring_deviations"),
    )


class RunRow(Base):
    """一次分析运行（参数 + 结果），便于审计与复现。"""
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    seed: Mapped[int] = mapped_column(Integer, default=20261006)
    n_samples: Mapped[int] = mapped_column(Integer, default=100_000)
    k_sigma: Mapped[float] = mapped_column(Float, default=3.0)
    result: Mapped[dict] = mapped_column(JSON)

    chain: Mapped[Chain] = relationship(back_populates="runs")
