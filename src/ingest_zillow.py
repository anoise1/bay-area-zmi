"""Zillow rents (ZORI) and home values (ZHVI) per Bay Area jurisdiction.

City-level Zillow research CSVs are wide (one row per city, one column per month).
We filter to the nine Bay Area counties, take the latest value and year-over-year
growth, and match RegionName to the crosswalk. (Zillow covers incorporated cities
only, so unincorporated county areas will be NaN — expected.)

Output: data/processed/zillow.csv
Run:    python src/ingest_zillow.py
"""
import io
import re
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd

from zmi_ingest import norm, PROC, RAW

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")}

# candidate filenames (Zillow renames these occasionally) — first that 200s wins
ZHVI_CANDIDATES = [
    "https://files.zillowstatic.com/research/public_csvs/zhvi/City_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    "https://files.zillowstatic.com/research/public_csvs/zhvi/City_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv",
]
ZORI_CANDIDATES = [
    "https://files.zillowstatic.com/research/public_csvs/zori/City_zori_uc_sfrcondomfr_sm_sa_month.csv",
    "https://files.zillowstatic.com/research/public_csvs/zori/City_zori_uc_sfrcondomfr_sm_month.csv",
    "https://files.zillowstatic.com/research/public_csvs/zori/City_zori_sm_month.csv",
]
BAY_COUNTIES = {"Alameda County", "Contra Costa County", "Marin County", "Napa County",
                "San Francisco County", "San Mateo County", "Santa Clara County",
                "Solano County", "Sonoma County"}


def session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=6, connect=6, read=6,
            backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])))
    s.headers.update(UA)
    return s


def fetch_first(sess, candidates, cache_name):
    cache = RAW / cache_name
    if cache.exists():
        return pd.read_csv(cache)
    for url in candidates:
        try:
            r = sess.get(url, timeout=90)
            if r.ok and r.text[:50].count(",") > 3:
                cache.write_text(r.text)
                print(f"  got {cache_name} <- {url.split('/')[-1]}")
                return pd.read_csv(io.StringIO(r.text))
        except Exception as e:
            print("  miss", url.split("/")[-1], repr(e)[:40])
    raise RuntimeError(f"no candidate worked for {cache_name}")


def latest_and_yoy(df, value_name):
    date_cols = [c for c in df.columns if re.match(r"\d{4}-\d{2}", str(c))]
    bay = df[df["CountyName"].isin(BAY_COUNTIES)].copy()
    filled = bay[date_cols].ffill(axis=1)
    bay[f"{value_name}_latest"] = filled.iloc[:, -1]
    if filled.shape[1] >= 13:
        bay[f"{value_name}_yoy"] = filled.iloc[:, -1] / filled.iloc[:, -13] - 1
    else:
        bay[f"{value_name}_yoy"] = pd.NA
    bay["latest_month"] = date_cols[-1]
    return bay[["RegionName", "CountyName", f"{value_name}_latest", f"{value_name}_yoy"]]


def to_key(name, valid):
    k = norm(name)
    if k in valid:
        return k
    if f"{k} city" in valid:
        return f"{k} city"
    return k  # leave; unmatched reported later


def main():
    cw = pd.read_csv(PROC / "jurisdictions_crosswalk.csv")
    valid = set(cw["key"])
    sess = session()
    zhvi = latest_and_yoy(fetch_first(sess, ZHVI_CANDIDATES, "zillow_zhvi_city.csv"), "zhvi")
    zori = latest_and_yoy(fetch_first(sess, ZORI_CANDIDATES, "zillow_zori_city.csv"), "zori")

    z = zhvi.merge(zori, on=["RegionName", "CountyName"], how="outer")
    z["key"] = z["RegionName"].apply(lambda n: to_key(n, valid))
    z = z[z["key"].isin(valid)].drop_duplicates("key")
    z.to_csv(PROC / "zillow.csv", index=False)

    print(f"\nmatched {z['key'].nunique()}/109 (cities only; uninc expected NaN)")
    print("coverage: zhvi", z["zhvi_latest"].notna().sum(), "| zori", z["zori_latest"].notna().sum())
    print("\nZHVI/ZORI describe:")
    print(z[["zhvi_latest", "zori_latest", "zhvi_yoy", "zori_yoy"]].describe().round(2).to_string())
    j = z.merge(cw[["key", "jurisdiction"]], on="key")
    print("\nhighest home values:")
    print(j.sort_values("zhvi_latest", ascending=False)[
        ["jurisdiction", "zhvi_latest", "zori_latest"]].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
