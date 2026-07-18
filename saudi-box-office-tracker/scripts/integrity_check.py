#!/usr/bin/env python3
"""Automated data-integrity checks (A–I).

Writes machine findings to data/integrity_findings.json and a human-readable
report to reports/Integrity_Report.md.
"""
from __future__ import annotations
import json
import datetime
from collections import defaultdict

import bo_lib
from bo_lib import ROOT

OUT_JSON = ROOT / "data" / "integrity_findings.json"
OUT_MD = ROOT / "reports" / "Integrity_Report.md"


def main():
    weeks = bo_lib.load_weeks()
    films_by_week = bo_lib.load_films_raw()
    canon = bo_lib.load_canon()
    rows = bo_lib.film_rows(weeks, films_by_week, canon)

    findings = {"generated": datetime.date.today().isoformat(), "summary": {}, "checks": []}
    weeks_by_filename = {w["filename"]: w for w in weeks}

    # ---------- A: each week has exactly 10 films ----------
    issues = [{"filename": fw["filename"], "n_films": len(fw.get("films", []))}
              for fw in films_by_week if len(fw.get("films", [])) != 10]
    findings["checks"].append({
        "id": "A", "name": "Each week has exactly 10 films",
        "expected": "n_films == 10 for every week",
        "n_checked": len(films_by_week), "n_failed": len(issues), "issues": issues,
    })

    # ---------- B: date_end is a Saturday ----------
    issues = []
    for w in weeks:
        de = w.get("date_end")
        if not de:
            continue
        try:
            d = datetime.date.fromisoformat(de)
            if d.weekday() != 5:
                issues.append({"filename": w["filename"], "date_end": de, "weekday": d.strftime("%A")})
        except ValueError:
            issues.append({"filename": w["filename"], "date_end": de, "weekday": "INVALID"})
    findings["checks"].append({
        "id": "B", "name": "date_end is a Saturday",
        "expected": "every date_end falls on a Saturday",
        "n_checked": len(weeks), "n_failed": len(issues), "issues": issues,
    })

    # ---------- C: year/month match date_end ----------
    issues = []
    for w in weeks:
        de = w.get("date_end")
        if not de:
            continue
        try:
            d = datetime.date.fromisoformat(de)
            counts = defaultdict(int)
            for i in range(7):
                dd = d - datetime.timedelta(days=i)
                counts[(dd.year, dd.month)] += 1
            label_year, label_month = max(counts, key=lambda k: (counts[k], k))
            if w.get("year") != label_year or w.get("month") != label_month:
                issues.append({"filename": w["filename"], "date_end": de,
                               "stored": (w.get("year"), w.get("month")),
                               "computed": (label_year, label_month)})
        except ValueError:
            pass
    findings["checks"].append({
        "id": "C", "name": "Year/month match the date_end's majority-of-days month",
        "expected": "stored (year, month) equals the labeled month for that week",
        "n_checked": len(weeks), "n_failed": len(issues), "issues": issues[:10],
    })

    # ---------- D: avg ticket price in 30..100 SAR ----------
    issues = []
    for w in weeks:
        rev, tk = w.get("revenue_M_SAR"), w.get("tickets_K")
        if not rev or not tk:
            continue
        avg = (rev * 1_000_000) / (tk * 1_000)
        if avg < 30 or avg > 100:
            issues.append({"filename": w["filename"], "date_end": w.get("date_end"), "avg_SAR": round(avg, 2)})
    findings["checks"].append({
        "id": "D", "name": "Avg ticket price (revenue ÷ tickets) in 30–100 SAR",
        "expected": "30 ≤ avg ≤ 100",
        "n_checked": sum(1 for w in weeks if w.get("revenue_M_SAR") and w.get("tickets_K")),
        "n_failed": len(issues), "issues": issues,
    })

    # ---------- E: per-film cumulative monotonicity (keyed on film_id) ----------
    issues = []
    by_film = defaultdict(list)
    for r in rows:
        key = r["film_id"] or (r["title_en"], r["title_ar"])
        by_film[key].append(r)
    n_pairs = 0
    for key, entries in by_film.items():
        entries.sort(key=lambda x: x["week_end"] or "")
        for i in range(1, len(entries)):
            prev, cur = entries[i - 1], entries[i]
            n_pairs += 2
            if prev["total_revenue_M"] is not None and cur["total_revenue_M"] is not None \
                    and cur["total_revenue_M"] + 0.05 < prev["total_revenue_M"]:
                issues.append({"film": str(key), "from": prev["week_end"], "to": cur["week_end"],
                               "field": "total_revenue_M", "prev": prev["total_revenue_M"], "cur": cur["total_revenue_M"]})
            if prev["total_tickets_K"] is not None and cur["total_tickets_K"] is not None \
                    and cur["total_tickets_K"] + 0.5 < prev["total_tickets_K"]:
                issues.append({"film": str(key), "from": prev["week_end"], "to": cur["week_end"],
                               "field": "total_tickets_K", "prev": prev["total_tickets_K"], "cur": cur["total_tickets_K"]})
    findings["checks"].append({
        "id": "E", "name": "Cumulative totals non-decreasing per film (canonical identity)",
        "expected": "total_revenue_M and total_tickets_K do not drop week-over-week for the same film",
        "n_checked": n_pairs, "n_failed": len(issues), "issues": issues[:20],
    })

    # ---------- F: top-10 ticket sum ≤ weekly total ----------
    issues = []
    for fw in films_by_week:
        wk = weeks_by_filename.get(fw["filename"])
        if not wk:
            continue
        wsum = sum((f.get("week_tickets_K") or 0) for f in fw.get("films", []))
        wt = wk.get("tickets_K") or 0
        if wt > 0 and wsum > wt + 0.5:
            issues.append({"filename": fw["filename"], "date_end": fw.get("date_end"),
                           "top10_sum_K": round(wsum, 1), "weekly_total_K": wt,
                           "diff_K": round(wsum - wt, 1)})
    findings["checks"].append({
        "id": "F", "name": "Sum of top-10 weekly tickets ≤ weekly total tickets",
        "expected": "top-10 total tickets should not exceed the week total",
        "n_checked": len(films_by_week), "n_failed": len(issues), "issues": issues,
    })

    # ---------- G: extreme/zero values ----------
    issues = []
    for fw in films_by_week:
        for film in fw.get("films", []):
            for field in ("week_revenue_M", "total_revenue_M"):
                v = film.get(field)
                if v is not None and v > 100:
                    issues.append({"filename": fw["filename"], "rank": film["rank"], "field": field, "value": v})
                if v is not None and v <= 0:
                    issues.append({"filename": fw["filename"], "rank": film["rank"], "field": field,
                                   "value": v, "note": "zero or negative"})
    findings["checks"].append({
        "id": "G", "name": "No zero/negative or absurd revenue (>100M)",
        "expected": "0 < revenue_M ≤ 100",
        "n_checked": sum(len(fw.get("films", [])) for fw in films_by_week) * 2,
        "n_failed": len(issues), "issues": issues[:20],
    })

    # ---------- H: every film row resolves to a canonical film_id ----------
    unresolved = bo_lib.unresolved_titles(rows)
    issues = [{"title_en": en, "title_ar": ar, "last_seen": wk} for (en, ar), wk in unresolved]
    findings["checks"].append({
        "id": "H", "name": "Every film row resolves to a canonical film ID",
        "expected": "config/films_canonical.json covers all observed title variants",
        "n_checked": len(rows), "n_failed": len(issues), "issues": issues,
    })

    # ---------- I: coverage gap map ----------
    gaps = bo_lib.known_gaps(weeks)
    findings["checks"].append({
        "id": "I", "name": "Coverage gap map (missing Saturdays, informational)",
        "expected": "gaps are known and tracked, not silent",
        "n_checked": 1, "n_failed": 0,
        "issues": [], "gaps": gaps,
    })

    # ---------- summary + outputs ----------
    findings["summary"]["total_checks"] = len(findings["checks"])
    findings["summary"]["total_passed"] = sum(1 for c in findings["checks"] if c["n_failed"] == 0)
    findings["summary"]["total_with_issues"] = sum(1 for c in findings["checks"] if c["n_failed"] > 0)
    findings["summary"]["total_issues"] = sum(c["n_failed"] for c in findings["checks"])
    findings["summary"]["n_weeks"] = len(weeks)
    findings["summary"]["n_film_rows"] = len(rows)
    findings["summary"]["n_gaps"] = len(gaps)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human-readable report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data Integrity Report — Saudi Box Office",
        "",
        f"*Generated {findings['generated']} on {len(weeks)} weeks / {len(rows)} film rows.*",
        "",
        f"**{findings['summary']['total_passed']} of {findings['summary']['total_checks']} checks clean; "
        f"{findings['summary']['total_issues']} issue(s) flagged; {len(gaps)} known missing week(s).**",
        "",
        "| Check | Result | Checked | Issues |",
        "|---|---|---|---|",
    ]
    for c in findings["checks"]:
        status = "✅ PASS" if c["n_failed"] == 0 else f"⚠️ {c['n_failed']} issue(s)"
        lines.append(f"| {c['id']} — {c['name']} | {status} | {c['n_checked']} | {c['n_failed']} |")
    flagged = [c for c in findings["checks"] if c["n_failed"] > 0]
    if flagged:
        lines += ["", "## Flagged details", ""]
        for c in flagged:
            lines.append(f"### Check {c['id']} — {c['name']}")
            for iss in c["issues"]:
                lines.append(f"- `{json.dumps(iss, ensure_ascii=False)}`")
            lines.append("")
    if gaps:
        lines += ["", "## Known missing weeks (Saturdays)", ""]
        lines.append(", ".join(gaps))
        lines.append("")
        lines.append("These weeks are absent from the source data — possibly never published by the "
                     "Commission. See KNOWLEDGE_BASE.md for the backfill status.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    for c in findings["checks"]:
        status = "PASS" if c["n_failed"] == 0 else f"{c['n_failed']} issue(s)"
        print(f"  [{c['id']}] {c['name']}: {status}")
    # Issues are warnings for a human to review, not pipeline failures.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
