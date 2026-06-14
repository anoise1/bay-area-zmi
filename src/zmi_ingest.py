"""ZMI data ingestion — Bay Area Zoning Mismatch Index (DSBA project).

Pulls Bay-Area, jurisdiction-level data from the MTC/ABAG ArcGIS open-data portal
(opendata.mtc.ca.gov / services3.arcgis.com), builds the canonical 109-jurisdiction
crosswalk, and assembles a partial master table (the supply/demand/production spine).

Run:  python src/zmi_ingest.py
"""
import re
import time
from pathlib import Path
import requests
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
for d in (RAW, PROC):
    d.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")}

ARCGIS = {
    "permits": "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/residentialpermits_attributes/FeatureServer/0",
    "sites":   "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/regional_housing_need_assessment_sites/FeatureServer/0",
    "jobs":    "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/pba2040_projections_juris_job_emp/FeatureServer/0",
    "hh":      "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/pba2040_projections_juris_hh_pop/FeatureServer/0",
}

CA_COUNTY_FIPS = {1: "Alameda", 13: "Contra Costa", 41: "Marin", 55: "Napa",
                  75: "San Francisco", 81: "San Mateo", 85: "Santa Clara",
                  95: "Solano", 97: "Sonoma"}


def fetch_arcgis(url, cache_name, page=2000, force=False):
    """Page an ArcGIS FeatureServer layer -> DataFrame (cached to data/raw)."""
    cache = RAW / f"{cache_name}.parquet"
    if cache.exists() and not force:
        return pd.read_parquet(cache)
    rows, off = [], 0
    for _ in range(200):
        r = requests.get(url + "/query", headers=UA, timeout=180, params={
            "where": "1=1", "outFields": "*", "resultOffset": off,
            "resultRecordCount": page, "returnGeometry": "false", "f": "json"})
        r.raise_for_status()
        feats = r.json().get("features", [])
        if not feats:
            break
        rows.extend(f["attributes"] for f in feats)
        off += len(feats)
        time.sleep(0.2)
    df = pd.DataFrame(rows)
    df.to_parquet(cache)
    print(f"  fetched {cache_name}: {df.shape[0]} rows")
    return df


def norm(s):
    if pd.isna(s):
        return s
    s = str(s).strip().lower().replace(".", "")
    s = re.sub(r"\bst\b", "saint", s)          # St. Helena -> saint helena
    for j in ("city of ", "town of "):
        s = s.replace(j, "")
    s = s.replace("unincorporated", "uninc")
    return " ".join(s.split())


def county_norm(c):
    return norm(c).replace(" county", "").strip()


def jkey(name, county):
    """Canonical join key. Unincorporated areas -> 'uninc::<county>' so the three
    MTC naming conventions ('Alameda Uninc', 'Alameda County', 'Unincorporated
    Alameda') all collapse to one key."""
    n = norm(name)
    cc = county_norm(to_county_name(county))
    if ("uninc" in n) or n.endswith(" county"):
        return f"uninc::{cc}"
    return n


def to_county_name(c):
    """Map a county value to a name. Handles numeric FIPS (6001, '06001', 1)
    as used in the permits/sites layers, and passes names through."""
    try:
        v = int(float(c))
        code = v - 6000 if v > 6000 else (v if v < 100 else int(str(v)[-3:]))
        return CA_COUNTY_FIPS.get(code, str(c))
    except (ValueError, TypeError):
        return str(c)


def build():
    print("== fetching MTC layers ==")
    jobs = fetch_arcgis(ARCGIS["jobs"], "mtc_jobs")
    hh = fetch_arcgis(ARCGIS["hh"], "mtc_hh")
    permits = fetch_arcgis(ARCGIS["permits"], "mtc_permits")
    sites = fetch_arcgis(ARCGIS["sites"], "mtc_sites")

    # --- base crosswalk: jobs + households (109 each, same jurname/fips) ---
    base = jobs[["jurname", "fipst", "fipco", "tjob2020"]].merge(
        hh[["jurname", "hh2020", "tpop2020"]], on="jurname", how="outer")
    base["county"] = base["fipco"].astype(int).map(CA_COUNTY_FIPS)
    base["place_fips"] = (base["fipst"].astype(int).astype(str).str.zfill(2)
                          + base["fipco"].astype(int).astype(str).str.zfill(3))
    base["key"] = [jkey(n, c) for n, c in zip(base["jurname"], base["county"])]
    base = base.rename(columns={"jurname": "jurisdiction", "tjob2020": "jobs_2020",
                                "hh2020": "households_2020", "tpop2020": "pop_2020"})
    print(f"\n== crosswalk: {base['key'].nunique()} unique keys / {len(base)} rows, "
          f"{base['county'].nunique()} counties ==")

    # --- production (P): permits by jurisdiction ---
    print(f"== permits permyear range: {permits['permyear'].min()}–{permits['permyear'].max()} "
          f"(counts: {permits['permyear'].value_counts().sort_index().to_dict()}) ==")
    p = permits.copy()
    p["key"] = [jkey(n, c) for n, c in zip(p["jurisdictn"], p["county"])]
    inc = ["vlowtot", "lowtot", "modtot", "amodtot", "totalunit"]
    for c in inc:
        p[c] = pd.to_numeric(p[c], errors="coerce").fillna(0)
    prod = p.groupby("key")[inc].sum().add_prefix("permit_")

    # --- capacity (A): realistic capacity + allowed density (sites) ---
    s = sites.copy()
    s["key"] = [jkey(n, c) for n, c in zip(s["jurisdict"], s["county"])]
    s["relcapcty"] = pd.to_numeric(s["relcapcty"], errors="coerce")
    s["allowden"] = pd.to_numeric(s["allowden"], errors="coerce")
    cap = s.groupby("key").agg(realistic_capacity=("relcapcty", "sum"),
                               allowed_density_mean=("allowden", "mean"),
                               n_sites=("relcapcty", "size"))

    # --- assemble ---
    m = base.merge(prod, on="key", how="left").merge(cap, on="key", how="left")
    m["jobs_housing_ratio"] = m["jobs_2020"] / m["households_2020"]
    m["capacity_per_household"] = m["realistic_capacity"] / m["households_2020"]
    m["permit_rate_per_1k_hh"] = 1000 * m["permit_totalunit"] / m["households_2020"]

    print("\n== source match coverage (of 109) ==")
    for col in ["jobs_2020", "households_2020", "permit_totalunit", "realistic_capacity"]:
        print(f"  {col:22} {m[col].notna().sum():>3}/109")
    miss_p = sorted(set(prod.index) - set(base["key"]))
    miss_s = sorted(set(cap.index) - set(base["key"]))
    print("  unmatched permit keys:", miss_p or "none")
    print("  unmatched sites  keys:", miss_s or "none")

    base.to_csv(PROC / "jurisdictions_crosswalk.csv", index=False)
    m.to_csv(PROC / "master_partial.csv", index=False)
    print(f"\n== saved crosswalk + master_partial ({len(m)} rows) ==")

    show = ["jurisdiction", "county", "jobs_housing_ratio", "households_2020",
            "permit_totalunit", "realistic_capacity", "capacity_per_household"]
    print(m[show].sort_values("jobs_housing_ratio", ascending=False).head(8).to_string(index=False))
    return m


if __name__ == "__main__":
    build()
