# Data dictionary — `bay_area_zmi_v3.csv`

109 rows (one per San Francisco Bay Area jurisdiction: 101 cities/towns + 8 unincorporated
county areas) × 92 columns, assembled from 12 public sources. A companion file,
`apr_permits_by_year.csv`, holds the same permit data in long format (one row per
jurisdiction-year, 2018–2025).

## Identifiers & keys
| Column | Description |
|---|---|
| `jurisdiction` | City, town, or unincorporated-area name |
| `county` | County name |
| `fipst`, `fipco`, `place_fips`, `place_fips5` | Census FIPS codes (state / county / place) |
| `key` | Normalized join key used to merge all sources |
| `acs_geo` | `place` if ACS values are city-level, `county_proxy` for unincorporated areas |
| `capacity_vintage` | Source of the 6th-cycle capacity: `6th_cycle`, `apr_tableC_2023plus`, or `5th_cycle_fallback` (for the 10 jurisdictions absent from the state file) |

## Size & context (MTC, 2020)
| Column | Description |
|---|---|
| `jobs_2020`, `households_2020`, `pop_2020` | Jobs, households, population |
| `jh_ratio_2020`, `jh_ratio_2022` | Jobs per housing unit |
| `jobs_2022`, `workers_2022` | Jobs (workplace) and resident workers, LODES 2022 |

## Housing need — RHNA 2023–2031 (ABAG)
| Column | Description |
|---|---|
| `rhna_very_low`, `rhna_low`, `rhna_moderate`, `rhna_above_moderate`, `rhna_total` | Housing units the jurisdiction must plan for, by income band |
| `rhna_per_1k` | RHNA total per 1,000 households |

## Production / permits (HCD Annual Progress Reports)
| Column | Description |
|---|---|
| `permits1417_*` | Units permitted 2014–2017 (MTC), by income band |
| `permits1825_vlow/low/mod/above/total` | Units permitted 2018–2025, by income band |
| `permits2325_total/vlow/low` | Units permitted 2023–2025 (6th cycle to date) |
| `permits1825_adu/mf24/mf5/sf` | Units permitted 2018–2025 by structure: ADU, 2–4 units, 5+ units, single-family |
| `permits1825_per_1k` | Total permits per 1,000 households |
| `permits1825_mf_per_1k` | Multifamily (2+ unit) permits per 1,000 households |
| `permits1825_belowmod_per_1k` | Below-moderate-income permits per 1,000 households |
| `adu_share_1825` | ADU share of all 2018–2025 permits |
| `rhna6_progress`, `rhna6_lowinc_progress` | Share of 6th-cycle RHNA permitted so far (overall / low-income) |

## Zoned capacity — two eras (HCD/DGS & MTC sites inventories)
| Column | Description |
|---|---|
| `capacity5_units`, `density5_mean`, `n_sites5`, `capacity5_per_1k` | 5th-cycle (2015–23 elements): zoned "realistic capacity", mean allowed density, site count, per 1k hh |
| `capacity6_units`, `capacity6_lower`, `density6_mean`, `n_sites6`, `capacity6_per_1k` | 6th-cycle (2023–31 elements): same measures |
| `sites6_vacant_share` | Share of 6th-cycle sites that are vacant |
| `capacity6_rezone_units` | Capacity on sites flagged for rezoning |
| `cap_ratio_6_to_5` | 6th-cycle ÷ 5th-cycle capacity per 1k (rezoning intensity) |
| `capacity_vs_rhna` | 6th-cycle capacity ÷ RHNA total |

## Zoning composition (Othering & Belonging Institute, parcel-level)
| Column | Description |
|---|---|
| `sf_share` | Share of residential land zoned single-family-only |
| `mf_share`, `mf_allowed_share` | Share allowing multifamily (1 − `sf_share`) |

## Prices (Zillow)
| Column | Description |
|---|---|
| `zhvi_latest`, `zhvi_yoy` | Typical home value ($) and year-over-year change |
| `zori_latest`, `zori_yoy` | Typical market rent ($/mo) and year-over-year change |

## Demographics (American Community Survey)
| Column | Description |
|---|---|
| `acs_units` | Housing units |
| `acs_med_income`, `acs_med_rent`, `acs_med_value` | Median household income, gross rent, home value |
| `acs_owner_share`, `acs_poc_share` | Owner-occupied share, people-of-color share |

## Regulatory friction (NZLUD — Mleczko & Desmond; covers 36/109)
| Column | Description |
|---|---|
| `nzlud_zri` | Zoning restrictiveness index |
| `nzlud_parking`, `nzlud_minlot`, `nzlud_adu_allowed`, `nzlud_mf_permitted`, `nzlud_approval_steps` | Parking minimums, minimum lot size, ADU allowance, multifamily-permitted measure, approval steps |

## Geography overlays (MTC — share of jurisdiction land)
| Column | Description |
|---|---|
| `sb79_share`, `sb79_tier1_share` | Share of land in draft SB 79 transit tiers (all / Tier 1) |
| `tpa_share`, `hqta_share` | Share in transit priority areas / high-quality transit areas |
| `hra_share`, `tra_share` | Share in high-resource areas / transit-rich areas |
| `epc_share` | Share in equity priority communities |

## The index (derived; all pillars are winsorized z-scores across the 109 jurisdictions)
| Column | Description |
|---|---|
| `D_demand` | Demand pillar (jobs/housing, prices, transit access) |
| `C_capacity`, `C_capacity_5th` | Legal-capacity pillar (6th-cycle / 5th-cycle) |
| `F_friction`, `F_coverage` | Friction pillar (NZLUD); `F_coverage` flags whether friction data exists |
| `P_delivery` | Delivery pillar (permits per 1k) |
| **`zmi_core`** | **The Zoning Mismatch Index = z(Demand) − z(Capacity).** Higher = more housing wanted than zoning allows |
| `zmi_full` | `zmi_core` plus the friction pillar |
| `zmi_realized` | z(Demand) − z(Delivery) |
| `zmi_core_5th` | Era-matched variant using 5th-cycle capacity |

## Notes on coverage
NZLUD friction columns cover 36/109 jurisdictions; Zillow rent (`zori_*`) 82/109 and value
(`zhvi_*`) 100/109 (small towns aren't published); LODES jobs 101/109. The 10 jurisdictions
missing from the state's 6th-cycle file are imputed and flagged in `capacity_vintage`. No rows
are dropped; true unknowns are left blank.
