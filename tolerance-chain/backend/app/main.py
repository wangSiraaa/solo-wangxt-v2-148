"""FastAPI 入口：尺寸链 CRUD、三种分析方法、演示数据。"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tolerance
from .database import Base, engine, get_db
from .models import Chain, RingRow, RunRow
from .schemas import AnalyzeIn, ChainIn, ChainOut, RingIn, RunOut
from .seed import seed_demo_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_demo_data(db)
    yield


app = FastAPI(
    title="尺寸公差链分析 API",
    version="1.0.0",
    description="比较装配间隙的最坏情况（极值法）、均方根与蒙特卡洛分布。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _ring_to_dict(r: RingRow) -> dict:
    return {
        "id": r.id, "key": r.key, "name": r.name, "source": r.source,
        "direction": r.direction, "nominal": r.nominal,
        "es": r.es, "ei": r.ei, "unit": r.unit,
        "distribution": r.distribution, "dist_params": r.dist_params or {},
        "note": r.note, "position": r.position,
    }


def _chain_to_out(c: Chain) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name,
        "description": c.description,
        "closed_unit": c.closed_unit, "closed_name": c.closed_name,
        "rings": [_ring_to_dict(r) for r in c.rings],
    }


def _get_chain(db: Session, chain_id: int) -> Chain:
    chain = db.get(Chain, chain_id)
    if chain is None:
        raise HTTPException(404, f"尺寸链 id={chain_id} 不存在")
    return chain


# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/chains", response_model=list[ChainOut])
def list_chains(db: Session = Depends(get_db)):
    return [_chain_to_out(c) for c in db.scalars(select(Chain).order_by(Chain.id))]


@app.post("/api/chains", response_model=ChainOut, status_code=201)
def create_chain(payload: ChainIn, db: Session = Depends(get_db)):
    if db.scalar(select(Chain).where(Chain.code == payload.code)):
        raise HTTPException(409, f"编号 {payload.code} 已存在")
    for r in payload.rings:
        try:
            r.validate_pair()
        except ValueError as e:
            raise HTTPException(422, str(e))

    chain = Chain(
        code=payload.code, name=payload.name, description=payload.description,
        closed_unit=payload.closed_unit, closed_name=payload.closed_name)
    chain.rings = [
        RingRow(
            position=i, key=r.key, name=r.name, source=r.source,
            direction=r.direction, nominal=r.nominal, es=r.es, ei=r.ei,
            unit=r.unit, distribution=r.distribution,
            dist_params=r.dist_params, note=r.note)
        for i, r in enumerate(payload.rings)]
    db.add(chain)
    db.commit()
    db.refresh(chain)
    return _chain_to_out(chain)


@app.get("/api/chains/{chain_id}", response_model=ChainOut)
def get_chain(chain_id: int, db: Session = Depends(get_db)):
    return _chain_to_out(_get_chain(db, chain_id))


@app.post("/api/chains/{chain_id}/analyze", response_model=RunOut)
def analyze_chain(chain_id: int, payload: AnalyzeIn | None = None,
                  db: Session = Depends(get_db)):
    payload = payload or AnalyzeIn()
    chain = _get_chain(db, chain_id)
    raw_rings = [_ring_to_dict(r) for r in chain.rings]

    try:
        result = tolerance.analyze(
            raw_rings, closed_unit=chain.closed_unit,
            mc_samples=payload.n_samples, seed=payload.seed,
            k_sigma=payload.k_sigma, methods=tuple(payload.methods))
    except tolerance.ToleranceError as e:
        # 方向/单位/闭合性/形态错误 —— 明确拒绝，不静默给数
        raise HTTPException(422, str(e))

    run = RunRow(chain_id=chain.id, seed=payload.seed,
                 n_samples=payload.n_samples, k_sigma=payload.k_sigma,
                 result=result)
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "chain_id": chain.id, "seed": run.seed,
            "n_samples": run.n_samples, "k_sigma": run.k_sigma,
            "result": run.result}


@app.get("/api/chains/{chain_id}/runs", response_model=list[RunOut])
def list_runs(chain_id: int, db: Session = Depends(get_db)):
    _get_chain(db, chain_id)
    rows = db.scalars(
        select(RunRow).where(RunRow.chain_id == chain_id)
        .order_by(RunRow.id.desc())).all()
    return [{"id": r.id, "chain_id": r.chain_id, "seed": r.seed,
             "n_samples": r.n_samples, "k_sigma": r.k_sigma,
             "result": r.result} for r in rows]


@app.post("/api/analyze-direct")
def analyze_direct(payload: dict, db: Session = Depends(get_db)):
    """不落库的即时计算，供界面临时试算。载荷：{closed_unit, rings, ...}。"""
    try:
        return tolerance.analyze(
            payload.get("rings", []),
            closed_unit=payload.get("closed_unit", "mm"),
            mc_samples=int(payload.get("n_samples", 100_000)),
            seed=int(payload.get("seed", 20261006)),
            k_sigma=float(payload.get("k_sigma", 3.0)))
    except tolerance.ToleranceError as e:
        raise HTTPException(422, str(e))
