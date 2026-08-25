# World Bank / Our World in Data: health spending vs. child mortality

Example dataset for the causal question **"Does health expenditure actually reduce
child mortality, or is the correlation just because richer countries spend more
and have lower mortality for unrelated reasons?"** — see the use-case design this
folder implements for the full background, DAG, and expected app walkthrough.

## Files

| File | Shape | Use it for |
|---|---|---|
| `worldbank_health_mortality_2019.csv` | 186 countries x 8 columns, single year | The quick path: upload -> agent profile/clean/model/estimate/compare in one sitting. |
| `worldbank_health_mortality_panel.csv` | 4,604 rows (country x year, 2000-2021) x 9 columns | Everything above, plus **Time Series mode** (`entity_column = country`, `time_column = year`) to see whether the spending-mortality relationship has strengthened or weakened over time. |
| `prepare_dataset.py` | - | Regenerates both CSVs from live OWID data. Only needs `pandas` (already a backend dependency) - no API key, no extra packages. Run with `python prepare_dataset.py`. |

## Columns

| Column | Meaning | Role in the causal question |
|---|---|---|
| `country` / `country_code` | Country name / ISO3 code | Identifier - not a causal variable. The agent's profiler flags both as `id_like_column` and the cleaning plan proposes dropping them (each has one unique value per row). |
| `year` | Calendar year | Constant within the 2019 snapshot (flagged `constant_column` there, correctly proposed for dropping); a real time axis in the panel file. |
| `region` | OWID world region | Optional grouping variable. |
| `population` | Total population | Context / potential confounder; heavy-tailed (a few very large countries), so the cleaning plan proposes capping outliers. |
| `gdp_per_capita` | GDP per capita, PPP-adjusted int-$ | **Confounder** - richer countries both spend more on health and have lower mortality through unrelated channels (nutrition, sanitation, education). This is the variable identification analysis should place in the backdoor adjustment set. |
| `health_expenditure_per_capita` | Health spending per capita, PPP int-$ | **Treatment.** |
| `health_expenditure_per_capita_lag2` | Same, shifted 2 years per country (panel file only) | Optional alternate treatment for testing a lagged-effect hypothesis instead of assuming same-year causation. |
| `child_mortality_rate` | Under-5 deaths per 1,000 live births | **Outcome.** |

## Suggested walkthrough in the app

1. Upload `worldbank_health_mortality_2019.csv` from the Dataset sidebar.
2. **Causality Agent -> 1. Profile data.** Expect: `country`/`country_code` flagged
   as identifiers, `year` flagged constant, a couple of outlier warnings on
   `population` and `health_expenditure_per_capita`. GDP and health expenditure
   are correlated but not flagged as redundant (`collinear_pair` needs `|r| >=
   0.98`) - they're related, not duplicates, which is exactly the point.
3. **2. Suggest cleaning plan -> apply.** Accepts the identifier/constant-column
   drops; review the outlier-capping steps before accepting them.
4. **3. Suggest causal model.** With an `OPENAI_API_KEY` configured, the LLM
   should propose `gdp_per_capita` as a confounder into both
   `health_expenditure_per_capita` and `child_mortality_rate`. Without a key,
   the heuristic fallback has no name-pattern or binary-column signal to latch
   onto for this dataset (it's tuned for churn/marketing data), so it likely
   won't propose a treatment on its own - pick `health_expenditure_per_capita`
   as treatment and `child_mortality_rate` as outcome manually in Controls, and
   let the edge-verification/identification machinery run from there.
5. **Identification panel**: confirm `gdp_per_capita` appears in the adjustment
   set - if the effect is only identifiable through that backdoor path, that's
   the interesting result to report.
6. **Robustness dashboard**: compare the *adjusted* effect against the naive
   (no-adjustment) correlation. A placebo-treatment or random-common-cause
   refuter should move the naive estimate noticeably while leaving the adjusted
   one comparatively stable.
7. **Compare competing models**: the confounder-stressed variant is the natural
   "is this just a wealth effect in disguise?" test.
8. Switch to `worldbank_health_mortality_panel.csv` and try **Time Series
   mode** (`entity_column = country`, `time_column = year`) to see whether the
   edge strength is stable across the 2000-2021 window, or try
   `health_expenditure_per_capita_lag2` as treatment to test the lagged-effect
   hypothesis instead of same-year causation.

## Caveats to keep in front of anyone using this as a demo

- This is **country-year aggregate (ecological) data** - a country-level effect
  doesn't prove the same causal story holds for individual patients or
  households.
- Health spending isn't randomly assigned. Even after adjusting for GDP,
  unmeasured governance quality is a live confounder - a good moment to point
  at the agent's "possible unobserved confounder" hypothesis output.
- `child_mortality_rate` and `health_expenditure_per_capita` are missing for
  ~5-10% of country-years (smaller/lower-income countries with less complete
  reporting); the panel file keeps this missingness rather than
  pre-imputing it, so the agent's cleaning plan has real work to do.

## Source

- [Child mortality vs. health spending - Our World in Data](https://ourworldindata.org/grapher/child-mortality-vs-health-expenditure)
- [Healthcare spending vs. GDP per capita - Our World in Data](https://ourworldindata.org/grapher/healthcare-expenditure-vs-gdp)
- Underlying series: World Bank WDI `SH.DYN.MORT` (under-5 mortality), `SH.XPD.CHEX.PC.CD` / `SH.XPD.CHEX.PP.CD` (health expenditure per capita), `NY.GDP.PCAP.CD` (GDP per capita), via OWID's merged, pre-cleaned CSV exports (public domain / CC BY, no API key required).
