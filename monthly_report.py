"""
monthly_report.py — analyse latest student permit data and post to Slack.
Called by .github/workflows/monthly-refresh.yml after fetch_data.py runs.
"""

import os
from datetime import datetime

import pandas as pd
import requests

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Countries to spotlight in the "collateral damage" section
WATCH_LIST = ["Nepal", "Bangladesh", "China", "India", "Canada", "USA", "Pakistan", "Turkey"]

# G7 for a quick Western-country check
G7 = {"Canada", "France", "Germany", "Italy", "Japan", "United Kingdom", "USA"}


def month_label(code):
    year, m = code.split("M")
    return f"{MONTH_NAMES[int(m)-1]} {year}"


def year_ago(period_code):
    year, m = period_code.split("M")
    return f"{int(year)-1}M{m}"


def load_data():
    monthly = pd.read_csv("data/van77m_raw.csv")
    monthly["INDHOLD"] = pd.to_numeric(monthly["INDHOLD"], errors="coerce").fillna(0).astype(int)
    return monthly


def analyse(monthly):
    # All study types, summed by country + period
    agg = (
        monthly.groupby(["STATSB", "TID"])["INDHOLD"].sum()
        .reset_index()
        .rename(columns={"STATSB": "country", "TID": "period", "INDHOLD": "permits"})
    )

    # Education-only
    edu = (
        monthly[monthly["OPHOLD"] == "Study etc., education"]
        .groupby(["STATSB", "TID"])["INDHOLD"].sum()
        .reset_index()
        .rename(columns={"STATSB": "country", "TID": "period", "INDHOLD": "permits_edu"})
    )

    latest   = agg["period"].max()
    prev_yr  = year_ago(latest)
    prev_mth = sorted(agg["period"].unique())[-2] if len(agg["period"].unique()) > 1 else latest

    this   = agg[agg["period"] == latest].set_index("country")["permits"]
    last_y = agg[agg["period"] == prev_yr].set_index("country")["permits"]
    last_m = agg[agg["period"] == prev_mth].set_index("country")["permits"]

    this_edu   = edu[edu["period"] == latest].set_index("country")["permits_edu"]
    last_y_edu = edu[edu["period"] == prev_yr].set_index("country")["permits_edu"]

    # Year-on-year for countries that had ≥10 permits last year
    yoy = pd.DataFrame({"now": this, "last_year": last_y}).fillna(0)
    yoy["change"] = yoy["now"] - yoy["last_year"]
    last = yoy["last_year"].astype(float)
    yoy["pct"] = (yoy["change"].astype(float) / last.where(last > 0, 1.0) * 100).where(last > 0, 0.0).round(1)
    yoy_min10     = yoy[yoy["last_year"] >= 10]

    top5_now    = this.sort_values(ascending=False).head(5)
    big_drops   = yoy_min10.nsmallest(5, "pct")
    big_gains   = yoy_min10.nlargest(5, "pct")

    # Jan-to-date running totals (education-only, for press-release comparison)
    latest_year = latest[:4]
    prev_year   = str(int(latest_year) - 1)
    ytd_months  = [f"{latest_year}M{m:02d}" for m in range(1, int(latest[5:]) + 1)]
    ytd_prev    = [f"{prev_year}M{m:02d}" for m in range(1, int(latest[5:]) + 1)]

    ytd_edu_now  = edu[edu["period"].isin(ytd_months)].groupby("country")["permits_edu"].sum()
    ytd_edu_prev = edu[edu["period"].isin(ytd_prev)].groupby("country")["permits_edu"].sum()

    return {
        "latest": latest,
        "prev_yr": prev_yr,
        "prev_mth": prev_mth,
        "top5_now": top5_now,
        "big_drops": big_drops,
        "big_gains": big_gains,
        "this": this,
        "last_y": last_y,
        "this_edu": this_edu,
        "last_y_edu": last_y_edu,
        "ytd_edu_now": ytd_edu_now,
        "ytd_edu_prev": ytd_edu_prev,
        "latest_year": latest_year,
    }


def signed(n):
    return f"+{n:,.0f}" if n >= 0 else f"{n:,.0f}"

def pct_str(now, prev):
    if prev == 0:
        return "new" if now > 0 else "—"
    p = (now - prev) / prev * 100
    arrow = "▲" if p > 0 else "▼"
    return f"{arrow} {abs(p):.0f}%"


def build_message(d):
    latest_label  = month_label(d["latest"])
    prev_yr_label = month_label(d["prev_yr"])

    # Top 5 this month
    top5_lines = "\n".join(
        f"  {i+1}. {c}: {int(v):,}"
        for i, (c, v) in enumerate(d["top5_now"].items())
    )

    # Watchlist: Nepal, Bangladesh, key western countries
    watch_lines = []
    for c in WATCH_LIST:
        now  = int(d["this"].get(c, 0))
        prev = int(d["last_y"].get(c, 0))
        watch_lines.append(f"  • {c}: {now:,} ({pct_str(now, prev)} vs {prev_yr_label})")

    # Education-only YTD for Nepal + Bangladesh (the press-release number)
    np_ytd_now  = int(d["ytd_edu_now"].get("Nepal", 0))
    np_ytd_prev = int(d["ytd_edu_prev"].get("Nepal", 0))
    bd_ytd_now  = int(d["ytd_edu_now"].get("Bangladesh", 0))
    bd_ytd_prev = int(d["ytd_edu_prev"].get("Bangladesh", 0))
    combined_now  = np_ytd_now + bd_ytd_now
    combined_prev = np_ytd_prev + bd_ytd_prev

    # Biggest drops
    drop_lines = "\n".join(
        f"  • {c}: {int(r['now']):,} vs {int(r['last_year']):,} ({r['pct']:+.0f}%)"
        for c, r in d["big_drops"].iterrows()
    ) or "  None"

    # G7 check
    g7_now  = sum(int(d["this"].get(c, 0)) for c in G7)
    g7_prev = sum(int(d["last_y"].get(c, 0)) for c in G7)

    return f"""📊 *Student permits update — {latest_label}*

*Top 5 source countries (all study types):*
{top5_lines}

*G7 countries combined:* {g7_now:,} ({pct_str(g7_now, g7_prev)} vs {prev_yr_label})

*Watchlist — year-on-year:*
{chr(10).join(watch_lines)}

*Biggest drops (min 10 permits last year):*
{drop_lines}

*Education-only Jan–{MONTH_NAMES[int(d['latest'][5:])-1]} {d['latest_year']} YTD:*
Nepal + Bangladesh: {combined_now:,} vs {combined_prev:,} same period {int(d['latest_year'])-1} ({pct_str(combined_now, combined_prev)})
_(This is the number the ministry uses — 'ca. 50' was Jan–May 2026)_"""


def main():
    print("Loading data...")
    monthly = load_data()

    print("Analysing...")
    d = analyse(monthly)

    message = build_message(d)
    print("\n── Message preview ──────────────────────────\n")
    print(message)
    print("\n─────────────────────────────────────────────\n")

    resp = requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=30)
    resp.raise_for_status()
    print("Sent to Slack.")


if __name__ == "__main__":
    main()
