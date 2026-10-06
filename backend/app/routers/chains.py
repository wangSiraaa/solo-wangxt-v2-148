"""尺寸链 CRUD 与计算路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, tolerance
from ..config import get_settings
from ..database import get_db
from ..schemas import ChainCreate, ChainOut, DimensionCreate, DimensionOut, CalculateRequest

router = APIRouter(prefix="/api/chains", tags=["chains"])
settings = get_settings()


def _dim_to_dict(d: models.Dimension) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "nominal": d.nominal,
        "lower_deviation": d.lower_deviation,
        "upper_deviation": d.upper_deviation,
        "dimension_unit": d.dimension_unit,
        "direction": d.direction,
        "source": d.source.value if isinstance(d.source, models.DimensionSource) else d.source,
        "source_detail": d.source_detail,
        "distribution_kind": (
            d.distribution_kind.value
            if isinstance(d.distribution_kind, models.DistributionKind)
            else d.distribution_kind
        ),
        "distribution_params": d.distribution_params or {},
        "position": d.position,
    }


def _get_chain_or_404(db: Session, chain_id: int) -> models.DimensionChain:
    chain = db.scalar(
        select(models.DimensionChain)
        .where(models.DimensionChain.id == chain_id)
        .options(selectinload(models.DimensionChain.dimensions))
    )
    if chain is None:
        raise HTTPException(status_code=404, detail=f"尺寸链 {chain_id} 不存在")
    return chain


@router.get("", response_model=list[ChainOut])
def list_chains(db: Session = Depends(get_db)) -> list[models.DimensionChain]:
    return list(db.scalars(
        select(models.DimensionChain)
        .options(selectinload(models.DimensionChain.dimensions))
        .order_by(models.DimensionChain.id)
    ))


@router.post("", response_model=ChainOut, status_code=201)
def create_chain(payload: ChainCreate, db: Session = Depends(get_db)) -> models.DimensionChain:
    chain = models.DimensionChain(
        name=payload.name,
        description=payload.description,
        base_unit=payload.base_unit,
        closing_name=payload.closing_name,
        closing_positive_direction=payload.closing_positive_direction,
        expected_closing_nominal=payload.expected_closing_nominal,
        acceptance_lower=payload.acceptance_lower,
        acceptance_upper=payload.acceptance_upper,
    )
    for i, d in enumerate(payload.dimensions):
        chain.dimensions.append(
            models.Dimension(
                position=d.position or i,
                name=d.name,
                nominal=d.nominal,
                lower_deviation=d.lower_deviation,
                upper_deviation=d.upper_deviation,
                dimension_unit=d.dimension_unit,
                direction=d.direction,
                source=d.source,
                source_detail=d.source_detail,
                distribution_kind=d.distribution_kind,
                distribution_params=d.distribution_params,
            )
        )
    db.add(chain)
    db.commit()
    db.refresh(chain)
    return _get_chain_or_404(db, chain.id)


@router.get("/{chain_id}", response_model=ChainOut)
def get_chain(chain_id: int, db: Session = Depends(get_db)) -> models.DimensionChain:
    return _get_chain_or_404(db, chain_id)


@router.delete("/{chain_id}", status_code=204)
def delete_chain(chain_id: int, db: Session = Depends(get_db)) -> None:
    chain = _get_chain_or_404(db, chain_id)
    db.delete(chain)
    db.commit()


@router.post("/{chain_id}/dimensions", response_model=DimensionOut, status_code=201)
def add_dimension(
    chain_id: int, payload: DimensionCreate, db: Session = Depends(get_db)
) -> models.Dimension:
    chain = _get_chain_or_404(db, chain_id)
    dim = models.Dimension(
        chain_id=chain.id,
        position=payload.position or len(chain.dimensions),
        name=payload.name,
        nominal=payload.nominal,
        lower_deviation=payload.lower_deviation,
        upper_deviation=payload.upper_deviation,
        dimension_unit=payload.dimension_unit,
        direction=payload.direction,
        source=payload.source,
        source_detail=payload.source_detail,
        distribution_kind=payload.distribution_kind,
        distribution_params=payload.distribution_params,
    )
    db.add(dim)
    db.commit()
    db.refresh(dim)
    return dim


@router.delete("/dimensions/{dimension_id}", status_code=204)
def delete_dimension(dimension_id: int, db: Session = Depends(get_db)) -> None:
    dim = db.get(models.Dimension, dimension_id)
    if dim is None:
        raise HTTPException(status_code=404, detail="组成环不存在")
    db.delete(dim)
    db.commit()


@router.post("/{chain_id}/analyze")
def analyze_chain(
    chain_id: int, payload: CalculateRequest, db: Session = Depends(get_db)
) -> dict:
    chain = _get_chain_or_404(db, chain_id)
    dims = [_dim_to_dict(d) for d in sorted(chain.dimensions, key=lambda x: x.position)]
    n = payload.n_samples or settings.default_n_samples
    seed = payload.seed if payload.seed is not None else settings.fixed_seed

    try:
        result = tolerance.analyze(
            dims,
            n_samples=n,
            seed=seed,
            k_sigma=settings.rss_k_sigma,
            expected_closing_nominal=chain.expected_closing_nominal,
            acceptance=(chain.acceptance_lower, chain.acceptance_upper),
            base_unit=chain.base_unit,
        )
    except tolerance.ToleranceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result["chain"] = {
        "id": chain.id,
        "name": chain.name,
        "closing_name": chain.closing_name,
        "closing_positive_direction": chain.closing_positive_direction,
        "base_unit": chain.base_unit,
    }

    # 留痕：三种方法各写一条，便于追溯“哪个尺寸主导”
    for method, key, n_used in (
        ("worst_case", "worst_case", None),
        ("rss", "rss", None),
        ("monte_carlo", "monte_carlo", n),
    ):
        if result.get(key):
            db.add(
                models.CalculationRun(
                    chain_id=chain.id,
                    method=method,
                    n_samples=n_used,
                    seed=seed if method == "monte_carlo" else None,
                    result=result[key],
                )
            )
    db.commit()
    return result


@router.get("/{chain_id}/runs")
def list_runs(chain_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _get_chain_or_404(db, chain_id)
    rows = db.scalars(
        select(models.CalculationRun)
        .where(models.CalculationRun.chain_id == chain_id)
        .order_by(models.CalculationRun.id.desc())
        .limit(50)
    )
    return [
        {
            "id": r.id,
            "method": r.method,
            "n_samples": r.n_samples,
            "seed": r.seed,
            "created_at": r.created_at.isoformat(),
            "result_excerpt": {
                k: r.result.get(k)
                for k in (
                    "minimum_mm", "maximum_mm", "mean_mm", "std_mm",
                    "p1_mm", "p99_mm", "sample_min_mm", "sample_max_mm",
                    "tolerance_span_mm",
                )
                if isinstance(r.result, dict) and k in r.result
            },
        }
        for r in rows
    ]
