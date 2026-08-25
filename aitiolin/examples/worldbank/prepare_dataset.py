"""Rebuild the World Bank / Our World in Data health-spending-vs-child-mortality
example dataset from live OWID sources.

Produces the same two files already checked into this folder:
  - worldbank_health_mortality_panel.csv   (country-year panel, 2000-2021)
  - worldbank_health_mortality_2019.csv    (single-year cross-section snapshot)

Run from anywhere with the project's Python environment:
    python prepare_dataset.py

Requires: pandas and network access to ourworldindata.org (no API key needed).
Uses only the Python standard library for the HTTP fetch, so no extra
dependency beyond what the Django backend already installs.
"""

import urllib.request
from io import StringIO

import pandas as pd

OWID_MORTALITY_VS_HEALTH_EXP = "https://ourworldindata.org/grapher/child-mortality-vs-health-expenditure.csv"
OWID_HEALTH_EXP_VS_GDP = "https://ourworldindata.org/grapher/healthcare-expenditure-vs-gdp.csv"

COUNTRY_CODE_PATTERN = r"^[A-Z]{3}$"


def _fetch_csv(url: str) -> pd.DataFrame:
    with urllib.request.urlopen(url, timeout=30) as response:
        content = response.read().decode("utf-8")
    return pd.read_csv(StringIO(content))


def _is_country(data_frame: pd.DataFrame) -> pd.Series:
    # OWID mixes in continents/income groups/"World" as pseudo-entities with no
    # (or non-standard) ISO3 code; keep only rows with a real 3-letter code.
    return data_frame["Code"].astype(str).str.match(COUNTRY_CODE_PATTERN, na=False)


def build_panel() -> pd.DataFrame:
    mortality = _fetch_csv(OWID_MORTALITY_VS_HEALTH_EXP).rename(
        columns={
            "Child mortality": "child_mortality_rate",
            "Current health expenditure per capita, PPP": "health_expenditure_per_capita",
            "Population": "population",
            "World region according to OWID": "region",
        }
    )
    gdp = _fetch_csv(OWID_HEALTH_EXP_VS_GDP).rename(
        columns={
            "Current health expenditure per capita (int-$)": "health_expenditure_per_capita_alt",
            "GDP per capita": "gdp_per_capita",
        }
    )

    mortality = mortality[_is_country(mortality)]
    gdp = gdp[_is_country(gdp)]

    merged = pd.merge(
        mortality[
            [
                "Entity",
                "Code",
                "Year",
                "child_mortality_rate",
                "health_expenditure_per_capita",
                "population",
                "region",
            ]
        ],
        gdp[["Entity", "Code", "Year", "gdp_per_capita", "health_expenditure_per_capita_alt"]],
        on=["Entity", "Code", "Year"],
        how="outer",
    )

    merged["health_expenditure_per_capita"] = merged["health_expenditure_per_capita"].fillna(
        merged["health_expenditure_per_capita_alt"]
    )
    merged = merged.drop(columns=["health_expenditure_per_capita_alt"])
    merged = merged.rename(columns={"Entity": "country", "Code": "country_code", "Year": "year"})

    # 2000-2021 keeps broad, fairly complete coverage across the three core series.
    merged = merged[(merged["year"] >= 2000) & (merged["year"] <= 2021)]
    merged = merged.sort_values(["country", "year"]).reset_index(drop=True)

    # Two-year lag: this year's mortality paired with health spending two years
    # earlier, for anyone who wants to test a lagged-effect hypothesis instead of
    # assuming spending and mortality move together in the same year.
    merged["health_expenditure_per_capita_lag2"] = merged.groupby("country")[
        "health_expenditure_per_capita"
    ].shift(2)

    return merged[
        [
            "country",
            "country_code",
            "year",
            "region",
            "population",
            "gdp_per_capita",
            "health_expenditure_per_capita",
            "health_expenditure_per_capita_lag2",
            "child_mortality_rate",
        ]
    ]


def build_snapshot(panel: pd.DataFrame, year: int = 2019) -> pd.DataFrame:
    snapshot = panel[panel["year"] == year].drop(columns=["health_expenditure_per_capita_lag2"])
    snapshot = snapshot.dropna(
        subset=["gdp_per_capita", "health_expenditure_per_capita", "child_mortality_rate"]
    )
    return snapshot.reset_index(drop=True)


if __name__ == "__main__":
    panel_df = build_panel()
    panel_df.to_csv("worldbank_health_mortality_panel.csv", index=False)
    print(f"Wrote worldbank_health_mortality_panel.csv: {panel_df.shape}")

    snapshot_df = build_snapshot(panel_df)
    snapshot_df.to_csv("worldbank_health_mortality_2019.csv", index=False)
    print(f"Wrote worldbank_health_mortality_2019.csv: {snapshot_df.shape}")
