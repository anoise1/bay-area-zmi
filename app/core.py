"""Shared data access + index logic for the ZMI web apps (FastAPI + Streamlit).

The pillar definitions here MUST mirror src/assemble_v3.py — `verify_consistency()`
checks that the recomputed index matches the stored one.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCENARIOS_FILE = DATA / "app" / "scenarios.json"
_LOCK = threading.Lock()

D_INPUTS = ["jh_ratio_2022", "zori_latest", "zhvi_latest", "hqta_share"]
C_INPUTS = ["capacity6_per_1k", "mf_allowed_share"]

# columns exposed by the API list endpoint
PUBLIC_COLS = [
    "jurisdiction", "county", "zmi_core", "zmi_full", "zmi_realized",
    "D_demand", "C_capacity", "F_friction",
    "rhna_total", "rhna6_progress", "permits1825_total", "permits1825_per_1k",
    "permits1825_mf_per_1k", "adu_share_1825", "capacity6_per_1k", "capacity5_per_1k",
    "sf_share", "mf_allowed_share", "zhvi_latest", "zori_latest",
    "sb79_share", "sb79_exposure", "hqta_share", "hra_share", "capacity_vintage",
]


def wz(s, lo=0.05, hi=0.95):
    """Winsorized z-score (identical to assemble_v3)."""
    s = pd.to_numeric(s, errors="coerce")
    s = s.clip(s.quantile(lo), s.quantile(hi))
    return (s - s.mean()) / s.std()


def load_master():
    df = pd.read_csv(DATA / "processed" / "bay_area_zmi_v3.csv")
    df["price_to_income"] = df["zhvi_latest"] / df["acs_med_income"]
    df["permit_capture_2325"] = df["permits2325_total"] / df["capacity6_units"]
    df["sb79_exposure"] = df["sb79_share"] * df["sf_share"]
    df["prescription"] = df.apply(prescribe, axis=1)
    return df


def load_yearly():
    return pd.read_csv(DATA / "processed" / "apr_permits_by_year.csv")


def load_geojson():
    with open(DATA / "app" / "jurisdictions_simplified.geojson") as f:
        return json.load(f)


def compute_zmi(df):
    """Recompute pillar scores + zmi_core for a (possibly modified) master frame."""
    D = pd.concat([wz(df[c]) for c in D_INPUTS], axis=1).mean(axis=1)
    C = pd.concat([wz(df[c]) for c in C_INPUTS], axis=1).mean(axis=1)
    return D, C, D - C


def verify_consistency(df, tol=1e-6):
    _, _, zmi = compute_zmi(df)
    return float((zmi - df["zmi_core"]).abs().max()) < tol


def prescribe(r):
    if r["D_demand"] < -0.4:
        return "low demand — do not force; focus subsidy elsewhere"
    if r["C_capacity"] < -0.3:
        return "capacity-bound — upzone / end SF-only (SB 9, SB 79)"
    if pd.notna(r.get("F_friction")) and r["F_friction"] > 0.3:
        return "friction-bound — cut fees/parking, ministerial approval (SB 423)"
    pc = r.get("permit_capture_2325")
    if pc is not None and pd.notna(pc) and pc < 0.05:
        return "conversion-bound — capacity exists, delivery lags: process/feasibility"
    return "on track — monitor"


def simulate(df, key, add_capacity_per_1k=0.0, mf_allowed_share=None):
    """Rezoning scenario: change one jurisdiction, recompute the whole index
    (z-scores are relative, so every score can shift slightly)."""
    base_row = df.loc[df["key"] == key]
    if base_row.empty:
        raise KeyError(key)
    sim = df.copy()
    i = base_row.index[0]
    sim.loc[i, "capacity6_per_1k"] = sim.loc[i, "capacity6_per_1k"] + add_capacity_per_1k
    if mf_allowed_share is not None:
        sim.loc[i, "mf_allowed_share"] = mf_allowed_share
    _, _, zmi_new = compute_zmi(sim)
    _, _, zmi_old = compute_zmi(df)
    rank_old = int(zmi_old.rank(ascending=False)[i])
    rank_new = int(zmi_new.rank(ascending=False)[i])
    return {
        "jurisdiction": df.loc[i, "jurisdiction"],
        "zmi_before": round(float(zmi_old[i]), 3),
        "zmi_after": round(float(zmi_new[i]), 3),
        "zmi_delta": round(float(zmi_new[i] - zmi_old[i]), 3),
        "rank_before": rank_old,
        "rank_after": rank_new,
        "inputs": {
            "add_capacity_per_1k": add_capacity_per_1k,
            "mf_allowed_share": mf_allowed_share,
            "capacity6_per_1k_after": round(float(sim.loc[i, "capacity6_per_1k"]), 1),
        },
    }


def list_scenarios():
    if SCENARIOS_FILE.exists():
        return json.loads(SCENARIOS_FILE.read_text())
    return []


def save_scenario(record):
    with _LOCK:
        items = list_scenarios()
        record = {"id": len(items) + 1,
                  "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  **record}
        items.append(record)
        SCENARIOS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCENARIOS_FILE.write_text(json.dumps(items, indent=1))
    return record
