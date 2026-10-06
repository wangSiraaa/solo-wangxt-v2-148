"""FastAPI 入口。

启动: uvicorn app.main:app --reload
本地无 PostgreSQL 时: TC_DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .routers import chains, demo, utils

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="尺寸公差链分析 API",
    version="1.0.0",
    description=(
        "比较装配间隙的最坏极值、均方根与蒙特卡洛结果。"
        "未知分布不自动设正态，单边公差不做对称化；结果用于设计比较，"
        "不替代制造验收。"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chains.router)
app.include_router(utils.router)
app.include_router(demo.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "default_n_samples": settings.default_n_samples, "fixed_seed": settings.fixed_seed}
