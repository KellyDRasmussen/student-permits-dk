import requests
import pandas as pd
import io
import os

API_URL = "https://api.statbank.dk/v1/data"
STUDY_CODES = ["10", "101", "102", "103"]
ANNUAL_YEARS = [str(y) for y in range(2021, 2024)]   # 2021-2023
MONTHLY_PERIODS = (
    [f"2024M{m:02d}" for m in range(1, 13)] +
    [f"2025M{m:02d}" for m in range(1, 13)] +
    [f"2026M{m:02d}" for m in range(1, 6)]
)


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
