# Data Integrity Report — Saudi Box Office

*Generated 2026-07-18 on 99 weeks / 990 film rows.*

**8 of 9 checks clean; 2 issue(s) flagged; 15 known missing week(s).**

| Check | Result | Checked | Issues |
|---|---|---|---|
| A — Each week has exactly 10 films | ✅ PASS | 99 | 0 |
| B — date_end is a Saturday | ✅ PASS | 99 | 0 |
| C — Year/month match the date_end's majority-of-days month | ✅ PASS | 99 | 0 |
| D — Avg ticket price (revenue ÷ tickets) in 30–100 SAR | ⚠️ 2 issue(s) | 99 | 2 |
| E — Cumulative totals non-decreasing per film (canonical identity) | ✅ PASS | 1398 | 0 |
| F — Sum of top-10 weekly tickets ≤ weekly total tickets | ✅ PASS | 99 | 0 |
| G — No zero/negative or absurd revenue (>100M) | ✅ PASS | 1980 | 0 |
| H — Every film row resolves to a canonical film ID | ✅ PASS | 990 | 0 |
| I — Coverage gap map (missing Saturdays, informational) | ✅ PASS | 1 | 0 |

## Flagged details

### Check D — Avg ticket price (revenue ÷ tickets) in 30–100 SAR
- `{"filename": "005_Weekly-Box-Office-Report-Design-2026---Sun_-Feb-8th---Feb-W1-EXT.png", "date_end": "2026-02-07", "avg_SAR": 29.59}`
- `{"filename": "068_weekly-update-infographic-sept-w3.png", "date_end": "2024-09-21", "avg_SAR": 27.55}`


## Known missing weeks (Saturdays)

2025-03-08, 2025-03-15, 2025-03-22, 2025-03-29, 2025-10-25, 2025-11-01, 2025-11-08, 2025-11-15, 2025-11-22, 2026-02-21, 2026-02-28, 2026-03-07, 2026-03-14, 2026-03-21, 2026-04-04

These weeks are absent from the source data — possibly never published by the Commission. See KNOWLEDGE_BASE.md for the backfill status.
