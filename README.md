# Student permits — Denmark

A Streamlit app for exploring residence permit data for third-country students in Denmark, built around a June 2026 press release from the Ministry of Immigration and Integration claiming a "dramatic fall" in student permits for Nepali and Bangladeshi nationals.

The data shows the fall is real. It also shows it isn't confined to Nepal and Bangladesh.

Built by [Kelly Rasmussen](https://github.com/KellyDRasmussen) for [Fair & Fornuftig](https://fairogfornuftig.dk).

## Data

All figures are derived from Statistics Denmark (Danmarks Statistik) via [statbank.dk](https://www.statbank.dk).

| Table | Coverage | Granularity |
|-------|----------|-------------|
| **VAN66** | Residence permits by citizenship and permit type | Annual, 2021–2023 |
| **VAN77M** | Residence permits by citizenship and permit type | Monthly, Jan 2024–present |

Both tables cover four study permit categories: education, au pair, interns, and other reasons. The ministry's headline figure uses education-only; the app lets you toggle between that and the full picture.

Data is fetched in BULK format from the Statbank API and stored as CSV in `data/`. Run `fetch_data.py` to refresh.

### Country groupings

Country groupings (G7, G20, Global North/South, Western/Non-Western) follow Statistics Denmark's own definitions where they exist. The Western/Non-Western split uses the Danish statistical definition: EU27 + EEA/European microstates + Canada, USA, Australia, and New Zealand. Grouping logic lives in `countries.py`.

## Running locally

```bash
pip install -r requirements.txt
python fetch_data.py     # pulls fresh data from Statbank API
streamlit run app.py
```

## Automation

A GitHub Action runs on the 5th of each month, fetches the latest VAN77M data, commits the updated CSVs, and posts a summary to Slack covering two permit categories:

**Education** (the ministry's press-release category):
- Nepal + Bangladesh vs their pre-tightening (pre-May 2025) baseline — the ministry's claim, tracked over a rolling 12 months plus a caveated raw 3-month figure
- The same baseline comparison for every other tracked country combined, to check whether the tightening is depressing permits more broadly or is specific to Nepal/Bangladesh
- The countries (outside Nepal/Bangladesh) with the biggest declines vs their own pre-tightening baseline
- The biggest single-month swings vs the same month last year, across all tracked countries

**"Other reasons"** — a separate, unexplained OPHOLD category (distinct from au pair/interns, which are tracked separately; Statbank publishes no further breakdown of what it covers):
- Aggregate change across all tracked countries vs their pre-tightening baseline
- The biggest declines and biggest gains vs each country's own baseline — this category fell ~45% overall post-tightening, concentrated in Nepal/Iran/Sri Lanka/Iraq/Bangladesh while rising for the USA/Australia/Japan, a pattern the education-only numbers don't show

All comparisons are rolling, so the report changes with the data each month instead of reprinting the same fixed sections.

To enable Slack notifications, add your webhook URL as a repository secret named `SLACK_WEBHOOK`. You can also trigger the action manually from the Actions tab.

## Context

The press release ([23 June 2026](https://www.uim.dk)) compared ~800 student permits issued to Nepali and Bangladeshi nationals in January–May 2025 with ~50 in the same period of 2026, citing tightening measures introduced in May 2025. What the press release doesn't cover is what happened to everyone else — which is what this app is for.

## Licence

CC0 — public domain.
