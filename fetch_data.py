import requests
import pandas as pd
import io
import os

API_URL = "https://api.statbank.dk/v1/data"
STUDY_CODES = ["10", "101", "102", "103"]

ANNUAL_START_YEAR = 2021
MONTHLY_START_PERIOD = "2024M01"


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
    # "*" pulls every year Statbank has published; trim to the window we care about
    # so we don't drag in decades of history we never use.
    df = _get("VAN66", [
        {"code": "STATSB", "values": ["*"]},
        {"code": "OPHOLD", "values": STUDY_CODES},
        {"code": "Tid", "values": ["*"]},
    ])
    return df[df["TID"] >= ANNUAL_START_YEAR]


def fetch_monthly():
    # "*" self-corrects to whatever's actually published, whatever Statbank's
    # real lag turns out to be, rather than guessing a fixed offset from today.
    df = _get("VAN77M", [
        {"code": "STATSB", "values": ["*"]},
        {"code": "OPHOLD", "values": STUDY_CODES},
        {"code": "Tid", "values": ["*"]},
    ])
    return df[df["TID"] >= MONTHLY_START_PERIOD]


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
