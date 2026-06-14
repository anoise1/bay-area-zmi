# Methodology & data notes

## The index

Unit of analysis: the 109 Bay Area jurisdictions (101 cities and towns + 8 unincorporated county
areas). All indicators are winsorized (5th/95th percentile) z-scores across jurisdictions.

| Pillar | Indicators |
|---|---|
| **D — Demand & suitability** | jobs per housing unit (LODES 2022 / ACS); Zillow home value (ZHVI) and market rent (ZORI); share of land in high-quality transit areas |
| **C — Legal capacity** | 6th-cycle sites-inventory "realistic capacity" per 1k households; multifamily-allowed share of residential land (1 − single-family-only share) |
| **F — Friction** (reported separately) | NZLUD parking minimums, minimum lot size, approval steps — available for 36/109 jurisdictions, never silently imputed |
| **P — Delivery** (outcome) | HCD APR permits 2018–2025 per 1k households, by income band and structure type |

**Scores:** `ZMI = z(D) − z(C)` (high = housing is wanted there and the rules don't allow it);
`zmi_full` adds F where available; `zmi_realized = z(D) − z(P)`. Equal pillar weights are checked
against PCA-derived weights (rank correlation 0.82). A 5th-cycle variant of C supports the
era-matched validation: pre-mandate capacity predicts 2018–25 permitting (p = .003), state-mandated
6th-cycle capacity does not, and on the multifamily outcome the value × capacity interaction is
strongly positive (p = .001) — consistent with Monkkonen–Lens–Manville's *Built-out cities?*.

**Prescriptions** are a transparent decision rule on the dominant adverse pillar:
low demand → don't force growth; capacity-bound → upzone (SB 9 / SB 79 territory);
friction-bound → fees/parking/ministerial approval; capacity present but unconverted → process
and feasibility. **SB 79 exposure** = (land share inside MTC's draft SB 79 transit tiers) ×
(current single-family-only share).

## Sources

| Source | Contributes | Vintage |
|---|---|---|
| [HCD Annual Progress Reports](https://data.ca.gov/dataset/housing-element-annual-progress-report-apr-data-by-jurisdiction-and-year), Table A2 | permits/entitlements/completions by income band & structure | 2018–2025 |
| HCD/DGS statewide sites inventory (Tables A & B) | 6th-cycle zoned capacity, density, vacancy | 2023–31 elements |
| [MTC Open Data](https://opendata.mtc.ca.gov/) sites inventory | 5th-cycle capacity | 2015–23 elements |
| [ABAG Final RHNA Plan](https://abag.ca.gov/our-work/housing/rhna-regional-housing-needs-allocation) | housing need by income band (sums to 441,176) | 2023–31 |
| [OBI Bay Area zoning](https://belonging.berkeley.edu/single-family-zoning-san-francisco-bay-area) (parcel shapefiles) | single-family-only land share | 2020 |
| [NZLUD](https://github.com/mtmleczko/nzlud) (Mleczko & Desmond) | regulatory friction | 2018–21 |
| [Zillow Research](https://www.zillow.com/research/data/) ZHVI/ZORI | values, rents | latest month |
| ACS via [censusreporter](https://censusreporter.org) | units, income, rent, tenure, race | 2022/2024 |
| [LEHD LODES 8](https://lehd.ces.census.gov/data/lodes/) | jobs & resident workers | 2022 |
| MTC: PBA50 growth geographies, HQ transit areas, TPAs, EPCs, **draft SB 79 tiers** | geography overlays | 2020–2026 |

## How 12 sources become one table

The build is four scripts run in order (commands in the README); conceptually it is nine steps:

1. **The spine.** Build the canonical list of 109 jurisdictions (101 cities + 8 unincorporated
   county areas) from MTC's jurisdiction layers, with a normalization key that reconciles every
   source's naming convention ("St. Helena"/"Saint Helena", "ALAMEDA COUNTY"/"Unincorporated
   Alameda"). Every later join uses this key; coverage is verified 109/109 at each step.
2. **Need.** Parse the RHNA 2023–31 allocation out of the official ABAG plan PDF — a two-column
   layout, with Solano County's eight sub-allocations recovered from an appendix (the county ran
   its own subregional process). Accept the extraction only when rows are internally consistent
   and the total equals the official 441,176.
3. **Production.** Aggregate the project-level APR ledger (Table A2, ~918k rows statewide,
   2018–2025) to jurisdiction-year: units permitted by income band (very-low → above-moderate)
   and by structure type (single-family, ADU, 2–4 units, 5+, mobile home).
4. **Capacity, two eras.** Aggregate the statewide 6th-cycle sites inventory (Tables A and B) to
   jurisdiction totals; for the 10 jurisdictions absent from the state file, impute from APR
   Table C rezone filings or 5th-cycle capacity, recording the source in `capacity_vintage`.
   Keep the 5th-cycle inventory as a separate column — the era-matched validation depends on it.
5. **Zoning.** Dissolve the OBI parcel shapefiles (all 9 counties) into each jurisdiction's
   single-family-only share of residential land.
6. **Markets & people.** Zillow ZHVI/ZORI by city; ACS housing units, income, rent, tenure and
   race (Census places, with county figures as flagged proxies for unincorporated areas);
   LODES 2022 jobs aggregated census-block → jurisdiction through the Census geography crosswalk.
7. **Friction.** NZLUD regulatory measures joined by place FIPS (available for 36/109 — reported
   separately, never imputed into the headline index).
8. **Geography.** In an equal-area projection, compute the share of each jurisdiction's land
   inside: the draft SB 79 transit tiers, high-quality transit areas, transit priority areas,
   PBA50 high-resource areas, and equity priority communities.
9. **Derived measures.** Per-1k-household ratios, winsorized z-scores (5th/95th pct), the D/C/F/P
   pillars, the ZMI variants — then write `bay_area_zmi_v3.csv` (109 × 92) and the long-format
   `apr_permits_by_year.csv`. Re-running the pipeline regenerates the CSV byte-identically.

## Data access

The pipeline (`src/ingest_v3.py`, `src/ingest_sites6.py`, `src/assemble_v3.py`) fetches the
sources and assembles the master table. Two inputs come straight from their official pages:

1. **HCD APR tables** (CSV) from the dataset page above → `data/raw/hcd_apr/`
2. *(optional)* **CTCAC/HCD Opportunity Map** from the
   [California Treasurer](https://www.treasurer.ca.gov/ctcac/opportunity.asp) → `data/raw/ctcac/`

The RHNA allocation is parsed from the official ABAG PDF (including the Solano subregion's
sub-allocations from the appendix) and is verified to sum to the regional determination exactly.

## Known limitations

APR and sites-inventory data are self-reported; APR unit counts include ADUs and single-family
rebuilds (the report's "ADU mask" section quantifies the distortion); 10 jurisdictions' 6th-cycle
capacity is imputed from APR Table C or 5th-cycle filings (flagged in `capacity_vintage`); NZLUD
covers 36/109 jurisdictions; Zillow rents are missing for small cities; vintages differ across
sources; all conclusions are jurisdiction-level.
