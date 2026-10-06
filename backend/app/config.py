"""应用配置。

生产/部署默认使用 PostgreSQL；本地没有数据库时可用 SQLite 做集成测试，
但 JSONB 等 PG 专有能力在 SQLite 下退化为普通 JSON，详见 README。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TC_", extra="ignore")

    # 例如 postgresql+psycopg2://user:pass@localhost:5432/tolchain
    database_url: str = "postgresql+psycopg2://tolchain:tolchain@localhost:5432/tolchain"

    # 蒙特卡洛默认抽样数与固定种子（种子不随请求变化，保证结果可复现）
    default_n_samples: int = 100_000
    fixed_seed: int = 20260601

    # RSS 报告“统计区间”所用的标准差倍数（正态 ±3σ ≈ 99.73%）
    rss_k_sigma: float = 3.0

    cors_origins: list[str] = ["http://localhost:4200"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
