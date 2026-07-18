#!/usr/bin/env python3
"""Export the canonical film registry + live aggregates as a CSV that matches the
"films_tagged" Google Sheet's columns, ready for File > Import (replace data).

Columns (same as the sheet): title_en, title_ar, country, genre_primary,
genre_secondary, confidence, note, best_total_revenue_M, weeks_in_top10,
best_rank, first_week, last_week

Output: reports/films_tagged_export.csv
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import bo_lib

OUT = bo_lib.ROOT / "reports" / "films_tagged_export.csv"


def main() -> int:
    canon = bo_lib.load_canon()
    rows = bo_lib.film_rows(canon=canon)

    agg = defaultdict(lambda: {"best_total": 0.0, "weeks": 0, "best_rank": 99,
                               "first": "9999", "last": ""})
    for r in rows:
        fid = r["film_id"]
        if not fid:
            continue
        a = agg[fid]
        a["best_total"] = max(a["best_total"], r["total_revenue_M"] or 0)
        a["weeks"] += 1
        a["best_rank"] = min(a["best_rank"], r["rank"] or 99)
        a["first"] = min(a["first"], r["week_end"])
        a["last"] = max(a["last"], r["week_end"])

    out_rows = []
    for fid, f in canon.films.items():
        a = agg.get(fid)
        if not a:
            continue  # registry entry with no data rows (shouldn't happen)
        out_rows.append({
            "title_en": f.get("title_en", ""),
            "title_ar": f.get("title_ar", ""),
            "country": f.get("country", ""),
            "genre_primary": f.get("genre", ""),
            "genre_secondary": f.get("genre_secondary", ""),
            "confidence": f.get("confidence", ""),
            "note": f.get("note", ""),
            "best_total_revenue_M": f'{a["best_total"]:g}',
            "weeks_in_top10": a["weeks"],
            "best_rank": a["best_rank"],
            "first_week": a["first"],
            "last_week": a["last"],
        })
    out_rows.sort(key=lambda r: -float(r["best_total_revenue_M"] or 0))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"films_tagged export: {len(out_rows)} films -> {OUT.name} "
          f"(Google Sheet: File > Import > Replace current sheet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
