"""Assemble the ZMI v3 master table: 109 Bay Area jurisdictions x ~45 columns.

Joins (on the canonical `key` from zmi_ingest.jkey):
  spine (MTC jobs/hh/permits14-17/5th-cycle sites)  <- data/processed/master_partial.csv
  RHNA 2023-31 by income                            <- data/raw/v3/rhna_2023_2031_allocation.csv
  HCD APR permits 2018-2025 by income (Table A2)    <- data/raw/hcd_apr/tablea2-2.csv
  HCD 6th-cycle sites capacity (Tables A/B, PreSB6) <- data/raw/v3/hcd_sites6_*.parquet
    (10 missing juris imputed: APR Table C 2023+ -> 5th-cycle MTC; capacity_vintage flag)
  OBI single-family share, Zillow ZHVI/ZORI         <- data/processed/*.csv
  ACS units/income/rent/value/tenure/race           <- data/raw/v3/acs_censusreporter.csv
  NZLUD friction (36/109)                           <- data/raw/nzlud/nzlud_muni.csv
  LODES 2022 jobs/workers                           <- data/raw/v3/lodes_*.csv.gz
  PBA50 growth geographies HRA/TRA shares           <- data/raw/v3/pba50_growth_geogs.geojson
  SB79 zones / TPA / HQTA / EPC area shares         <- data/raw/v3/*.geojson (spatial overlay)

Then computes winsorized z-scores, the D/C/F pillars, ZMI variants, and saves
  data/processed/bay_area_zmi_v3.csv  + data/processed/apr_permits_by_year.csv

Run:  /opt/anaconda3/bin/python src/assemble_v3.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from zmi_ingest import jkey, norm, CA_COUNTY_FIPS  # noqa: E402

RAW, V3, PROC = ROOT / "data/raw", ROOT / "data/raw/v3", ROOT / "data/processed"
BAY_UP = {"ALAMEDA", "CONTRA COSTA", "MARIN", "NAPA", "SAN FRANCISCO",
          "SAN MATEO", "SANTA CLARA", "SOLANO", "SONOMA"}
FIPS2CO = {f"06{c:03d}": n for c, n in
           {1: "Alameda", 13: "Contra Costa", 41: "Marin", 55: "Napa", 75: "San Francisco",
            81: "San Mateo", 85: "Santa Clara", 95: "Solano", 97: "Sonoma"}.items()}


def wz(s, lo=0.05, hi=0.95):
    """Winsorized z-score."""
    s = pd.to_numeric(s, errors="coerce")
    s = s.clip(s.quantile(lo), s.quantile(hi))
    return (s - s.mean()) / s.std()


# ---------------------------------------------------------------- spine
spine = pd.read_csv(PROC / "master_partial.csv")
spine = spine.rename(columns={
    "realistic_capacity": "capacity5_units", "allowed_density_mean": "density5_mean",
    "n_sites": "n_sites5", "permit_totalunit": "permits1417_total",
    "permit_vlowtot": "permits1417_vlow", "permit_lowtot": "permits1417_low",
    "jobs_housing_ratio": "jh_ratio_2020"})
spine = spine.drop(columns=["capacity_per_household", "permit_rate_per_1k_hh",
                            "permit_modtot", "permit_amodtot"], errors="ignore")
print(f"spine: {spine.shape}")

# ---------------------------------------------------------------- RHNA 6th cycle
rhna = pd.read_csv(V3 / "rhna_2023_2031_allocation.csv")
co_of = dict(zip(spine["key"].map(lambda k: k.split("::")[-1]), spine["county"]))
def rhna_key(name):
    n = norm(name).replace("(city)", "").strip()
    if n.startswith("uninc"):
        n = n.replace("uninc", "").strip()
        n = n.removesuffix(" county").strip()   # "Unincorporated Alameda County"
        return f"uninc::{n}"
    return n
rhna["key"] = rhna["jurisdiction"].map(rhna_key)
rhna = rhna.set_index("key")[["rhna_very_low", "rhna_low", "rhna_moderate",
                              "rhna_above_moderate", "rhna_total"]]
m = spine.merge(rhna, on="key", how="left")
print(f"RHNA matched: {m['rhna_total'].notna().sum()}/109")

# ---------------------------------------------------------------- APR A2 permits 2018-2025
bp = {"vlow": ["BP_ACUTELY_LOW_INCOME_DR", "BP_ACUTELY_LOW_INCOME_NDR",
               "BP_EXTREMELY_LOW_INCOME_DR", "BP_EXTREMELY_INCOME_NDR",
               "BP_VLOW_INCOME_DR", "BP_VLOW_INCOME_NDR"],
      "low": ["BP_LOW_INCOME_DR", "BP_LOW_INCOME_NDR"],
      "mod": ["BP_MOD_INCOME_DR", "BP_MOD_INCOME_NDR"],
      "above": ["BP_ABOVE_MOD_INCOME"]}
allbp = [c for cols in bp.values() for c in cols]
a2 = pd.read_csv(RAW / "hcd_apr/tablea2-2.csv", low_memory=False,
                 usecols=["JURIS_NAME", "CNTY_NAME", "YEAR", "UNIT_CAT"] + allbp)
a2["CNTY_NAME"] = a2["CNTY_NAME"].astype(str).str.upper().str.strip()
a2 = a2[a2["CNTY_NAME"].isin(BAY_UP)]
for c in allbp:
    a2[c] = pd.to_numeric(a2[c], errors="coerce").fillna(0)
for band, cols in bp.items():
    a2[band] = a2[cols].sum(axis=1)
a2["total"] = a2[list(bp)].sum(axis=1)
a2["key"] = [jkey(j, c.title()) for j, c in zip(a2["JURIS_NAME"], a2["CNTY_NAME"])]
yearly = (a2.groupby(["key", "YEAR"])[["vlow", "low", "mod", "above", "total"]]
            .sum().reset_index().rename(columns={"YEAR": "year"}))
yearly.to_csv(PROC / "apr_permits_by_year.csv", index=False)
tot = yearly.groupby("key")[["vlow", "low", "mod", "above", "total"]].sum()
tot.columns = [f"permits1825_{c}" for c in tot.columns]
cyc6 = (yearly[yearly["year"] >= 2023].groupby("key")[["total", "vlow", "low"]].sum()
        .rename(columns={"total": "permits2325_total", "vlow": "permits2325_vlow",
                         "low": "permits2325_low"}))
# structure split: APR totals include ADUs and single-family (tear-down rebuilds included);
# multifamily is the RHNA-scale margin
cat = a2.assign(grp=a2["UNIT_CAT"].map(
    {"5+": "mf5", "2 to 4": "mf24", "ADU": "adu",
     "SFD": "sf", "SFA": "sf", "MH": "sf"}))
cat = (cat.groupby(["key", "grp"])["total"].sum().unstack(fill_value=0)
          .add_prefix("permits1825_"))
m = (m.merge(tot, on="key", how="left").merge(cyc6, on="key", how="left")
       .merge(cat, on="key", how="left"))
print(f"APR permits matched: {m['permits1825_total'].notna().sum()}/109 "
      f"(unmatched APR keys: {sorted(set(tot.index) - set(m['key'])) or 'none'})")

# ---------------------------------------------------------------- 6th-cycle capacity
sA = pd.read_parquet(V3 / "hcd_sites6_tableA.parquet")
sP = pd.read_parquet(V3 / "hcd_sites6_presb6_ply.parquet")
sA = pd.concat([sA, sP], ignore_index=True)
sB = pd.read_parquet(V3 / "hcd_sites6_tableB.parquet")
for df_ in (sA, sB):
    df_["Total_Capacity"] = pd.to_numeric(df_["Total_Capacity"], errors="coerce")
    df_["key"] = [jkey(j, c) for j, c in zip(df_["jurisdiction_name"], df_["County_Name"])]
sA["Lower_Income_Capacity"] = pd.to_numeric(sA["Lower_Income_Capacity"], errors="coerce")
sA["maxden"] = pd.to_numeric(sA["Max_Density_Allowed_units_per_a"], errors="coerce")
sA["vacant"] = sA["Existing_Use_Vacancy"].astype(str).str.lower().str.startswith("vacant")
capA = sA.groupby("key").agg(
    capacity6_units=("Total_Capacity", "sum"),
    capacity6_lower=("Lower_Income_Capacity", "sum"),
    density6_mean=("maxden", "mean"),
    sites6_vacant_share=("vacant", "mean"),
    n_sites6=("Total_Capacity", "size"))
capB = sB.groupby("key").agg(capacity6_rezone_units=("Total_Capacity", "sum"))
m = m.merge(capA, on="key", how="left").merge(capB, on="key", how="left")

# impute the 10 jurisdictions missing from the DGS statewide map
tc = pd.read_csv(RAW / "hcd_apr/tablec.csv", low_memory=False,
                 usecols=["JURISDICTION", "COUNTY", "YEAR", "REALISTIC_CAPACITY"])
tc["COUNTY"] = tc["COUNTY"].astype(str).str.upper().str.strip()
tc = tc[tc["COUNTY"].isin(BAY_UP) & (tc["YEAR"] >= 2023)]
tc["REALISTIC_CAPACITY"] = pd.to_numeric(tc["REALISTIC_CAPACITY"], errors="coerce")
tc["key"] = [jkey(j, c.title()) for j, c in zip(tc["JURISDICTION"], tc["COUNTY"])]
tcap = tc.groupby("key")["REALISTIC_CAPACITY"].sum()
m["capacity_vintage"] = np.where(m["capacity6_units"].notna(), "6th_cycle", "missing")
need = m["capacity6_units"].isna()
m.loc[need, "capacity6_units"] = m.loc[need, "key"].map(tcap)
m.loc[need & m["capacity6_units"].notna(), "capacity_vintage"] = "apr_tableC_2023plus"
need = m["capacity6_units"].isna()
m.loc[need, "capacity6_units"] = m.loc[need, "capacity5_units"]
m.loc[need, "capacity_vintage"] = "5th_cycle_fallback"
print("capacity_vintage:", m["capacity_vintage"].value_counts().to_dict())

# ---------------------------------------------------------------- OBI + Zillow
m = m.merge(pd.read_csv(PROC / "obi_sf_share.csv"), on="key", how="left")
m = m.merge(pd.read_csv(PROC / "zillow.csv").drop(columns=["RegionName", "CountyName"]),
            on="key", how="left")

# ---------------------------------------------------------------- ACS
acs = pd.read_csv(V3 / "acs_censusreporter.csv")
def acs_key(row):
    g, name = row["geoid"], str(row["jurisdiction"])
    if g.startswith("05000US"):
        return f"uninc::{norm(FIPS2CO.get(g[-5:], ''))}", "county_proxy"
    n = name.replace(" city, CA", "").replace(" town, CA", "")
    if n.endswith(" CDP, CA"):
        return None, None
    return norm(n), "place"
keys = acs.apply(acs_key, axis=1, result_type="expand")
acs["key"], acs["acs_geo"] = keys[0], keys[1]
acs = acs.dropna(subset=["key"])
acs_out = pd.DataFrame({
    "key": acs["key"], "acs_geo": acs["acs_geo"],
    "acs_units": acs["B25001001"],
    "acs_med_income": acs["B19013001"],
    "acs_med_rent": acs["B25064001"],
    "acs_med_value": acs["B25077001"],
    "acs_owner_share": acs["B25003002"] / acs["B25003001"],
    "acs_poc_share": 1 - acs["B03002003"] / acs["B03002001"],
}).drop_duplicates("key")
m = m.merge(acs_out, on="key", how="left")
print(f"ACS matched: {m['acs_units'].notna().sum()}/109")

# ---------------------------------------------------------------- place-FIPS map + NZLUD
xw = pd.read_csv(V3 / "lodes_ca_xwalk.csv.gz", dtype=str,
                 usecols=["tabblk2020", "cty", "stplc", "stplcname"])
xw = xw[xw["cty"].isin(FIPS2CO)]
plc = (xw.dropna(subset=["stplc"]).drop_duplicates("stplc"))
plc["key"] = plc["stplcname"].map(
    lambda s: norm(str(s).replace(" city, CA", "").replace(" town, CA", "")))
fips_of_key = dict(zip(plc["key"], plc["stplc"]))
m["place_fips5"] = m["key"].map(fips_of_key)

nz = pd.read_csv(RAW / "nzlud/nzlud_muni.csv", encoding="latin-1")
nz = nz[nz["statename"] == "CA"].copy()
nz["place_fips5"] = nz["GEOID"].astype(str).str.zfill(7)
nzcols = {"zri": "nzlud_zri", "parking_median": "nzlud_parking",
          "min_lot_size": "nzlud_minlot", "adu": "nzlud_adu_allowed",
          "mf_per": "nzlud_mf_permitted", "total_nz": "nzlud_approval_steps"}
m = m.merge(nz[["place_fips5"] + list(nzcols)].rename(columns=nzcols),
            on="place_fips5", how="left")
print(f"NZLUD matched: {m['nzlud_zri'].notna().sum()}/109")

# ---------------------------------------------------------------- LODES 2022
def lodes_agg(fname, geocol, out):
    df_ = pd.read_csv(V3 / fname, dtype={geocol: str}, usecols=[geocol, "C000"])
    df_ = df_.merge(xw[["tabblk2020", "cty", "stplc"]],
                    left_on=geocol, right_on="tabblk2020", how="inner")
    df_["key"] = np.where(df_["stplc"].notna(),
                          df_["stplc"].map(lambda s: plc.set_index("stplc")["key"].get(s)),
                          df_["cty"].map(lambda c: f"uninc::{norm(FIPS2CO[c])}"))
    return df_.groupby("key")["C000"].sum().rename(out)
m = m.merge(lodes_agg("lodes_ca_wac_2022.csv.gz", "w_geocode", "jobs_2022"),
            on="key", how="left")
m = m.merge(lodes_agg("lodes_ca_rac_2022.csv.gz", "h_geocode", "workers_2022"),
            on="key", how="left")
print(f"LODES matched: {m['jobs_2022'].notna().sum()}/109")

# ---------------------------------------------------------------- spatial overlays
import geopandas as gpd
jur = gpd.read_file(V3 / "jurisdictions.geojson").to_crs(3310)
jur["key"] = [jkey(n, c) for n, c in zip(jur["jurname"], jur["coname"])]
jur["jur_area"] = jur.geometry.area
jur = jur.dissolve(by="key", aggfunc={"jur_area": "sum"})

def share_of(path, out, where=None):
    g = gpd.read_file(path)
    if where is not None:
        g = g[where(g)]
    g = g.to_crs(3310)
    u = g.union_all() if hasattr(g, "union_all") else g.unary_union
    inter = jur.geometry.intersection(u).area
    return (inter / jur["jur_area"]).rename(out)

ovl = pd.concat([
    share_of(V3 / "sb79_tod_zones.geojson", "sb79_share"),
    share_of(V3 / "sb79_tod_zones.geojson", "sb79_tier1_share",
             where=lambda g: g["zone_label"].str.startswith("Tier 1")),
    share_of(V3 / "transit_priority_areas_2026.geojson", "tpa_share"),
    share_of(V3 / "hq_transit_areas.geojson", "hqta_share"),
    share_of(V3 / "equity_priority_communities.geojson", "epc_share"),
], axis=1).reset_index()
m = m.merge(ovl, on="key", how="left")

# HRA/TRA polygons are dissolved across cities (jurisdicti='Multiple') -> spatial overlay
ovl2 = pd.concat([
    share_of(V3 / "pba50_growth_geogs.geojson", "hra_share",
             where=lambda g: g["designatio"].str.contains("High-Resource", na=False)),
    share_of(V3 / "pba50_growth_geogs.geojson", "tra_share",
             where=lambda g: g["designatio"].str.contains("Transit-Rich", na=False)),
], axis=1).reset_index()
m = m.merge(ovl2, on="key", how="left")
for c in ["hra_share", "tra_share"]:
    m[c] = m[c].fillna(0).clip(0, 1)
print("overlays done")

# ---------------------------------------------------------------- derived + ZMI
m["hh"] = m["households_2020"]
m["jh_ratio_2022"] = m["jobs_2022"] / m["acs_units"].fillna(m["hh"])
m["permits1825_per_1k"] = 1000 * m["permits1825_total"] / m["hh"]
m["permits1825_mf_per_1k"] = 1000 * (m["permits1825_mf5"].fillna(0)
                                     + m["permits1825_mf24"].fillna(0)) / m["hh"]
m["adu_share_1825"] = m["permits1825_adu"] / m["permits1825_total"]
m["permits1825_belowmod_per_1k"] = 1000 * (m["permits1825_vlow"] + m["permits1825_low"]) / m["hh"]
m["capacity6_per_1k"] = 1000 * m["capacity6_units"] / m["hh"]
m["capacity5_per_1k"] = 1000 * m["capacity5_units"] / m["hh"]
m["cap_ratio_6_to_5"] = m["capacity6_per_1k"] / m["capacity5_per_1k"]
m["rhna_per_1k"] = 1000 * m["rhna_total"] / m["hh"]
m["rhna6_progress"] = m["permits2325_total"] / m["rhna_total"]
m["rhna6_lowinc_progress"] = (m["permits2325_vlow"] + m["permits2325_low"]) / \
                             (m["rhna_very_low"] + m["rhna_low"])
m["capacity_vs_rhna"] = m["capacity6_units"] / m["rhna_total"]
m["mf_allowed_share"] = 1 - m["sf_share"]

# pillars (winsorized z-scores)
zD = pd.concat([wz(m["jh_ratio_2022"]), wz(m["zori_latest"]), wz(m["zhvi_latest"]),
                wz(m["hqta_share"])], axis=1)
m["D_demand"] = zD.mean(axis=1)
zC = pd.concat([wz(m["capacity6_per_1k"]), wz(m["mf_allowed_share"])], axis=1)
m["C_capacity"] = zC.mean(axis=1)
zF = pd.concat([wz(m["nzlud_parking"]), wz(m["nzlud_minlot"]),
                wz(m["nzlud_approval_steps"])], axis=1)
m["F_friction"] = zF.mean(axis=1)          # NaN where NZLUD missing
m["F_coverage"] = zF.notna().any(axis=1)
m["P_delivery"] = wz(m["permits1825_per_1k"])

m["zmi_core"] = m["D_demand"] - m["C_capacity"]
m["zmi_full"] = m["zmi_core"] + m["F_friction"].fillna(0)
m["zmi_realized"] = m["D_demand"] - m["P_delivery"]
# era-matched variant: 5th-cycle capacity pillar, for validating against 2018-25 permits
zC5 = pd.concat([wz(m["capacity5_per_1k"]), wz(m["mf_allowed_share"])], axis=1)
m["C_capacity_5th"] = zC5.mean(axis=1)
m["zmi_core_5th"] = m["D_demand"] - m["C_capacity_5th"]

# ---------------------------------------------------------------- save + report
m = m.drop(columns=["hh"])
m.to_csv(PROC / "bay_area_zmi_v3.csv", index=False)
print(f"\nSAVED data/processed/bay_area_zmi_v3.csv: {m.shape[0]} rows x {m.shape[1]} cols")

print("\n== coverage (non-null /109) ==")
for c in ["rhna_total", "permits1825_total", "capacity6_units", "sf_share", "zhvi_latest",
          "zori_latest", "acs_units", "jobs_2022", "sb79_share", "hqta_share", "hra_share",
          "nzlud_zri", "zmi_core"]:
    print(f"  {c:28} {m[c].notna().sum():>3}")

print("\n== validation (era-matched): permits 18-25 vs 5th-cycle structure ==")
import statsmodels.api as sm
d = m[["zhvi_latest", "capacity5_per_1k", "permits1825_per_1k", "zmi_core_5th"]].dropna()
X = pd.DataFrame({"rent": wz(d["zhvi_latest"]), "cap5": wz(d["capacity5_per_1k"])})
X["rentXcap5"] = X["rent"] * X["cap5"]
r = sm.OLS(np.log1p(d["permits1825_per_1k"]), sm.add_constant(X)).fit()
print(f"  cap5 coef {r.params['cap5']:+.3f} (p={r.pvalues['cap5']:.3f}), R2={r.rsquared:.3f}, n={len(d)}")
print(f"  corr(zmi_core_5th, log permits/1k): "
      f"{d['zmi_core_5th'].corr(np.log1p(d['permits1825_per_1k'])):+.3f}")
v6 = m[["capacity6_per_1k", "zhvi_latest", "permits1825_per_1k"]].dropna()
X6 = pd.DataFrame({"rent": wz(v6["zhvi_latest"]), "cap6": wz(v6["capacity6_per_1k"])})
r6 = sm.OLS(np.log1p(v6["permits1825_per_1k"]), sm.add_constant(X6)).fit()
print(f"  (decoupling check) cap6 coef {r6.params['cap6']:+.3f} (p={r6.pvalues['cap6']:.3f}) "
      f"— 6th-cycle paper capacity no longer tracks past delivery")
vv = m[["capacity5_per_1k", "capacity6_per_1k"]].dropna()
print(f"  corr(cap5/1k, cap6/1k) = {vv['capacity5_per_1k'].corr(vv['capacity6_per_1k']):+.3f}")

show = ["jurisdiction", "county", "zmi_core", "D_demand", "C_capacity",
        "rhna6_progress", "sb79_share"]
print("\n== TOP 10 mismatch (high demand, low legal capacity) ==")
print(m.nlargest(10, "zmi_core")[show].round(2).to_string(index=False))
print("\n== BOTTOM 10 ==")
print(m.nsmallest(10, "zmi_core")[show].round(2).to_string(index=False))
