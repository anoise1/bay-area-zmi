# Bay Area Zoning Mismatch Index (ZMI)

**Where the region needs homes vs. what local rules allow — and what 2018–2025 permit data
reveals.** DSBA 2025/26 Python Programming course project (pilot track) by Andrew Shumilo.

**▶ Live app: [bay-area-zmi.streamlit.app](https://bay-area-zmi.streamlit.app)**

For each of the **109 Bay Area jurisdictions**, the ZMI compares a *Demand* pillar (jobs per
housing unit, Zillow values & rents, high-quality-transit coverage) against a *Capacity* pillar
(6th-cycle zoned site capacity per household, multifamily-allowed land share):
`ZMI = z(Demand) − z(Capacity)`. High ZMI = housing is wanted there and the rules don't allow it.
Validated against HCD permit data; extended with friction (NZLUD), income bands, equity overlays,
and MTC's April-2026 **draft SB 79** transit-override tiers.

**Headline findings**
1. *The ADU mask* — the most-blocked towns look productive in headline permit counts, but 54% of
   their permits are ADUs; their multifamily permitting is ~1.4 units per 1k households over eight
   years (11× below the most-open group).
2. *Decoupling* — pre-mandate (5th-cycle) zoned capacity predicts 2018-25 permits (p=.003); the new
   state-mandated 6th-cycle capacity predicts nothing (vintage correlation just +0.33). On the
   multifamily margin the Built-Out-Cities value×capacity interaction replicates (p=.001).
3. *The flat gradient* — zoned capacity is uncorrelated with transit access (ρ≈−0.08): the region
   plans transit-oriented growth its zoning never made legal. SB 79 targets exactly this margin.
4. *Equity runs through volume* — need shares are equal (~41% below-moderate everywhere) but
   high-resource jurisdictions deliver low-income RHNA ~35% slower.

## Contents

| Artifact | What |
|---|---|
| `ZMI_Bay_Area.ipynb` | the full report notebook (executed; regenerate via `src/build_notebook.py`) |
| `data/processed/bay_area_zmi_v3.csv` | the master dataset, 109 × 92 |
| `streamlit_app.py` | interactive web app (map, profiles, hypotheses, SB 79, simulator) |
| `app/api.py` | REST API (FastAPI) |
| `src/` | full data pipeline (every byte from public sources) |
| `docs/METHODOLOGY.md` | index definition, sources, data access, limitations |

## Run

```bash
pip install -r requirements.txt

# the web app
streamlit run streamlit_app.py

# the REST API  ->  interactive docs at http://localhost:8000/docs
uvicorn app.api:app --port 8000
```

### REST API

```bash
# GET with filters / sorting / pagination
curl 'localhost:8000/jurisdictions?county=Santa%20Clara&min_zmi=1&sort=zmi_core&limit=5'
curl 'localhost:8000/jurisdictions/Palo%20Alto'

# POST — create a rezoning scenario (recomputes the whole index)
curl -X POST localhost:8000/scenarios -H 'Content-Type: application/json' \
  -d '{"jurisdiction": "Palo Alto", "add_capacity_per_1k": 200, "mf_allowed_share": 0.5}'
curl localhost:8000/scenarios
```

### Rebuild the data from scratch

```bash
python src/ingest_v3.py       # MTC/ABAG layers, RHNA PDF, Zillow, LODES, ACS, Terner
python src/ingest_sites6.py   # HCD/DGS statewide 6th-cycle sites inventory
python src/assemble_v3.py     # 109x92 master table + pillars + ZMI
python src/build_notebook.py && jupyter nbconvert --to notebook --execute --inplace ZMI_Bay_Area.ipynb
```

`data/raw/` (~600 MB) is git-ignored; the `src/` scripts fetch the sources — see
`docs/METHODOLOGY.md` for where each dataset comes from.

## Deploy

**Web app (Streamlit Community Cloud):** [share.streamlit.io](https://share.streamlit.io) →
*New app* → pick this repo/branch → main file `streamlit_app.py` → Deploy. Set the app to public
in *Settings → Sharing*. Live: https://bay-area-zmi.streamlit.app

**REST API (optional, Render free tier):** the repo includes `render.yaml`, so at
[dashboard.render.com](https://dashboard.render.com) → *New → Blueprint* → connect this repo, the
API deploys itself with interactive docs at `/docs`. (Locally it runs the same way:
`uvicorn app.api:app --port 8000`.)

## Data sources

ABAG RHNA Final Plan · HCD Annual Progress Reports · HCD/DGS statewide sites inventory ·
MTC/ABAG Open Data (growth geographies, transit layers, EPCs, draft SB 79 tiers) · OBI Bay Area
zoning · NZLUD (Mleczko & Desmond) · Zillow Research · ACS (censusreporter) · LEHD LODES ·
Terner Center reports. Full citations in the notebook §10.
