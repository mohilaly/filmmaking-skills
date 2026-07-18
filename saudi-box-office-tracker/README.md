# Saudi Box Office Tracker

A clean, growing dataset of the Saudi cinema box office, built from the weekly
infographics published by the **Saudi Film Commission** (هيئة الأفلام, Ministry
of Culture) at [film.moc.gov.sa/Box-Office](https://film.moc.gov.sa/Box-Office).

Every week the Commission publishes one image with three headline numbers and a
top-10 films panel. This project turns those images into structured data
(JSONL + Excel) so the numbers can be tracked, compared, and charted over time.

## What's in the box

- **`Saudi_Box_Office_Weekly.xlsx`** — the deliverable, 7 sheets: Weekly Summary,
  Top 10 Films, Films by Title, Monthly Totals, Yearly Totals, About, and a
  Coverage Calendar.
- **`Saudi_Box_Office_Dashboard.html`** — a self-contained dashboard (opens
  offline, light + dark, inline-SVG charts).
- **`Saudi_Box_Office_DATA_BRIEF.md`** — an always-current plain-text briefing.
- **`data/`** — the raw, append-only source of truth:
  - `weekly_data.jsonl` — one record per week (headline numbers).
  - `films_data.jsonl` — one record per top-10 film per week.
  - `source_image_urls.txt` — provenance: the source image for every week.
- **`config/films_canonical.json`** — a canonical film registry so the same
  film under different Arabic/English spellings is counted once.
- **`scripts/`** — the pipeline (see below).

## Coverage

- **4 May 2024 → 4 July 2026** — 99 weeks captured (15 known-missing weeks are
  flagged in the Coverage Calendar, not treated as zero-activity).
- ~990 film entries resolving to ~291 unique films.

| Year | Weeks | Tickets (K) | Revenue (M SAR) | Avg ticket (SAR) |
|------|-------|-------------|------------------|-------------------|
| 2024 | 35 | 13,218.4 | 629.0 | 47.59 |
| 2025 | 44 | 17,687.9 | 859.7 | 48.60 |
| 2026 | 20 | 8,722.7 | 435.3 | 49.90 |

(2024 and 2026 are partial years.)

**Units, fixed across the whole dataset:** tickets are in **thousands**,
revenue in **millions of SAR**. Average ticket price = revenue × 1,000,000 ÷
(tickets × 1,000).

## Rebuilding

The pipeline runs in a local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install openpyxl Pillow matplotlib
python3 scripts/run_pipeline.py
```

`run_pipeline.py` auto-uses `.venv`, so it works regardless of which `python3`
is on your PATH. It runs the integrity checks (A–I), rebuilds the workbook and
Coverage Calendar, then regenerates the dashboard, brief, and charts.

## How the data is extracted

The Commission's page is a JavaScript app and is **geo-restricted to traffic
inside Saudi Arabia** — fetching it must be done from a machine in KSA
(`scripts/check_new_report.sh` is a watcher for exactly that). Each new weekly
image is read with vision (not OCR — OCR mangles the small decimals): the header
band gives films / tickets / revenue and the exact week range, and the top-10
panel is read card by card. One record per week is appended to the two JSONL
files, film identities are resolved against the canonical registry, and the
pipeline rebuilds everything.

## License & data

Code is released under the [MIT License](LICENSE). The underlying figures are
facts drawn from the Saudi Film Commission's publicly published weekly reports;
this repository is an independent, unofficial dataset and is not affiliated with
or endorsed by the Commission.
