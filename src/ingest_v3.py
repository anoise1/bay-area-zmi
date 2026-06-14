"""ZMI v3 ingestion — fresh data layer for the Zoning Mismatch Index.

Downloads everything reachable for the v3 design:
  * MTC/ABAG ArcGIS layers (SB 79 TOD zones/stops, PBA50/PBA50+ growth geographies,
    major transit stops, high-quality transit areas, transit priority areas 2026,
    growth boundaries, jurisdiction polygons, equity priority communities)
  * ABAG Final RHNA 2023-2031 allocation plan (PDF, table extracted later)
  * Terner fee / hard-cost PDFs
  * Census LODES (CA crosswalk + WAC 2022) for current jobs by jurisdiction
  * ACS 2018-2022/2024 via the censusreporter API

Idempotent: each artifact is skipped when its file already exists.
Run:  python src/ingest_v3.py
"""
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "v3"
RAW.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36")}

MTC = "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services"

# name -> (service/layer URL, with_geometry)
ARCGIS_LAYERS = {
    "sb79_tod_zones":      (f"{MTC}/mtc_sb79_tod_zones/FeatureServer/1", True),
    "sb79_tod_stops":      (f"{MTC}/mtc_sb79_tod_stops/FeatureServer/1", True),
    "pba50_growth_geogs":  (f"{MTC}/pba2050_growth_geographies_2020/FeatureServer/0", True),
    "pba50plus_growth_geogs": (f"{MTC}/pba50plus_fbp_growth_geographies/FeatureServer/0", True),
    "major_transit_stops_2026": (f"{MTC}/cdot_br_hq_transit_stops_apr2026/FeatureServer/0", True),
    "hq_transit_areas":    (f"{MTC}/cdot_ca_hq_transit_areas/FeatureServer/0", True),
    "transit_priority_areas_2026": (f"{MTC}/transit_priority_areas_2026/FeatureServer/0", True),
    "growth_boundaries_2019": (f"{MTC}/growth_boundaries_2019/FeatureServer/0", True),
    "jurisdictions":       (f"{MTC}/region_jurisdiction_clp/FeatureServer/0", True),
    "equity_priority_communities": (
        f"{MTC}/draft_equity_priority_communities_pba2050plus_acs2022a/FeatureServer/0", True),
}

DIRECT_FILES = {
    "abag_rhna_final_plan_2023_2031.pdf":
        "https://abag.ca.gov/sites/default/files/documents/2021-12/Final_RHNA_Allocation_Report_2023-2031-approved_0.pdf",
    "terner_residential_impact_fees_2019.pdf":
        "https://ternercenter.berkeley.edu/wp-content/uploads/pdfs/Residential_Impact_Fees_in_California_August_2019.pdf",
    "terner_development_fees_2018.pdf":
        "https://ternercenter.berkeley.edu/wp-content/uploads/pdfs/Development_Fees_Report_Final_2.pdf",
    "terner_hard_construction_costs_2020.pdf":
        "https://ternercenter.berkeley.edu/wp-content/uploads/pdfs/Hard_Construction_Costs_March_2020.pdf",
    "lodes_ca_xwalk.csv.gz":
        "https://lehd.ces.census.gov/data/lodes/LODES8/ca/ca_xwalk.csv.gz",
    "lodes_ca_wac_2022.csv.gz":
        "https://lehd.ces.census.gov/data/lodes/LODES8/ca/wac/ca_wac_S000_JT00_2022.csv.gz",
    "lodes_ca_rac_2022.csv.gz":
        "https://lehd.ces.census.gov/data/lodes/LODES8/ca/rac/ca_rac_S000_JT00_2022.csv.gz",
}

BAY_COUNTY_FIPS = ["001", "013", "041", "055", "075", "081", "085", "095", "097"]


def layer_count(url):
    r = requests.get(f"{url}/query", headers=UA, timeout=60,
                     params={"where": "1=1", "returnCountOnly": "true", "f": "json"})
    r.raise_for_status()
    return r.json().get("count", -1)


def fetch_layer_geojson(name, url):
    out = RAW / f"{name}.geojson"
    if out.exists():
        print(f"  [skip] {name} (exists)")
        return
    n = layer_count(url)
    feats, off = [], 0
    while True:
        r = requests.get(f"{url}/query", headers=UA, timeout=300, params={
            "where": "1=1", "outFields": "*", "resultOffset": off,
            "resultRecordCount": 1000, "f": "geojson", "outSR": 4326})
        r.raise_for_status()
        page = r.json().get("features", [])
        if not page:
            break
        feats.extend(page)
        off += len(page)
        if off >= n > 0:
            break
        time.sleep(0.2)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    mb = out.stat().st_size / 1e6
    print(f"  [ok]   {name}: {len(feats)}/{n} features, {mb:.1f} MB")


def fetch_direct(fname, url):
    out = RAW / fname
    if out.exists() and out.stat().st_size > 10_000:
        print(f"  [skip] {fname} (exists)")
        return
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"  [ok]   {fname}: {len(r.content)/1e6:.1f} MB")


def fetch_acs():
    """ACS via the censusreporter API. Place GEOIDs come from the LODES
    crosswalk (stplc/stplcname for the 9 Bay counties); the unincorporated
    county-remainder jurisdictions get county (050) geographies as proxies."""
    out = RAW / "acs_censusreporter.csv"
    if out.exists():
        print("  [skip] acs_censusreporter.csv (exists)")
        return
    xw = pd.read_csv(RAW / "lodes_ca_xwalk.csv.gz", dtype=str,
                     usecols=["cty", "stplc", "stplcname"])
    xw = xw[xw["cty"].isin(["06" + c for c in BAY_COUNTY_FIPS])]
    places = (xw.dropna(subset=["stplc"])
                .drop_duplicates("stplc")[["stplc", "stplcname"]])
    geos = {f"16000US{r.stplc}": r.stplcname for r in places.itertuples()}
    for c in BAY_COUNTY_FIPS:
        geos[f"05000US06{c}"] = f"uninc-county-06{c}"
    tables = "B25001,B19013,B25064,B25077,B25003,B03002"
    rows = []
    gids = list(geos)
    for i in range(0, len(gids), 20):
        chunk = ",".join(gids[i:i + 20])
        r = requests.get("https://api.censusreporter.org/1.0/data/show/latest",
                         headers=UA, timeout=120,
                         params={"table_ids": tables, "geo_ids": chunk})
        if r.status_code != 200:
            print(f"  [warn] censusreporter chunk {i}: HTTP {r.status_code} "
                  f"{r.text[:120]}")
            continue
        d = r.json()
        for gid, td in d.get("data", {}).items():
            row = {"geoid": gid, "jurisdiction": geos.get(gid, "?")}
            for t, cols in td.items():
                for cid, v in cols.get("estimate", {}).items():
                    row[cid] = v
            rows.append(row)
        time.sleep(0.5)
    if rows:
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"  [ok]   ACS: {len(rows)} geographies x tables {tables}")


def main():
    print("== ArcGIS layers (MTC/ABAG) ==")
    for name, (url, _geom) in ARCGIS_LAYERS.items():
        try:
            fetch_layer_geojson(name, url)
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
    print("== direct files ==")
    for fname, url in DIRECT_FILES.items():
        try:
            fetch_direct(fname, url)
        except Exception as e:
            print(f"  [FAIL] {fname}: {e}")
    print("== ACS via censusreporter ==")
    try:
        fetch_acs()
    except Exception as e:
        print(f"  [FAIL] acs: {e}")
    print("done.")


if __name__ == "__main__":
    main()
