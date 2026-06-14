"""OBI single-family zoning share per jurisdiction (area-based, from shapefiles).

Uses the Othering & Belonging Institute per-jurisdiction zipped shapefiles
(github.com/OtheringBelonging/BayAreaZoning, data/shapefile/). Computes the share
of *residential* land AREA zoned single-family-only (Zoning==1) vs multifamily-
allowed (Zoning==2). Because only the within-file ratio is used, the CRS/units
cancel out, so no reprojection is needed.

Resilient + resumable: caches zips to data/raw/obi_shp/ and partial results to
data/raw/obi_shp_shares.csv.

Output: data/processed/obi_sf_share.csv
Run:    python src/ingest_obi.py
"""
import re
import difflib
import warnings
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import geopandas as gpd

from zmi_ingest import norm, PROC, RAW

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")}
TREE = "https://api.github.com/repos/OtheringBelonging/BayAreaZoning/git/trees/master?recursive=1"
RAWBASE = "https://raw.githubusercontent.com/OtheringBelonging/BayAreaZoning/master/"
SHP_DIR = RAW / "obi_shp"
SHP_DIR.mkdir(parents=True, exist_ok=True)
CACHE = RAW / "obi_shp_shares.csv"

UNINC = {"UnincorpAlameda": "uninc::alameda", "UnincorpCC": "uninc::contra costa",
         "UnincorpMarin": "uninc::marin", "UnincorpNapa": "uninc::napa",
         "UnincorpSC": "uninc::santa clara", "UnincorpSM": "uninc::san mateo",
         "UnincorpSolano": "uninc::solano", "UnincorpSonoma": "uninc::sonoma"}


def session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=6, connect=6, read=6,
            backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])))
    s.headers.update(UA)
    return s


def stem_to_key(stem, valid):
    if stem in UNINC:
        return UNINC[stem]
    k = norm(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem))
    if k in valid:
        return k
    if f"{k} city" in valid:
        return f"{k} city"
    m = difflib.get_close_matches(k, list(valid), n=1, cutoff=0.84)
    return m[0] if m else None


def share_from_zip(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")              # geographic-CRS area warning OK (ratio only)
        gdf = gpd.read_file(f"zip://{path}")
        zcol = next((c for c in gdf.columns if c.lower() == "zoning"), None)
        if zcol is None or gdf.geometry.isna().all():
            return None
        z = pd.to_numeric(gdf[zcol], errors="coerce")
        area = gdf.geometry.area
        sf, mf = area[z == 1].sum(), area[z == 2].sum()
    if sf + mf <= 0:
        return None
    return {"sf_share": sf / (sf + mf), "mf_share": mf / (sf + mf)}


def main():
    cw = pd.read_csv(PROC / "jurisdictions_crosswalk.csv")
    valid = set(cw["key"])
    sess = session()
    tree = sess.get(TREE, timeout=60).json()["tree"]
    zips = [x["path"] for x in tree if x["path"].startswith("data/shapefile/") and x["path"].endswith(".zip")]
    print(f"OBI shapefiles: {len(zips)}")

    done = {}
    if CACHE.exists():
        done = {r["zip"]: r for r in pd.read_csv(CACHE).to_dict("records")}
        print(f"  resuming: {len(done)} cached")

    rows, unmatched, bad = list(done.values()), [], []
    for i, path in enumerate(zips):
        fname = path.split("/")[-1]
        if fname in done:
            continue
        stem = fname.replace("_zoning.zip", "")
        key = stem_to_key(stem, valid)
        if key is None:
            unmatched.append(stem)
            continue
        local = SHP_DIR / fname
        if not local.exists():
            try:
                local.write_bytes(sess.get(RAWBASE + path, timeout=60).content)
            except Exception as e:
                bad.append((stem, "dl " + repr(e)[:40]))
                continue
        try:
            res = share_from_zip(local)
        except Exception as e:
            bad.append((stem, "read " + repr(e)[:40]))
            continue
        if res is None:
            bad.append((stem, "no zoning/area"))
            continue
        res.update(zip=fname, key=key)
        rows.append(res)
        if len(rows) % 10 == 0:
            pd.DataFrame(rows).to_csv(CACHE, index=False)
            print(f"  ...{len(rows)} processed", flush=True)
    pd.DataFrame(rows).to_csv(CACHE, index=False)

    out = pd.DataFrame(rows).drop_duplicates("key")[["key", "sf_share", "mf_share"]]
    out.to_csv(PROC / "obi_sf_share.csv", index=False)
    print(f"\nmatched {out['key'].nunique()}/109")
    if unmatched:
        print("UNMATCHED:", unmatched)
    if bad:
        print("PROBLEMS:", bad)
    j = out.merge(cw[["key", "jurisdiction", "county"]], on="key")
    print("\nsf_share describe:\n", out["sf_share"].describe().round(3).to_string())
    print("\nmost single-family-exclusive:")
    print(j.sort_values("sf_share", ascending=False)[["jurisdiction", "county", "sf_share"]].head(8).to_string(index=False))
    print("\nleast single-family:")
    print(j.sort_values("sf_share")[["jurisdiction", "county", "sf_share"]].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
