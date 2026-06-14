"""Bay Area Zoning Mismatch Index — Streamlit app (pilot deliverable).

Run:  /opt/anaconda3/bin/streamlit run streamlit_app.py     (from repo root)
The pages mirror the report notebook ZMI_Bay_Area.ipynb.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import statsmodels.api as sm
import streamlit as st
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import core

st.set_page_config(page_title="Bay Area Zoning Mismatch Index", page_icon="🏘️",
                   layout="wide")

METRICS = {
    "zmi_core": "ZMI (demand − capacity)",
    "D_demand": "Demand pillar",
    "C_capacity": "Capacity pillar",
    "permits1825_per_1k": "Permits 2018-25 per 1k households",
    "permits1825_mf_per_1k": "Multifamily permits 2018-25 per 1k",
    "capacity6_per_1k": "Zoned capacity (6th cycle) per 1k",
    "sf_share": "Single-family-only land share",
    "rhna6_progress": "RHNA 2023-31 progress",
    "sb79_exposure": "SB 79 exposure",
    "adu_share_1825": "ADU share of permits",
}


@st.cache_data
def data():
    df = core.load_master()
    return df, core.load_yearly(), core.load_geojson()


DF, YEARLY, GEO = data()


def choropleth(metric):
    fig = px.choropleth_map(
        DF, geojson=GEO, locations="key", featureidkey="properties.key",
        color=metric, color_continuous_scale="RdYlGn_r",
        hover_name="jurisdiction",
        hover_data={"key": False, "county": True, metric: ":.2f"},
        map_style="carto-positron", center={"lat": 37.85, "lon": -122.27}, zoom=7.6,
        opacity=0.75, height=620,
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                      coloraxis_colorbar_title=None)
    return fig


# ----------------------------------------------------------------------- pages
def page_overview():
    st.title("🏘️ A Zoning Mismatch Index for the San Francisco Bay Area")
    st.caption("Where the region needs homes vs. what local rules allow — and what "
               "2018–2025 permit data reveals. DSBA 2025/26 · data current to June 2026.")
    c = st.columns(4)
    c[0].metric("RHNA 2023-31 need", "441,176 units")
    c[1].metric("Permitted 2018-25", f"{int(DF.permits1825_total.sum()):,} units")
    c[2].metric("Median SF-only land share", f"{DF.sf_share.median():.0%}")
    c[3].metric("Jurisdictions in draft SB 79 zones", f"{(DF.sb79_share > 0).sum()} / 109")
    st.markdown("""
**The index.** For each of the 109 Bay Area jurisdictions, the ZMI compares a **Demand pillar**
(jobs per housing unit, Zillow values & rents, high-quality-transit coverage) against a
**Capacity pillar** (zoned site capacity per household, multifamily-allowed land share), both as
winsorized z-scores: `ZMI = z(Demand) − z(Capacity)`. High ZMI = housing is wanted there and the
rules don't allow it. A friction pillar (NZLUD) and a delivery pillar (HCD permits) extend it.

> ⚠️ **How to read the ranking:** it measures *restrictiveness relative to demand*, not quality of
> life. **Rank 1 = the most blocked jurisdiction** (e.g. Colma, Palo Alto); rank 109 = the least
> blocked. Upzoning a city in the simulator moves it *away* from rank 1 — that's the intended
> direction.

**Four headline findings** *(details on the Hypotheses page)*:
1. **The ADU mask** — the most-blocked towns *look* productive (88 vs 55 permits/1k), but 54% of
   their permits are ADUs; their **multifamily** permitting is ~1.4 units per 1k households over
   eight years — **11× below** the open group.
2. **Paper capacity has decoupled from delivery** — pre-mandate (5th-cycle) zoned capacity predicts
   2018-25 permits (p=.003); the new state-mandated 6th-cycle capacity predicts nothing (the two
   correlate at just +0.33). On the multifamily margin, the *value × capacity* interaction
   replicates the Built-Out-Cities result (p=.001).
3. **The flat gradient** — zoned capacity is *uncorrelated* with transit access (ρ≈−0.08): the
   region plans transit-oriented growth its zoning never made legal. SB 79 (eff. 2026-07-01)
   targets exactly this margin.
4. **The equity gap runs through volume** — need shares are equal (~41% below-moderate everywhere)
   but high-resource jurisdictions deliver low-income RHNA ~35% slower.
""")
    st.info("Use the sidebar: interactive **map**, per-city **profiles & prescriptions**, the "
            "**hypothesis tests**, the **SB 79 ranking**, and a **rezoning simulator** "
            "(the REST API's POST /scenarios in UI form).")


def page_map():
    st.header("Mismatch map & rankings")
    metric = st.selectbox("Metric", list(METRICS), format_func=METRICS.get)
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(choropleth(metric), width='stretch')
    with right:
        d = DF.dropna(subset=[metric]).sort_values(metric, ascending=False)
        show = pd.concat([d.head(12), d.tail(12)])
        fig = go.Figure(go.Bar(
            x=show[metric], y=show["jurisdiction"], orientation="h",
            marker_color=np.where(show[metric] > show[metric].median(),
                                  "#c1443c", "#2a9d8f")))
        fig.update_layout(height=620, margin=dict(l=0, r=0, t=24, b=0),
                          yaxis=dict(autorange="reversed"),
                          title=f"Top / bottom 12 — {METRICS[metric]}")
        st.plotly_chart(fig, width='stretch')
    with st.expander("Full table (all 109)"):
        st.dataframe(DF[["jurisdiction", "county"] + list(METRICS)]
                     .sort_values(metric, ascending=False).round(3),
                     width='stretch', height=420)
        st.download_button("Download master dataset (CSV)",
                           DF.to_csv(index=False), "bay_area_zmi_v3.csv", "text/csv")


def page_profile():
    st.header("Jurisdiction profile")
    name = st.selectbox("Jurisdiction", sorted(DF["jurisdiction"]))
    r = DF[DF["jurisdiction"] == name].iloc[0]
    rank = int(DF["zmi_core"].rank(ascending=False)[r.name])
    c = st.columns(5)
    c[0].metric("ZMI", f"{r.zmi_core:+.2f}", f"mismatch rank {rank}/109", delta_color="off",
                help="Rank 1 = most blocked (demand most exceeds legal capacity); "
                     "rank 109 = least blocked. Not a livability ranking.")
    c[1].metric("Demand pillar", f"{r.D_demand:+.2f}")
    c[2].metric("Capacity pillar", f"{r.C_capacity:+.2f}")
    c[3].metric("RHNA 2023-31", f"{int(r.rhna_total):,}",
                f"{r.rhna6_progress:.0%} permitted so far", delta_color="off")
    c[4].metric("SB 79 land share", f"{r.sb79_share:.1%}")
    st.success(f"**Diagnosis → lever:** {r.prescription}")

    left, right = st.columns(2)
    with left:
        comp = pd.DataFrame({
            "component": ["Demand (D)", "− Capacity (−C)", "Friction (F)"],
            "value": [r.D_demand, -r.C_capacity,
                      r.F_friction if pd.notna(r.F_friction) else 0],
        })
        fig = px.bar(comp, x="component", y="value", color="component",
                     color_discrete_sequence=["#356f9f", "#c1443c", "#888"],
                     title="What drives the score (ZMI = D − C)")
        fig.update_layout(showlegend=False, height=340, margin=dict(t=40, b=0))
        st.plotly_chart(fig, width='stretch')
        if pd.isna(r.F_friction):
            st.caption("Friction pillar: no NZLUD coverage for this jurisdiction (36/109 covered).")
    with right:
        y = YEARLY[YEARLY["key"] == r.key]
        fig = px.bar(y, x="year", y=["vlow", "low", "mod", "above"],
                     title="Permits by income band (HCD APR)",
                     color_discrete_sequence=px.colors.sequential.Viridis_r)
        fig.update_layout(height=340, legend_title=None, margin=dict(t=40, b=0))
        st.plotly_chart(fig, width='stretch')

    cols = ["zhvi_latest", "zori_latest", "jh_ratio_2022", "sf_share",
            "capacity6_per_1k", "permits1825_per_1k", "permits1825_mf_per_1k",
            "adu_share_1825", "hqta_share", "hra_share"]
    t = pd.DataFrame({name: r[cols],
                      "county median": DF[DF.county == r.county][cols].median(),
                      "region median": DF[cols].median()}).round(2)
    st.dataframe(t, width='stretch')


def page_hypotheses():
    st.header("Hypothesis tests (mirrors notebook §7)")

    st.subheader("H1 · The (flat) gradient: capacity vs transit access")
    hi_d = DF[DF["D_demand"] > DF["D_demand"].median()].copy()
    hi_d["transit"] = np.where(hi_d["hqta_share"] > DF["hqta_share"].median(),
                               "transit-rich", "transit-poor")
    st.dataframe(hi_d.groupby("transit")[
        ["capacity5_per_1k", "capacity6_per_1k", "sf_share"]].median().round(1))
    a = hi_d.loc[hi_d.transit == "transit-rich", "capacity5_per_1k"].dropna()
    b = hi_d.loc[hi_d.transit == "transit-poor", "capacity5_per_1k"].dropna()
    _, p = sps.mannwhitneyu(a, b, alternative="less")
    rho, prho = sps.spearmanr(DF["hqta_share"], DF["capacity5_per_1k"], nan_policy="omit")
    st.markdown(f"""Strong form ("transit-rich zones *less*") — **rejected** (Mann-Whitney p={p:.2f}).
What holds is a **flat gradient**: Spearman ρ = {rho:+.2f} (p={prho:.2f}) across all 109 —
high-access places hold **no more** zoned capacity than low-access ones, even though every regional
plan directs growth to transit. The flatness *is* the mismatch; SB 79 targets exactly this margin.""")

    st.subheader("H2 · Decoupling: which capacity predicts actual permits?")
    rows = []
    for cap, lab in [("capacity5_per_1k", "5th cycle (pre-mandate)"),
                     ("capacity6_per_1k", "6th cycle (state-mandated)")]:
        for out, olab in [("permits1825_per_1k", "all units"),
                          ("permits1825_mf_per_1k", "multifamily")]:
            d = DF[["zhvi_latest", cap, out]].dropna()
            z = lambda s: (s - s.mean()) / s.std()
            X = pd.DataFrame({"value": z(np.log(d["zhvi_latest"])),
                              "capacity": z(np.log1p(d[cap]))})
            X["value × capacity"] = X["value"] * X["capacity"]
            r = sm.OLS(np.log1p(d[out]), sm.add_constant(X)).fit()
            rows.append({"capacity vintage": lab, "outcome": olab,
                         "capacity coef": round(r.params["capacity"], 3),
                         "p": round(r.pvalues["capacity"], 3),
                         "value×cap coef": round(r.params["value × capacity"], 3),
                         "p ": round(r.pvalues["value × capacity"], 3),
                         "R²": round(r.rsquared, 3)})
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    st.markdown("""Pre-mandate capacity predicts a decade of permitting; mandated capacity does not
(the vintages correlate at only +0.33). On the **multifamily** outcome the Built-Out-Cities
*value × capacity* interaction replicates (p≈.001): zoned room matters most where prices are high.
**A compliant sites inventory is no longer evidence a city will deliver** — track conversion.""")
    d = DF.dropna(subset=["capacity5_per_1k", "capacity6_per_1k"])
    fig = px.scatter(d, x="capacity5_per_1k", y="capacity6_per_1k", log_x=True, log_y=True,
                     color="zhvi_latest", color_continuous_scale="plasma",
                     hover_name="jurisdiction", height=480,
                     labels={"capacity5_per_1k": "5th-cycle capacity /1k hh",
                             "capacity6_per_1k": "6th-cycle capacity /1k hh",
                             "zhvi_latest": "home value $"},
                     title="The state-mandated rezoning wave (everything above the 45° line)")
    lim = [d["capacity5_per_1k"].min() * 0.9, d["capacity6_per_1k"].max() * 1.1]
    fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines",
                             line=dict(dash="dash", color="gray"), showlegend=False))
    st.plotly_chart(fig, width='stretch')

    st.subheader("H3 · Equity: who gets the below-moderate homes?")
    df2 = DF.copy()
    df2["resource"] = np.where(df2["hra_share"] > df2["hra_share"].median(),
                               "High-resource", "Other")
    df2["mismatch"] = np.where(df2["zmi_core"] > df2["zmi_core"].median(),
                               "high ZMI", "low ZMI")
    g = df2.groupby(["resource", "mismatch"])
    t = pd.DataFrame({
        "n": g.size(),
        "RHNA share below-mod": (g[["rhna_very_low", "rhna_low"]].sum().sum(axis=1)
                                 / g["rhna_total"].sum()),
        "permit share below-mod": ((g["permits1825_vlow"].sum() + g["permits1825_low"].sum())
                                   / g["permits1825_total"].sum()),
        "low-inc RHNA progress 23-25": (g[["permits2325_vlow", "permits2325_low"]].sum().sum(axis=1)
                                        / g[["rhna_very_low", "rhna_low"]].sum().sum(axis=1)),
    }).round(3)
    st.dataframe(t, width='stretch')
    st.markdown("""Need shares are equal on paper (~41% below-moderate everywhere — ABAG's equity
adjustment works). Delivery is not: **high-resource jurisdictions run ~35% slower on low-income
RHNA** (0.12 vs 0.18). The equity gap operates through *total volume*, not just the affordable
share — the AFFH reading of the index.""")

    st.subheader("Permits vs need, by income band (region)")
    bands = pd.DataFrame({
        "RHNA need share": (DF[["rhna_very_low", "rhna_low", "rhna_moderate",
                                "rhna_above_moderate"]].sum()
                            / DF["rhna_total"].sum()).values,
        "Permitted share 2018-25": (DF[["permits1825_vlow", "permits1825_low",
                                        "permits1825_mod", "permits1825_above"]].sum()
                                    / DF["permits1825_total"].sum()).values,
    }, index=["Very low", "Low", "Moderate", "Above moderate"])
    fig = px.bar(bands, barmode="group", height=380,
                 color_discrete_sequence=["#356f9f", "#c1443c"])
    fig.update_layout(yaxis_tickformat=".0%", legend_title=None)
    st.plotly_chart(fig, width='stretch')


def page_sb79():
    st.header("SB 79 — the state override, effective 2026-07-01")
    st.markdown("""[SB 79](https://www.hklaw.com/en/insights/publications/2025/12/californias-2026-housing-laws-what-you-need-to-know)
overrides local zoning near major transit (tiered heights/densities). MTC published **draft tier
maps in April 2026**; crossing them with current zoning gives a forward-looking exposure measure:
**`sb79_exposure` = (land share inside SB 79 tiers) × (single-family-only land share)** — how much
transit-adjacent land is currently locked to single-family uses.""")
    d = DF[DF["sb79_share"] > 0]
    c1, c2 = st.columns([2, 3])
    with c1:
        st.dataframe(d.nlargest(15, "sb79_exposure")[
            ["jurisdiction", "county", "sb79_share", "sb79_tier1_share",
             "sf_share", "sb79_exposure", "zmi_core"]].round(3),
            hide_index=True, height=560)
    with c2:
        fig = px.scatter(d, x="sb79_share", y="sf_share", size="rhna_total",
                         color="zmi_core", color_continuous_scale="RdYlGn_r",
                         hover_name="jurisdiction", height=560,
                         labels={"sb79_share": "land share in draft SB 79 tiers",
                                 "sf_share": "single-family-only share"},
                         title="Where the override meets single-family zoning")
        st.plotly_chart(fig, width='stretch')
    st.caption(f"{len(d)}/109 jurisdictions are touched by the draft tiers. "
               "Draft MTC data — tiers may change before final rules.")


def page_simulator():
    st.header("Rezoning scenario simulator")
    st.markdown("Change one jurisdiction's zoning inputs and recompute the **whole index** "
                "(z-scores are relative, so everyone's score can shift). The **Save** button "
                "creates a scenario record — the same operation as the REST API's "
                "`POST /scenarios`.")
    name = st.selectbox("Jurisdiction", sorted(DF["jurisdiction"]))
    r = DF[DF["jurisdiction"] == name].iloc[0]
    c1, c2 = st.columns(2)
    add_cap = c1.slider("Add zoned capacity (units per 1k households)", 0, 500, 100, 10)
    mf = c2.slider("Multifamily-allowed land share", 0.0, 1.0,
                   float(round(r.mf_allowed_share, 2)), 0.01)
    res = core.simulate(DF, r.key, add_capacity_per_1k=add_cap, mf_allowed_share=mf)
    c = st.columns(4)
    c[0].metric("ZMI before", f"{res['zmi_before']:+.2f}")
    c[1].metric("ZMI after", f"{res['zmi_after']:+.2f}", f"{res['zmi_delta']:+.2f}",
                delta_color="inverse")
    c[2].metric("Mismatch rank before", f"{res['rank_before']}/109",
                help="Rank 1 = most blocked, 109 = least blocked")
    moved = res["rank_after"] - res["rank_before"]
    c[3].metric("Mismatch rank after", f"{res['rank_after']}/109",
                f"{moved:+d} places {'less' if moved >= 0 else 'MORE'} blocked",
                delta_color="normal")
    st.caption("Rank 1 = the most blocked jurisdiction (highest demand relative to legal "
               "capacity). Adding capacity or multifamily-allowed land moves a city *away* "
               "from rank 1 — a green arrow means the simulated reform reduces its mismatch.")
    note = st.text_input("Note (stored with the scenario)", "")
    if st.button("💾 Save scenario (POST /scenarios)"):
        rec = core.save_scenario({**res, "note": note})
        st.success(f"saved as scenario #{rec['id']}")
    saved = core.list_scenarios()
    if saved:
        with st.expander(f"Saved scenarios ({len(saved)})"):
            st.dataframe(pd.json_normalize(saved), width='stretch', hide_index=True)


def page_data():
    st.header("Data & methodology")
    st.markdown("""**Pipeline** (all public sources, all scripted): `src/ingest_v3.py` (MTC/ABAG
ArcGIS layers, RHNA PDF, Zillow, LODES, ACS via censusreporter, Terner PDFs) →
`src/ingest_sites6.py` (HCD/DGS statewide 6th-cycle sites inventory) → `src/assemble_v3.py`
(109 × 92 master table + pillars + ZMI). Full report: `ZMI_Bay_Area.ipynb`.

| Source | Contribution | Vintage |
|---|---|---|
| HCD Annual Progress Reports (Table A2, project-level) | permits by income band & structure | 2018–2025 |
| HCD/DGS statewide sites inventory (Tables A/B) | 6th-cycle zoned capacity | 2023–31 |
| MTC 5th-cycle sites inventory | pre-mandate capacity | 2015–23 |
| ABAG Final RHNA Plan (PDF, incl. Solano subregion) | need by income band | 2023–31 |
| OBI parcel zoning (9 counties) | single-family-only share | 2020 |
| NZLUD (Mleczko–Desmond) | friction (36/109) | 2018–21 |
| Zillow ZHVI/ZORI · ACS · LODES | prices, demographics, jobs | 2022–latest |
| MTC growth geographies / HQTA / TPA / EPC / **draft SB 79 tiers** | geography shares | 2020–2026 |

**Index.** Pillars are means of winsorized z-scores (p5/p95): D = {jobs/unit, ZORI, ZHVI, HQTA
share}; C = {6th-cycle capacity per 1k hh, MF-allowed share}; `ZMI = z(D) − z(C)`; friction (F,
NZLUD) reported separately, never silently imputed. Equal weights vs PCA weights: rank ρ = 0.82.

**Known limitations.** Self-reported APR & sites data; APR counts ADUs and SF rebuilds as units
(see "the ADU mask"); 10 jurisdictions' capacity imputed (flagged in `capacity_vintage`); NZLUD
covers 36/109; Zillow rents missing for small cities; jurisdiction-level only — no parcel-level or
causal claims.""")
    st.subheader("Descriptive statistics")
    desc_cols = {
        'jh_ratio_2022': 'jobs per housing unit', 'zhvi_latest': 'home value, $',
        'zori_latest': 'market rent, $/mo', 'acs_med_income': 'median income, $',
        'permits1825_per_1k': 'permits 2018-25 per 1k hh',
        'capacity6_per_1k': 'zoned capacity per 1k hh',
        'rhna_per_1k': 'RHNA per 1k hh', 'sf_share': 'single-family-only share',
    }
    d = DF[list(desc_cols)].describe().T
    d['median'] = DF[list(desc_cols)].median()
    d = d[['count', 'mean', 'median', 'std', 'min', 'max']].round(2)
    d.index = [f'{k} — {v}' for k, v in desc_cols.items()]
    st.dataframe(d, width='stretch')

    st.subheader("Correlation structure")
    hm_cols = ['zmi_core', 'D_demand', 'C_capacity', 'permits1825_per_1k', 'permits1825_mf_per_1k',
               'capacity6_per_1k', 'capacity5_per_1k', 'sf_share', 'zhvi_latest', 'jh_ratio_2022',
               'hqta_share', 'hra_share', 'sb79_share', 'rhna_per_1k', 'rhna6_progress']
    corr = DF[hm_cols].corr(method='spearman')
    fig = px.imshow(corr, color_continuous_scale='RdBu_r', zmin=-1, zmax=1, aspect='auto',
                    text_auto='.2f', height=560, title="Spearman correlations of the core indicators")
    fig.update_traces(textfont_size=9)
    st.plotly_chart(fig, width='stretch')

    with st.expander("Missingness audit"):
        miss = DF.isna().sum()
        st.dataframe(miss[miss > 0].sort_values(ascending=False).rename("n_missing"))
    st.markdown("**REST API** (run `uvicorn app.api:app`): "
                "`GET /jurisdictions?county=Santa+Clara&min_zmi=1&sort=zmi_core&limit=10` · "
                "`GET /jurisdictions/Palo Alto` · `POST /scenarios` "
                '`{"jurisdiction": "Palo Alto", "add_capacity_per_1k": 200}` · interactive docs at `/docs`.')


PAGES = {
    "Overview": page_overview,
    "Map & rankings": page_map,
    "Jurisdiction profile": page_profile,
    "Hypotheses & validation": page_hypotheses,
    "SB 79 exposure": page_sb79,
    "Scenario simulator": page_simulator,
    "Data & methodology": page_data,
}
choice = st.sidebar.radio("Pages", list(PAGES))
st.sidebar.markdown(
    "---\n*[Report notebook](https://github.com/anoise1/bay-area-zmi/blob/main/ZMI_Bay_Area.ipynb)"
    " · [data & code](https://github.com/anoise1/bay-area-zmi) · 109 jurisdictions*")
PAGES[choice]()
