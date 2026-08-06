"""
monthly_report.py — analyse latest student permit data and post to Slack.
Called by .github/workflows/monthly-refresh.yml after fetch_data.py runs.

All analysis is education-permit-only (OPHOLD == "Study etc., education") —
that's the category the ministry's press release used, and the one that
maps onto "student" in the ordinary sense (as opposed to au pair/intern/
other-reasons permits, which are different routes entirely).

Every section is built by comparing against a rolling window, so the
report changes with the data each month rather than reprinting the same
fixed sections with updated numbers.
"""

import os

import pandas as pd
import requests

from countries import WESTERN

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Tightening measures for third-country students were introduced May 2025 —
# see README. Everything before this is the "pre-tightening baseline".
POLICY_START = "2025M05"

# The ministry's June 2026 press release was specifically about these two.
PRESS_RELEASE_COUNTRIES = ["Nepal", "Bangladesh"]

# Trailing windows for the "is this broad or targeted" comparison.
# 12 months avoids conflating the policy effect with normal intake
# seasonality (permit issuance clusters around Aug/Jan academic starts).
# 3 months is shown alongside as a caveated directional signal only.
TRAILING_SEASONAL_SAFE = 12
TRAILING_RAW = 3

# Minimum total permits during the pre-policy period for a country to be
# included in the collateral-impact leaderboard/aggregate — keeps single-
# digit-a-year countries from dominating a %-change ranking on noise.
MIN_BASELINE_SUM = 30

# Minimum year-ago count for a country to be included in the monthly
# shock scan, same reasoning.
MIN_YOY_BASE = 5

LEADERBOARD_SIZE = 5
SHOCK_LIST_SIZE = 5


def month_label(period):
    year, m = period.split("M")
    return f"{MONTH_NAMES[int(m) - 1]} {year}"


def period_range_label(periods):
    return f"{month_label(periods[0])}–{month_label(periods[-1])}"


def western_tag(country):
    return " [Western]" if country in WESTERN else ""


def arrow(n):
    if pd.isna(n) or n == 0:
        return "—"
    return "▲" if n > 0 else "▼"


def pct_fmt(pct):
    if pd.isna(pct):
        return "n/a"
    return f"{arrow(pct)} {abs(pct):.0f}%"


def load_data():
    df = pd.read_csv("data/van77m_raw.csv")
    df["INDHOLD"] = pd.to_numeric(df["INDHOLD"], errors="coerce").fillna(0).astype(int)
    edu = df[df["OPHOLD"] == "Study etc., education"]
    return edu.pivot_table(index="STATSB", columns="TID", values="INDHOLD",
                            aggfunc="sum", fill_value=0)


def pct_change(baseline, current):
    return (current - baseline) / baseline.replace(0, pd.NA) * 100


def analyse(pivot):
    periods = sorted(pivot.columns)
    latest = periods[-1]

    pre_periods     = [p for p in periods if p < POLICY_START]
    trailing12       = periods[-TRAILING_SEASONAL_SAFE:]
    trailing3        = periods[-TRAILING_RAW:]

    latest_yr, latest_m = latest.split("M")
    year_ago_period = f"{int(latest_yr) - 1}M{latest_m}"

    pre_avg  = pivot[pre_periods].mean(axis=1)
    pre_sum  = pivot[pre_periods].sum(axis=1)
    t12_avg  = pivot[trailing12].mean(axis=1)
    t3_avg   = pivot[trailing3].mean(axis=1)

    t12_pct = pct_change(pre_avg, t12_avg)
    t3_pct  = pct_change(pre_avg, t3_avg)

    pool = pivot.index[pre_sum >= MIN_BASELINE_SUM]
    others_pool = pool.difference(PRESS_RELEASE_COUNTRIES)

    npbd_pre  = pre_avg.reindex(PRESS_RELEASE_COUNTRIES).sum()
    npbd_t12  = t12_avg.reindex(PRESS_RELEASE_COUNTRIES).sum()
    npbd_t3   = t3_avg.reindex(PRESS_RELEASE_COUNTRIES).sum()

    others_pre_total = pre_avg.drop(index=PRESS_RELEASE_COUNTRIES, errors="ignore").sum()
    others_t12_total = t12_avg.drop(index=PRESS_RELEASE_COUNTRIES, errors="ignore").sum()
    others_t3_total  = t3_avg.drop(index=PRESS_RELEASE_COUNTRIES, errors="ignore").sum()

    leaderboard = t12_pct.loc[others_pool].sort_values().head(LEADERBOARD_SIZE)
    n_down = (t12_pct.loc[others_pool] < 0).sum()
    n_total = len(others_pool)

    yoy_shocks = None
    if year_ago_period in pivot.columns:
        yoy = pd.DataFrame({"now": pivot[latest], "ya": pivot[year_ago_period]})
        yoy = yoy[yoy["ya"] >= MIN_YOY_BASE]
        yoy["change"] = yoy["now"] - yoy["ya"]
        yoy["pct"] = yoy["change"] / yoy["ya"] * 100
        yoy_shocks = yoy.reindex(yoy["pct"].abs().sort_values(ascending=False).index).head(SHOCK_LIST_SIZE)

    return {
        "latest": latest,
        "year_ago_period": year_ago_period,
        "pre_periods": pre_periods,
        "trailing12": trailing12,
        "trailing3": trailing3,
        "npbd_pre": npbd_pre, "npbd_t12": npbd_t12, "npbd_t3": npbd_t3,
        "others_pre_total": others_pre_total,
        "others_t12_total": others_t12_total,
        "others_t3_total": others_t3_total,
        "leaderboard": leaderboard,
        "t12_avg": t12_avg, "pre_avg": pre_avg,
        "n_down": n_down, "n_total": n_total,
        "yoy_shocks": yoy_shocks,
    }


def build_message(d):
    latest_label = month_label(d["latest"])
    pre_label    = period_range_label(d["pre_periods"])
    t12_label    = period_range_label(d["trailing12"])

    npbd_t12_pct = pct_change(pd.Series([d["npbd_pre"]]), pd.Series([d["npbd_t12"]])).iloc[0]
    npbd_t3_pct  = pct_change(pd.Series([d["npbd_pre"]]), pd.Series([d["npbd_t3"]])).iloc[0]
    others_t12_pct = pct_change(pd.Series([d["others_pre_total"]]), pd.Series([d["others_t12_total"]])).iloc[0]
    others_t3_pct  = pct_change(pd.Series([d["others_pre_total"]]), pd.Series([d["others_t3_total"]])).iloc[0]

    tracker_section = f"""*Ministry claim tracker — Nepal + Bangladesh, education permits:*
{d['npbd_t12']:.0f}/mo over {t12_label} vs {d['npbd_pre']:.0f}/mo pre-tightening baseline ({pct_fmt(npbd_t12_pct)})
_(raw last 3 months: {d['npbd_t3']:.0f}/mo, {pct_fmt(npbd_t3_pct)} — seasonal, directional only)_"""

    lb_lines = "\n".join(
        f"  • {country}{western_tag(country)}: {pct_fmt(pct)} vs pre-tightening baseline"
        for country, pct in d["leaderboard"].items()
    ) or "  None"

    collateral_section = f"""*Everyone else, combined ({d['n_total']} countries tracked):*
{d['others_t12_total']:.0f}/mo over {t12_label} vs {d['others_pre_total']:.0f}/mo pre-tightening baseline ({pct_fmt(others_t12_pct)})
{d['n_down']} of {d['n_total']} down since the policy, {d['n_total'] - d['n_down']} flat or up
_(raw last 3 months: {pct_fmt(others_t3_pct)} — see caveat above, same seasonal effect hits this figure too)_

*Biggest declines outside Nepal/Bangladesh (12-month basis):*
{lb_lines}"""

    if d["yoy_shocks"] is not None and len(d["yoy_shocks"]):
        shock_lines = "\n".join(
            f"  • {country}{western_tag(country)}: {int(row['now'])} vs {int(row['ya'])} a year ago ({pct_fmt(row['pct'])})"
            for country, row in d["yoy_shocks"].iterrows()
        )
    else:
        shock_lines = "  Not enough data for a year-on-year comparison yet."

    shock_section = f"""*Biggest single-month moves, {latest_label} vs {month_label(d['year_ago_period'])}:*
{shock_lines}"""

    return f"""📊 *Student permits update — {latest_label}*

{tracker_section}

──
{collateral_section}

──
{shock_section}"""


def main():
    print("Loading data...")
    pivot = load_data()

    print("Analysing...")
    d = analyse(pivot)

    message = build_message(d)
    print("\n── Message preview ──────────────────────────\n")
    print(message)
    print("\n─────────────────────────────────────────────\n")

    resp = requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=30)
    resp.raise_for_status()
    print("Sent to Slack.")


if __name__ == "__main__":
    main()
