import requests
import pandas as pd
import io
import os
from datetime import date

API_URL = "https://api.statbank.dk/v1/data"
STUDY_CODES = ["10", "101", "102", "103"]

MONTHLY_START_YEAR = 2024
MONTHLY_START_MONTH = 1


def _latest_available_month(today=None):
    # Statistics Denmark publishes VAN77M for month M roughly 3 weeks after
    # month end, so the newest safely-available month is last month.
    today = today or date.today()
    year, month = today.year, today.month - 1
    if month == 0:
        year, month = year - 1, 12
    return year, month


def _month_range(start_year, start_month, end_year, end_month):
    periods = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        periods.append(f"{y}M{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return periods


_END_YEAR, _END_MONTH = _latest_available_month()
ANNUAL_YEARS = [str(y) for y in range(2021, _END_YEAR)]  # full completed years only
MONTHLY_PERIODS = _month_range(MONTHLY_START_YEAR, MONTHLY_START_MONTH, _END_YEAR, _END_MONTH)


def _get(table, variables):
    payload = {
        "table": table,
        "format": "BULK",
        "lang": "en",
        "variables": variables,
    }
    r = requests.post(API_URL, json=payload)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep=";")
    df = df[df["STATSB"] != "Total"]
    df["INDHOLD"] = pd.to_numeric(df["INDHOLD"], errors="coerce").fillna(0).astype(int)
    return df


def fetch_annual():
    return _get("VAN66", [
        {"code": "STATSB", "values": ["*"]},
        {"code": "OPHOLD", "values": STUDY_CODES},
        {"code": "Tid", "values": ANNUAL_YEARS},
    ])


def fetch_monthly():
    return _get("VAN77M", [
        {"code": "STATSB", "values": ["*"]},
        {"code": "OPHOLD", "values": STUDY_CODES},
        {"code": "Tid", "values": MONTHLY_PERIODS},
    ])


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    print("Fetching VAN66 (annual 2021-2025)...")
    annual = fetch_annual()
    annual.to_csv("data/van66_raw.csv", index=False)
    print(f"Saved {len(annual)} rows to data/van66_raw.csv")

    print("Fetching VAN77M (monthly Jan 2024-May 2026)...")
    monthly = fetch_monthly()
    monthly.to_csv("data/van77m_raw.csv", index=False)
    print(f"Saved {len(monthly)} rows to data/van77m_raw.csv\n")

    totals = annual.groupby("STATSB")["INDHOLD"].sum().sort_values(ascending=False)
    print("Top 20 countries by total annual study permits (2021-2025):")
    print(totals.head(20).to_string())
