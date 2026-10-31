"""
monthly_report.py — analyse latest student permit data and post to Slack.
Called by .github/workflows/monthly-refresh.yml after fetch_data.py runs.

Tracks two OPHOLD (residence permit purpose) categories:
  - "Study etc., education" — the category the ministry's press release used.
  - "Study etc., other reasons" — Statbank's own residual/catch-all label
    within "Study etc."; distinct from au pair and interns, which are
    separate categories. Statbank publishes no further breakdown of what's
    inside it (checked via the VAN77M tableinfo endpoint), so treat it as
    an open question, not a known quantity.

Every section is built by comparing against a rolling window, so the
report changes with the data each month rather than reprinting the same
fixed sections with updated numbers.
"""

import os

import pandas as pd
import requests

from countries import WESTERN

# Unset locally = dry run (prints the message, posts nothing). Unset in
# GitHub Actions is an error, so a missing secret can't pass as a green run.
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK")

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Tightening measures for third-country students were introduced May 2025 —
# see README. Everything before this is the "pre-tightening baseline".
POLICY_START = "2025M05"

# The ministry's June 2026 press release was specifically about these two,
# in the education category.
PRESS_RELEASE_COUNTRIES = ["Nepal", "Bangladesh"]

# Countries whose education permits arrive in a few large batches a year
# (USA: Sep and Jan). One batch shifting by a month (Sep 2026 appears to have
# moved to Aug) puts three batches in a 12-month window and fakes a surge,
# then a crash. They are about half of "everyone else", so they're reported
# on their own lines, intake by intake, and kept out of the aggregate,
# leaderboard and single-month scan.
LUMPY_COUNTRIES = ["USA"]

# Baseline length. Exactly 12 months (May 2024-Apr 2025) so every calendar
# month is counted once; using all pre-policy months double-counted Jan-Apr.
BASELINE_MONTHS = 12

CATEGORIES = [
    ("Education", "Study etc., education"),
    ("Other reasons", "Study etc., other reasons"),
]

# Trailing windows for the "is this broad or targeted" comparison.
# 12 months avoids conflating the policy effect with normal intake
# seasonality (permit issuance clusters around Aug/Jan academic starts).
# 3 months is shown alongside as a caveated directional signal only.
TRAILING_SEASONAL_SAFE = 12
TRAILING_RAW = 3

# Minimum total permits during the pre-policy period for a country to be
# included in a leaderboard/aggregate — keeps single-digit-a-year countries
# from dominating a %-change ranking on noise. Same monthly rate as the
# 30-over-16-months bar used before the baseline became 12 months.
MIN_BASELINE_SUM = 23

# Minimum year-ago count for a country to be included in the monthly
# shock scan. Single months are noisy, so this is set higher than the
# baseline threshold (0 vs 11 is not a story).
MIN_YOY_BASE = 20

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


def pct_change(baseline, current):
    return (current - baseline) / baseline.replace(0, pd.NA) * 100


def load_data():
    df = pd.read_csv("data/van77m_raw.csv")
    df["INDHOLD"] = pd.to_numeric(df["INDHOLD"], errors="coerce").fillna(0).astype(int)
    return df


def pivot_for(df, ophold_value):
    sub = df[df["OPHOLD"] == ophold_value]
    return sub.pivot_table(index="STATSB", columns="TID", values="INDHOLD",
                            aggfunc="sum", fill_value=0)


def category_stats(pivot):
    """Baseline vs rolling-window stats shared by every category section."""
    periods = sorted(pivot.columns)
    latest = periods[-1]

    pre_periods = [p for p in periods if p < POLICY_START][-BASELINE_MONTHS:]
    trailing12  = periods[-TRAILING_SEASONAL_SAFE:]
    trailing3   = periods[-TRAILING_RAW:]

    latest_yr, latest_m = latest.split("M")
    year_ago_period = f"{int(latest_yr) - 1}M{latest_m}"

    pre_avg = pivot[pre_periods].mean(axis=1)
    pre_sum = pivot[pre_periods].sum(axis=1)
    t12_avg = pivot[trailing12].mean(axis=1)
    t3_avg  = pivot[trailing3].mean(axis=1)

    return {
        "periods": periods, "latest": latest, "year_ago_period": year_ago_period,
        "pre_periods": pre_periods, "trailing12": trailing12, "trailing3": trailing3,
        "pre_avg": pre_avg, "pre_sum": pre_sum, "t12_avg": t12_avg, "t3_avg": t3_avg,
        "t12_pct": pct_change(pre_avg, t12_avg),
        "pool": pivot.index[pre_sum >= MIN_BASELINE_SUM],
    }


def monthly_yoy_shocks(pivot, stats, n=SHOCK_LIST_SIZE):
    latest, year_ago_period = stats["latest"], stats["year_ago_period"]
    if year_ago_period not in pivot.columns:
        return None
    yoy = pd.DataFrame({"now": pivot[latest], "ya": pivot[year_ago_period]})
    yoy = yoy[yoy["ya"] >= MIN_YOY_BASE]
    yoy["change"] = yoy["now"] - yoy["ya"]
    yoy["pct"] = yoy["change"] / yoy["ya"] * 100
    return yoy.reindex(yoy["pct"].abs().sort_values(ascending=False).index).head(n)


# Intake seasons for lumpy countries: autumn Jul-Oct catches the Sep batch
# even if it lands in Aug or Oct; spring Dec-Feb catches the Jan batch.
AUTUMN = ["07", "08", "09", "10"]


def intake_totals(row, periods):
    """{label: (total, complete?)} for each autumn and spring intake."""
    have = set(periods)
    out = {}
    for y in sorted({p[:4] for p in periods}):
        months = [f"{y}M{m}" for m in AUTUMN]
        if any(m in have for m in months):
            out[f"Autumn {y}"] = (sum(row.get(m, 0) for m in months),
                                  all(m in have for m in months))
        months = [f"{int(y) - 1}M12", f"{y}M01", f"{y}M02"]
        if any(m in have for m in months):
            out[f"Spring {y}"] = (sum(row.get(m, 0) for m in months),
                                  all(m in have for m in months))
    return out


def lumpy_stats(pivot, stats):
    """Latest autumn and spring intakes vs the same intake a year earlier."""
    rows = {}
    for c in LUMPY_COUNTRIES:
        if c not in pivot.index:
            continue
        it = intake_totals(pivot.loc[c].to_dict(), stats["periods"])
        lines = []
        for season in ("Autumn", "Spring"):
            keys = sorted(k for k in it if k.startswith(season))
            if len(keys) >= 2:
                (cur_k, prev_k) = keys[-1], keys[-2]
                (cur, done), (prev, _) = it[cur_k], it[prev_k]
                lines.append((cur_k, cur, done, prev_k, prev))
        rows[c] = lines
    return rows


def analyse_education(pivot):
    s = category_stats(pivot)
    excluded = PRESS_RELEASE_COUNTRIES + LUMPY_COUNTRIES
    others_pool = s["pool"].difference(excluded)

    npbd_pre = s["pre_avg"].reindex(PRESS_RELEASE_COUNTRIES).sum()
    npbd_t12 = s["t12_avg"].reindex(PRESS_RELEASE_COUNTRIES).sum()
    npbd_t3  = s["t3_avg"].reindex(PRESS_RELEASE_COUNTRIES).sum()

    others_pre_total = s["pre_avg"].drop(index=excluded, errors="ignore").sum()
    others_t12_total = s["t12_avg"].drop(index=excluded, errors="ignore").sum()
    others_t3_total  = s["t3_avg"].drop(index=excluded, errors="ignore").sum()

    leaderboard = s["t12_pct"].loc[others_pool].sort_values().head(LEADERBOARD_SIZE)
    n_down = (s["t12_pct"].loc[others_pool] < 0).sum()

    return {
        **s,
        "npbd_pre": npbd_pre, "npbd_t12": npbd_t12, "npbd_t3": npbd_t3,
        "others_pre_total": others_pre_total,
        "others_t12_total": others_t12_total, "others_t3_total": others_t3_total,
        "leaderboard": leaderboard,
        "n_down": n_down, "n_total": len(others_pool),
        "yoy_shocks": monthly_yoy_shocks(pivot.drop(index=LUMPY_COUNTRIES, errors="ignore"), s),
        "lumpy": lumpy_stats(pivot, s),
    }


def analyse_other_reasons(pivot):
    s = category_stats(pivot)
    pool = s["pool"]

    pool_pre_total = s["pre_avg"].loc[pool].sum()
    pool_t12_total = s["t12_avg"].loc[pool].sum()

    ranked = s["t12_pct"].loc[pool].sort_values()

    return {
        **s,
        "pool_pre_total": pool_pre_total, "pool_t12_total": pool_t12_total,
        "declines": ranked.head(LEADERBOARD_SIZE),
        "gains": ranked.tail(LEADERBOARD_SIZE)[::-1],
        "n_down": int((ranked < 0).sum()), "n_total": len(pool),
    }


def build_education_section(d, t12_label):
    npbd_t12_pct = pct_change(pd.Series([d["npbd_pre"]]), pd.Series([d["npbd_t12"]])).iloc[0]
    npbd_t3_pct  = pct_change(pd.Series([d["npbd_pre"]]), pd.Series([d["npbd_t3"]])).iloc[0]
    others_t12_pct = pct_change(pd.Series([d["others_pre_total"]]), pd.Series([d["others_t12_total"]])).iloc[0]
    others_t3_pct  = pct_change(pd.Series([d["others_pre_total"]]), pd.Series([d["others_t3_total"]])).iloc[0]

    tracker = f"""*Ministry claim tracker — Nepal + Bangladesh, education permits:*
{d['npbd_t12']:.0f}/mo over {t12_label} vs {d['npbd_pre']:.0f}/mo pre-tightening baseline ({pct_fmt(npbd_t12_pct)})
_(raw last 3 months: {d['npbd_t3']:.0f}/mo, {pct_fmt(npbd_t3_pct)} — seasonal, directional only)_"""

    lb_lines = "\n".join(
        f"  • {country}{western_tag(country)}: {pct_fmt(pct)} vs pre-tightening baseline"
        for country, pct in d["leaderboard"].items()
    ) or "  None"

    collateral = f"""*Everyone else, combined ({d['n_total']} countries tracked, excl. {", ".join(LUMPY_COUNTRIES)}):*
{d['others_t12_total']:.0f}/mo over {t12_label} vs {d['others_pre_total']:.0f}/mo pre-tightening baseline ({pct_fmt(others_t12_pct)})
{d['n_down']} of {d['n_total']} down since the policy, {d['n_total'] - d['n_down']} flat or up
_(raw last 3 months: {pct_fmt(others_t3_pct)} — same seasonal effect as above hits this figure too)_

*Biggest declines outside Nepal/Bangladesh (12-month basis):*
{lb_lines}"""

    lumpy_lines = "\n".join(
        f"  • {c}{western_tag(c)} {cur_k}: {cur:.0f} vs {prev:.0f} in {prev_k}"
        + (f" ({pct_fmt((cur - prev) / prev * 100)})" if done and prev else " (intake still in progress)")
        for c, lines in d["lumpy"].items()
        for cur_k, cur, done, prev_k, prev in lines
    )
    if lumpy_lines:
        collateral += ("\n\n*Reported separately — permits arrive in large batches, "
                       "compared intake by intake:*\n" + lumpy_lines)

    if d["yoy_shocks"] is not None and len(d["yoy_shocks"]):
        shock_lines = "\n".join(
            f"  • {country}{western_tag(country)}: {int(row['now'])} vs {int(row['ya'])} a year ago ({pct_fmt(row['pct'])})"
            for country, row in d["yoy_shocks"].iterrows()
        )
    else:
        shock_lines = "  Not enough data for a year-on-year comparison yet."

    shocks = f"""*Biggest single-month moves, {month_label(d['latest'])} vs {month_label(d['year_ago_period'])}:*
{shock_lines}"""

    return f"*📚 EDUCATION PERMITS*\n\n{tracker}\n\n{collateral}\n\n{shocks}"


def build_other_reasons_section(d, t12_label):
    pool_pct = pct_change(pd.Series([d["pool_pre_total"]]), pd.Series([d["pool_t12_total"]])).iloc[0]

    decline_lines = "\n".join(
        f"  • {country}{western_tag(country)}: {pct_fmt(pct)} vs pre-tightening baseline"
        for country, pct in d["declines"].items()
    ) or "  None"
    gain_lines = "\n".join(
        f"  • {country}{western_tag(country)}: {pct_fmt(pct)} vs pre-tightening baseline"
        for country, pct in d["gains"].items()
    ) or "  None"

    return f"""*🗂️ OTHER-REASONS PERMITS*
_("Study etc., other reasons" is Statbank's own residual label — distinct from au pair and interns, which are tracked separately. No further official breakdown of what it covers is published, so treat the composition as an open question.)_

*All {d['n_total']} tracked countries, combined:*
{d['pool_t12_total']:.0f}/mo over {t12_label} vs {d['pool_pre_total']:.0f}/mo pre-tightening baseline ({pct_fmt(pool_pct)})
{d['n_down']} of {d['n_total']} down since the policy, {d['n_total'] - d['n_down']} flat or up

*Biggest declines (12-month basis):*
{decline_lines}

*Biggest gains (12-month basis):*
{gain_lines}"""


def build_message(edu_d, other_d, t12_label):
    latest_label = month_label(edu_d["latest"])
    return f"""📊 *Student permits update — {latest_label}*

{build_education_section(edu_d, t12_label)}

──
{build_other_reasons_section(other_d, t12_label)}"""


def main():
    print("Loading data...")
    df = load_data()

    print("Analysing...")
    edu_pivot   = pivot_for(df, "Study etc., education")
    other_pivot = pivot_for(df, "Study etc., other reasons")

    edu_d   = analyse_education(edu_pivot)
    other_d = analyse_other_reasons(other_pivot)
    t12_label = period_range_label(edu_d["trailing12"])

    message = build_message(edu_d, other_d, t12_label)
    print("\n── Message preview ──────────────────────────\n")
    print(message)
    print("\n─────────────────────────────────────────────\n")

    if not SLACK_WEBHOOK:
        if os.environ.get("GITHUB_ACTIONS"):
            raise RuntimeError("SLACK_WEBHOOK is not set — nothing posted.")
        print("SLACK_WEBHOOK not set — dry run, nothing posted.")
        return
    resp = requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=30)
    resp.raise_for_status()
    print("Sent to Slack.")


if __name__ == "__main__":
    main()
