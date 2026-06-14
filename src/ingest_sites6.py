"""Download the HCD/DGS statewide 6th-cycle Housing Element Sites Inventory
(Bay Area subset) from the public DGS ArcGIS server that backs HCD's
"Housing Element Sites and Local Government Owned Sites" map.

Layers (services8.arcgis.com/a4GMqC2tQHvYiVtK):
  - SB6_ParcelsA_Pub_Join/4            -> sites inventory Table A (capacity by income)
  - Housing_Element__SB6B__ply_join/4  -> Table B (sites to be rezoned, proposed zoning)
  - SB6_PointsHist_Pub_Join (PreSB6)   -> pre-2021-format submissions

Attributes only (lat/long included; polygon geometry skipped — not needed for
jurisdiction-level aggregation). Run: python src/ingest_sites6.py
"""
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "v3"
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36")}
S8 = "https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services"
BAY = ("County_Name IN ('Alameda','Contra Costa','Marin','Napa','San Francisco',"
       "'San Mateo','Santa Clara','Solano','Sonoma')")

LAYERS = {
    "hcd_sites6_tableA": f"{S8}/SB6_ParcelsA_Pub_Join/FeatureServer/4",
    "hcd_sites6_tableB": f"{S8}/Housing_Element__SB6B__ply_join/FeatureServer/4",
    "hcd_sites6_presb6_pts": f"{S8}/SB6_PointsHist_Pub_Join/FeatureServer/6",
    "hcd_sites6_presb6_ply": f"{S8}/Housing_Element__PreSB6__ply_join/FeatureServer/10",
}


def fetch(name, url):
    out = RAW / f"{name}.parquet"
    if out.exists():
        print(f"[skip] {name}")
        return
    rows, off = [], 0
    while True:
        r = requests.get(f"{url}/query", headers=UA, timeout=300, params={
            "where": BAY, "outFields": "*", "resultOffset": off,
            "resultRecordCount": 1000, "returnGeometry": "false", "f": "json"})
        r.raise_for_status()
        d = r.json()
        if "error" in d:
            print(f"[FAIL] {name}: {d['error']}")
            return
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(f["attributes"] for f in feats)
        off += len(feats)
        time.sleep(0.15)
    df = pd.DataFrame(rows)
    df.to_parquet(out)
    print(f"[ok] {name}: {df.shape[0]} rows x {df.shape[1]} cols, "
          f"{df['jurisdiction_name'].nunique() if 'jurisdiction_name' in df else '?'} jurisdictions")


for name, url in LAYERS.items():
    try:
        fetch(name, url)
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
print("done.")
