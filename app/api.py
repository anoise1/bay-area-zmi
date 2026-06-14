"""Bay Area ZMI — REST API (course pilot requirement).

Run:  /opt/anaconda3/bin/uvicorn app.api:app --reload --port 8000   (from repo root)
Docs: http://localhost:8000/docs

Endpoints
  GET  /jurisdictions?county=&min_zmi=&max_zmi=&sort=&order=&limit=&offset=
  GET  /jurisdictions/{name}
  GET  /scenarios
  POST /scenarios        <- creates a new instance: a rezoning what-if, recomputes the index
"""
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app import core

app = FastAPI(
    title="Bay Area Zoning Mismatch Index API",
    description="109 Bay Area jurisdictions: demand vs zoning capacity vs delivery "
                "(DSBA 2025/26 project).",
    version="1.0",
)
DF = core.load_master()
assert core.verify_consistency(DF), "stored zmi_core does not match pillar definition"


def _clean(obj):
    """JSON-safe: NaN -> None, numpy -> python, floats rounded."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer, int)) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 3)
    return obj


def _find(name: str) -> pd.Series:
    hit = DF[DF["jurisdiction"].str.lower() == name.lower()]
    if hit.empty:
        hit = DF[DF["jurisdiction"].str.lower().str.contains(name.lower())]
    if hit.empty:
        raise HTTPException(404, f"jurisdiction '{name}' not found")
    if len(hit) > 1:
        raise HTTPException(409, f"ambiguous name; matches: {hit['jurisdiction'].tolist()}")
    return hit.iloc[0]


@app.get("/jurisdictions")
def list_jurisdictions(
    county: Optional[str] = Query(None, description="filter: county name, e.g. 'Santa Clara'"),
    min_zmi: Optional[float] = Query(None, description="filter: zmi_core >= value"),
    max_zmi: Optional[float] = Query(None, description="filter: zmi_core <= value"),
    sort: str = Query("zmi_core", description=f"one of {core.PUBLIC_COLS}"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(25, ge=1, le=109),
    offset: int = Query(0, ge=0),
):
    d = DF
    if county:
        d = d[d["county"].str.lower() == county.lower()]
        if d.empty:
            raise HTTPException(404, f"no jurisdictions in county '{county}'")
    if min_zmi is not None:
        d = d[d["zmi_core"] >= min_zmi]
    if max_zmi is not None:
        d = d[d["zmi_core"] <= max_zmi]
    if sort not in core.PUBLIC_COLS:
        raise HTTPException(422, f"sort must be one of {core.PUBLIC_COLS}")
    d = d.sort_values(sort, ascending=(order == "asc"), na_position="last")
    page = d[core.PUBLIC_COLS].iloc[offset:offset + limit]
    return {"total": int(len(d)), "offset": offset, "limit": limit,
            "items": _clean(page.to_dict(orient="records"))}


@app.get("/jurisdictions/{name}")
def get_jurisdiction(name: str):
    row = _find(name)
    out = _clean(row[core.PUBLIC_COLS].to_dict())
    out["decomposition"] = _clean({
        "D_demand": round(float(row["D_demand"]), 3),
        "C_capacity": round(float(row["C_capacity"]), 3),
        "F_friction": (round(float(row["F_friction"]), 3)
                       if pd.notna(row["F_friction"]) else None),
        "P_delivery": round(float(row["P_delivery"]), 3),
    })
    out["prescription"] = row["prescription"]
    out["rank_of_109_by_zmi"] = int(DF["zmi_core"].rank(ascending=False)[row.name])
    return out


class ScenarioIn(BaseModel):
    """A rezoning what-if for one jurisdiction."""
    jurisdiction: str = Field(examples=["Palo Alto"])
    add_capacity_per_1k: float = Field(0.0, ge=0, le=2000,
                                       description="extra zoned units per 1k households")
    mf_allowed_share: Optional[float] = Field(None, ge=0, le=1,
                                              description="new multifamily-allowed land share")
    note: str = ""


@app.post("/scenarios", status_code=201)
def create_scenario(s: ScenarioIn):
    row = _find(s.jurisdiction)
    result = core.simulate(DF, row["key"],
                           add_capacity_per_1k=s.add_capacity_per_1k,
                           mf_allowed_share=s.mf_allowed_share)
    record = core.save_scenario({**result, "note": s.note})
    return record


@app.get("/scenarios")
def get_scenarios():
    return core.list_scenarios()
