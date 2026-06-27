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

A GitHub Action runs on the 5th of each month, fetches the latest VAN77M data, commits the updated CSVs, and posts a summary to Slack covering:

- Top source countries that month
- Year-on-year changes for Nepal, Bangladesh, China, India, Canada, USA, Pakistan, Turkey
- G7 countries combined
- Education-only Jan-to-date totals (the number the ministry uses)

To enable Slack notifications, add your webhook URL as a repository secret named `SLACK_WEBHOOK`. You can also trigger the action manually from the Actions tab.

## Context

The press release ([23 June 2026](https://www.uim.dk)) compared ~800 student permits issued to Nepali and Bangladeshi nationals in January–May 2025 with ~50 in the same period of 2026, citing tightening measures introduced in May 2025. What the press release doesn't cover is what happened to everyone else — which is what this app is for.

## Licence

CC0 — public domain.
