# Saudi Box Office Dataset — Briefing for Analysis

This document describes `Saudi_Box_Office_Weekly.xlsx` so it can be analyzed without
seeing how it was built. Read this first, then work from the spreadsheet.
*Regenerated automatically on 2026-07-18 — numbers below are always current.*

## What the data is

Weekly cinema box office for Saudi Arabia, taken from the Saudi Film Commission's
official weekly reports (Ministry of Culture). One row per published week, plus the
top 10 films for each of those weeks. Source: https://film.moc.gov.sa/Box-Office

- **Coverage:** 4 May 2024 to 4 Jul 2026.
- **Weeks captured:** 99 (of 114 Saturdays in the
  range — 15 were never published; see caveat 3).
- **Unique films tracked:** 291 (via the canonical film registry — the same
  film under different spellings counts once).

## Units and conventions (important)

- **Tickets are in THOUSANDS.** A value of `695.9` means 695,900 tickets.
- **Revenue is in MILLIONS of Saudi Riyals (SAR).** A value of `35.3` means 35.3 million SAR.
- **Average ticket price** = revenue ÷ tickets, expressed in SAR.
- A week's figures cover the prior trading week ending that Saturday ("Week ending" /
  "Date end" is the last day of the range).
- For each film, "Week revenue/tickets" is that single week; "Total revenue/tickets"
  is cumulative since the film's release.
- Currency is SAR throughout. No inflation adjustment has been applied.

## Sheets and columns

### 1. Weekly Summary (99 rows, newest first)
One row per week: week ending date, year/month/week keys, films in cinema, tickets
(thousands), revenue (million SAR), average ticket price, Arabic week label, trading
date range, source image and URL.

### 2. Top 10 Films (990 rows)
One row per film per week: week keys, rank 1–10, Arabic + English title, country,
weeks in cinema, that week's revenue/tickets, cumulative revenue/tickets, source image.

### 3. Films by Title (291 rows)
One row per unique film (canonical identity), aggregated across all its weeks:
first/last week seen, weeks in top 10, best rank, best single-week revenue, best
cumulative revenue and tickets.

### 4. Monthly Totals (27 rows)
Aggregated per year+month: weeks counted, tickets, revenue, avg films/week, avg price.

### 5. Yearly Totals
| Year | Weeks captured | Tickets (K) | Revenue (M SAR) | Avg ticket (SAR) |
|---|---|---|---|---|
| 2024 | 35 | 13,218.4 | 629 | 47.59 |
| 2025 | 44 | 17,687.9 | 859.7 | 48.60 |
| 2026 | 20 | 8,722.7 | 435.3 | 49.90 |

(First and last years are partial.)

### 6. About
Provenance and method notes.

### 7. Coverage Calendar
Per-Saturday capture map — green captured, red missing. Use it to see exactly which
weeks any period is missing before summing.

## Countries present
Australia, Bangladesh, Belgium, Canada, China, Egypt, Finland, France, Hong Kong, India, Japan, Philippines, Russia, Saudi Arabia, UK, USA.

## Caveats the analyst must respect

1. **Partial years.** Capture starts 4 May 2024; the current
   year runs through 4 Jul 2026. Do not compare full-year
   totals without normalizing (use weeks-captured, or compare like periods).
2. **Weeks captured per year differ** (35 / 44 / 20).
   Divide by weeks captured for fair per-week comparisons, not by 52.
3. **History has gaps — exactly 15 missing Saturdays:** 4 weeks 8 Mar 2025 → 29 Mar 2025; 5 weeks 25 Oct 2025 → 22 Nov 2025; 5 weeks 21 Feb 2026 → 21 Mar 2026; 4 Apr 2026.
   These were never published by the Commission (backfill hunt planned). Treat missing
   weeks as absent data, NOT zero activity. A simple sum understates any period
   containing a gap; the Coverage Calendar sheet shows exactly where they are.
4. **Tickets in thousands, revenue in millions.** Multiply before reporting absolutes.
5. **Titles can be Arabic-only or English-only.** Group films via the "Films by Title"
   sheet (canonical identity), never by matching title strings yourself.
6. **Figures were transcribed from infographic images by sight**, so a stray digit is
   possible. For high-stakes numbers, sanity-check against the source image (URL in
   the Weekly Summary sheet). Cumulative figures occasionally jump when a film
   re-enters the chart.
7. **Genre tags exist outside the xlsx** — the canonical registry
   (`config/films_canonical.json`) and the "films_tagged" Google Sheet carry per-film
   genre; the source reports have no genre, distributor, or screen-count fields.

## Good questions this data can answer
Yearly and monthly trends; seasonality and holiday peaks; local (Saudi/Egyptian) vs
Hollywood share over time; longest-running and highest-grossing films; opening-to-total
multipliers ("legs"); weekly decay per film; top-10 concentration; ticket-price drift;
week-over-week momentum; year-over-year cumulative pace on like-for-like weeks.
