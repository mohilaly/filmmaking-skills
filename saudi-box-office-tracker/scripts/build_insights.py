#!/usr/bin/env python3
"""Insights layer: compute metrics -> charts -> dashboard -> brief -> email.

Reads the raw JSONL through bo_lib (canonical film identity), writes:
    Saudi_Box_Office_Dashboard.html      self-contained dashboard (Mac + iPhone)
    Saudi_Box_Office_DATA_BRIEF.md       analyst briefing, always current
    reports/charts/*.png                 static charts (email twin + reuse)
    reports/weekly_email.html            rich local twin of the weekly digest
    reports/email_draft_body.html        CSS-only body for the Gmail draft
    reports/email_subject.txt            subject line for the Gmail draft

Units everywhere: tickets in THOUSANDS, revenue in MILLIONS of SAR.
"""
from __future__ import annotations

import datetime
import json
from collections import defaultdict
from pathlib import Path

import bo_lib

ROOT = bo_lib.ROOT
REPORTS = ROOT / "reports"
CHARTS = REPORTS / "charts"

# Origin groups: color follows the entity, fixed order (see dashboard palette)
ORIGIN_GROUPS = ["Saudi Arabia", "Egypt", "USA", "India", "Other"]


def origin_group(country: str) -> str:
    return country if country in ORIGIN_GROUPS[:4] else "Other"


def _iso_week(date_str: str) -> int:
    return datetime.date.fromisoformat(date_str).isocalendar()[1]


# --------------------------------------------------------------------------
# compute
# --------------------------------------------------------------------------

def compute() -> dict:
    weeks = sorted(bo_lib.load_weeks(), key=lambda w: w["date_end"])
    canon = bo_lib.load_canon()
    rows = bo_lib.film_rows(canon=canon)
    gaps = bo_lib.known_gaps(weeks)

    for w in weeks:
        w["price"] = round(w["revenue_M_SAR"] * 1000 / w["tickets_K"], 2)

    latest, prev = weeks[-1], weeks[-2]

    # same-week-last-year (nearest captured Saturday within +/-10 days)
    latest_d = datetime.date.fromisoformat(latest["date_end"])
    target = latest_d - datetime.timedelta(days=364)
    yoy_week = None
    for w in weeks:
        d = datetime.date.fromisoformat(w["date_end"])
        if abs((d - target).days) <= 10:
            yoy_week = w
    def pct(now, base):
        return None if not base else round((now - base) / base * 100, 1)

    kpis = {}
    for key, label in [("tickets_K", "tickets"), ("revenue_M_SAR", "revenue"),
                       ("price", "price"), ("films", "films")]:
        kpis[label] = {
            "value": latest[key],
            "wow": pct(latest[key], prev[key]),
            "yoy": pct(latest[key], yoy_week[key]) if yoy_week else None,
            "spark": [w[key] for w in weeks[-12:]],
        }

    # full weekly series (for the pulse chart), gap-aware
    pulse = [{"date": w["date_end"], "tickets": w["tickets_K"],
              "revenue": w["revenue_M_SAR"], "price": w["price"]} for w in weeks]

    # YoY cumulative pace by ISO week-of-year
    pace = {}
    for w in weeks:
        y = w["year"]
        pace.setdefault(y, []).append((_iso_week(w["date_end"]), w["revenue_M_SAR"],
                                       w["tickets_K"]))
    yoy_pace = {}
    for y, items in pace.items():
        items.sort()
        cum_r = cum_t = 0.0
        series = []
        for wk, r, t in items:
            cum_r += r
            cum_t += t
            series.append({"week": wk, "cum_revenue": round(cum_r, 1),
                           "cum_tickets": round(cum_t, 1)})
        yoy_pace[y] = series

    # like-for-like pace comparison: same ISO weeks captured in both years
    def like_for_like(y1, y2, upto_week):
        w1 = {wk: r for wk, r, _ in pace.get(y1, []) if wk <= upto_week}
        w2 = {wk: r for wk, r, _ in pace.get(y2, []) if wk <= upto_week}
        common = sorted(set(w1) & set(w2))
        s1 = sum(w1[w] for w in common)
        s2 = sum(w2[w] for w in common)
        return {"weeks": len(common), "sum_a": round(s1, 1), "sum_b": round(s2, 1),
                "pct": pct(s2, s1)}
    this_week_no = _iso_week(latest["date_end"])
    pace_vs_2025 = like_for_like(2025, 2026, this_week_no)

    # per-week film rows, keyed
    by_week = defaultdict(list)
    for r in rows:
        by_week[r["week_end"]].append(r)
    latest_films = sorted(by_week[latest["date_end"]], key=lambda r: r["rank"])
    prev_films = {r["film_id"]: r for r in by_week[prev["date_end"]]}

    def film_name(r):
        return r["title_en"] or r["title_ar"]

    top10 = []
    for r in latest_films:
        p = prev_films.get(r["film_id"])
        top10.append({
            "rank": r["rank"], "film_id": r["film_id"],
            "title_en": r["title_en"], "title_ar": r["title_ar"],
            "name": film_name(r), "country": r["country"],
            "origin": origin_group(r["country"]),
            "weeks": r["weeks_in_cinema"],
            "week_revenue": r["week_revenue_M"], "week_tickets": r["week_tickets_K"],
            "total_revenue": r["total_revenue_M"], "total_tickets": r["total_tickets_K"],
            "prev_rank": p["rank"] if p else None,
            "wow_revenue": pct(r["week_revenue_M"], p["week_revenue_M"]) if p else None,
            "is_new": (r["weeks_in_cinema"] or 0) <= 1,
            "genre": canon.get(r["film_id"]).get("genre", "") if r["film_id"] else "",
        })

    new_openings = [f for f in top10 if f["is_new"]]
    movers = sorted([f for f in top10 if f["wow_revenue"] is not None],
                    key=lambda f: f["wow_revenue"], reverse=True)

    # films that dropped out of the top 10 this week
    latest_ids = {r["film_id"] for r in latest_films}
    dropped = [{"name": film_name(r), "rank": r["rank"]}
               for r in by_week[prev["date_end"]] if r["film_id"] not in latest_ids]

    # origin share by month (share of top-10 week revenue), last 13 months
    month_rev = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if not r["week_end"]:
            continue
        mkey = r["week_end"][:7]
        month_rev[mkey][origin_group(r["country"])] += r["week_revenue_M"] or 0
    months = sorted(month_rev)[-13:]
    origin_monthly = []
    for m in months:
        total = sum(month_rev[m].values()) or 1
        origin_monthly.append({
            "month": m,
            "total": round(sum(month_rev[m].values()), 1),
            "share": {g: round(month_rev[m][g] / total * 100, 1) for g in ORIGIN_GROUPS},
        })

    # origin share: latest week vs previous week (for the email "share shift")
    def week_share(films):
        tot = sum(f["week_revenue_M"] or 0 for f in films) or 1
        agg = defaultdict(float)
        for f in films:
            agg[origin_group(f["country"])] += f["week_revenue_M"] or 0
        return {g: round(agg[g] / tot * 100, 1) for g in ORIGIN_GROUPS}
    share_now = week_share(by_week[latest["date_end"]])
    share_prev = week_share(by_week[prev["date_end"]])

    # genre revenue, current calendar year (top-10 week revenue via canon genre)
    genre_rev = defaultdict(float)
    for r in rows:
        if r["year"] == latest["year"] and r["film_id"]:
            g = canon.get(r["film_id"]).get("genre") or "Untagged"
            genre_rev[g] += r["week_revenue_M"] or 0
    genre_year = sorted(((g, round(v, 1)) for g, v in genre_rev.items()),
                        key=lambda kv: kv[1], reverse=True)

    # film spotlight: highest-ranked Saudi film in the latest week,
    # falling back to the highest-ranked film overall
    spot_row = next((f for f in top10 if f["origin"] == "Saudi Arabia"), top10[0])
    spot_hist = sorted([r for r in rows if r["film_id"] == spot_row["film_id"]],
                       key=lambda r: r["week_end"])
    opening = spot_hist[0]
    spotlight = {
        "film_id": spot_row["film_id"], "name": spot_row["name"],
        "title_ar": spot_row["title_ar"], "country": spot_row["country"],
        "genre": spot_row["genre"],
        "weeks": [{"date": r["week_end"], "rank": r["rank"],
                   "revenue": r["week_revenue_M"], "tickets": r["week_tickets_K"]}
                  for r in spot_hist],
        "opening_revenue": opening["week_revenue_M"],
        "total_revenue": spot_hist[-1]["total_revenue_M"],
        "total_tickets": spot_hist[-1]["total_tickets_K"],
        "multiplier": round(spot_hist[-1]["total_revenue_M"] / opening["week_revenue_M"], 2)
        if opening["week_revenue_M"] else None,
    }

    # legs leaderboard: opening-week revenue -> latest cumulative, films with 3+ weeks
    first_seen, last_row, n_weeks = {}, {}, defaultdict(int)
    for r in sorted(rows, key=lambda r: r["week_end"]):
        if not r["film_id"]:
            continue
        first_seen.setdefault(r["film_id"], r)
        last_row[r["film_id"]] = r
        n_weeks[r["film_id"]] += 1
    legs = []
    for fid, first in first_seen.items():
        last = last_row[fid]
        if n_weeks[fid] >= 3 and (first["week_revenue_M"] or 0) >= 1 and last["total_revenue_M"]:
            legs.append({
                "film_id": fid, "name": first["title_en"] or first["title_ar"],
                "country": first["country"], "origin": origin_group(first["country"]),
                "opening": first["week_revenue_M"], "total": last["total_revenue_M"],
                "weeks": n_weeks[fid],
                "multiplier": round(last["total_revenue_M"] / first["week_revenue_M"], 2),
            })
    legs_by_total = sorted(legs, key=lambda f: f["total"], reverse=True)[:10]
    legs_by_mult = sorted(legs, key=lambda f: f["multiplier"], reverse=True)[:10]

    # data quality footer
    try:
        integ = json.loads((ROOT / "data" / "integrity_findings.json").read_text())
        integrity = {"passed": integ["summary"]["total_passed"],
                     "total": integ["summary"]["total_checks"],
                     "issues": integ["summary"]["total_issues"]}
    except OSError:
        integrity = None

    all_saturdays = []
    d = datetime.date.fromisoformat(weeks[0]["date_end"])
    while d <= latest_d:
        all_saturdays.append(d.isoformat())
        d += datetime.timedelta(days=7)

    # yearly totals (for the brief)
    yearly = []
    for y in sorted({w["year"] for w in weeks}):
        ws = [w for w in weeks if w["year"] == y]
        t = sum(w["tickets_K"] for w in ws)
        r = sum(w["revenue_M_SAR"] for w in ws)
        yearly.append({"year": y, "weeks": len(ws), "tickets": round(t, 1),
                       "revenue": round(r, 1), "price": round(r * 1000 / t, 2)})
    n_months = len({w["date_end"][:7] for w in weeks})
    countries = sorted({r["country"] for r in rows if r["country"]})

    return {
        "generated": datetime.date.today().isoformat(),
        "yearly": yearly, "n_months": n_months, "countries": countries,
        "n_film_rows": len(rows),
        "latest": latest, "prev": prev, "yoy_week": yoy_week,
        "kpis": kpis, "pulse": pulse,
        "yoy_pace": yoy_pace, "pace_vs_2025": pace_vs_2025,
        "top10": top10, "new_openings": new_openings, "movers": movers,
        "dropped": dropped,
        "origin_monthly": origin_monthly,
        "share_now": share_now, "share_prev": share_prev,
        "genre_year": genre_year,
        "spotlight": spotlight,
        "legs_by_total": legs_by_total, "legs_by_mult": legs_by_mult,
        "weeks_count": len(weeks), "gaps": gaps, "all_saturdays": all_saturdays,
        "integrity": integrity,
        "n_films": len({r["film_id"] for r in rows if r["film_id"]}),
        "first_week": weeks[0]["date_end"],
    }


# --------------------------------------------------------------------------
# formatting + SVG helpers (dashboard charts are hand-built inline SVG)
# --------------------------------------------------------------------------

MONTHS_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# series colors, fixed by entity (validated with the dataviz palette checker)
ORIGIN_COLOR = {
    "Saudi Arabia": "var(--c-saudi)", "Egypt": "var(--c-egypt)",
    "USA": "var(--c-usa)", "India": "var(--c-india)", "Other": "var(--c-other)",
}
ORIGIN_LABEL = {"Saudi Arabia": "Saudi", "Egypt": "Egyptian", "USA": "Hollywood",
                "India": "Indian", "Other": "Other"}


def fmt(x, dec=1):
    if x is None:
        return "—"
    s = f"{x:,.{dec}f}"
    return s[:-2] if s.endswith(".0") else s


def fmt_date(iso, year=False):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {MONTHS_EN[d.month]}" + (f" {d.year}" if year else "")


def delta_chip(p, up_good=True, vs=""):
    if p is None:
        return f'<span class="delta na">— <small>{vs}</small></span>'
    good = (p >= 0) == up_good
    arrow = "▲" if p >= 0 else "▼"
    cls = "good" if good else "bad"
    return (f'<span class="delta {cls}">{arrow} {fmt(abs(p))}%'
            f' <small>{vs}</small></span>')


def _scale(v, lo, hi, out_lo, out_hi):
    if hi == lo:
        return out_lo
    return out_lo + (v - lo) / (hi - lo) * (out_hi - out_lo)


def _nice_ticks(vmax, n=4):
    import math
    raw = vmax / n
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    ticks, t = [], 0
    while t <= vmax + 1e-9:
        ticks.append(round(t, 6))
        t += step
    if ticks[-1] < vmax:  # top tick must cover the data, or lines clip
        ticks.append(round(ticks[-1] + step, 6))
    return ticks


def sparkline(values, w=140, h=34, up_good=True):
    lo, hi = min(values), max(values)
    pad = 3
    pts = [(_scale(i, 0, len(values) - 1, pad, w - pad),
            _scale(v, lo, hi if hi > lo else lo + 1, h - pad, pad))
           for i, v in enumerate(values)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    cx, cy = pts[-1]
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'aria-hidden="true">'
            f'<polyline points="{path}" fill="none" stroke="var(--muted)" '
            f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" '
            f'opacity="0.7"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="var(--accent)" '
            f'stroke="var(--surface)" stroke-width="2"/></svg>')


def film_strip(all_saturdays, gaps, latest_date):
    """The signature: one frame per Saturday; hollow frames = never published."""
    gapset = set(gaps)
    n = len(all_saturdays)
    fw, gap, top, fh = 7.4, 2.4, 7, 18
    W = n * (fw + gap) + gap
    H = 32
    parts = [f'<svg class="strip" viewBox="0 0 {W:.0f} {H}" '
             f'preserveAspectRatio="none" role="img" '
             f'aria-label="Coverage: {n - len(gaps)} of {n} Saturdays captured">']
    # sprocket holes
    for i in range(n):
        x = gap + i * (fw + gap) + fw / 2
        for y in (2.5, H - 4.5):
            parts.append(f'<rect x="{x - 1.4:.1f}" y="{y}" width="2.8" height="2" '
                         f'rx="0.8" fill="var(--muted)" opacity="0.45"/>')
    for i, d in enumerate(all_saturdays):
        x = gap + i * (fw + gap)
        if d in gapset:
            parts.append(
                f'<rect x="{x:.1f}" y="{top}" width="{fw}" height="{fh}" rx="1.6" '
                f'fill="none" stroke="var(--muted)" stroke-width="1" opacity="0.55" '
                f'data-tip="{fmt_date(d, True)} — not published"/>')
        else:
            hot = d == latest_date
            fill = "var(--accent)" if hot else "var(--frame)"
            parts.append(
                f'<rect x="{x:.1f}" y="{top}" width="{fw}" height="{fh}" rx="1.6" '
                f'fill="{fill}" data-tip="{fmt_date(d, True)} — captured"/>')
    parts.append("</svg>")
    return "".join(parts)


def pulse_chart(pulse, gaps, w=1000, h=230):
    """Full-history weekly revenue line; the line breaks at coverage gaps."""
    ml, mr, mt, mb = 16, 74, 14, 30
    dates = [datetime.date.fromisoformat(p["date"]) for p in pulse]
    d0, d1 = dates[0], dates[-1]
    span = (d1 - d0).days or 1
    vmax = max(p["revenue"] for p in pulse)
    ticks = _nice_ticks(vmax)
    ymax = ticks[-1]

    def X(d):
        return _scale((d - d0).days, 0, span, ml, w - mr)

    def Y(v):
        return _scale(v, 0, ymax, h - mb, mt)

    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Weekly revenue, {fmt_date(pulse[0]["date"], True)} to '
             f'{fmt_date(pulse[-1]["date"], True)}">']
    for t in ticks:
        y = Y(t)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{w - mr}" y2="{y:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{w - mr + 8}" y="{y + 3.5:.1f}" class="tick">'
                     f'{fmt(t, 0)}M</text>')
    # x ticks: each January + each July
    for d in dates:
        if d.month in (1, 7) and d.day <= 7:
            x = X(d)
            label = f"{MONTHS_EN[d.month]} {d.year}" if d.month == 1 else MONTHS_EN[d.month]
            parts.append(f'<text x="{x:.1f}" y="{h - 8}" class="tick" '
                         f'text-anchor="middle">{label}</text>')
    # split into contiguous segments (break where >7 days pass)
    segs, cur = [], [pulse[0]]
    for a, b in zip(pulse, pulse[1:]):
        da = datetime.date.fromisoformat(a["date"])
        db = datetime.date.fromisoformat(b["date"])
        if (db - da).days > 7:
            segs.append(cur)
            cur = [b]
        else:
            cur.append(b)
    segs.append(cur)
    for seg in segs:
        pts = [(X(datetime.date.fromisoformat(p["date"])), Y(p["revenue"])) for p in seg]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if len(pts) > 1:
            area = (f'M {pts[0][0]:.1f},{Y(0):.1f} L ' + " L ".join(
                f"{x:.1f},{y:.1f}" for x, y in pts) + f' L {pts[-1][0]:.1f},{Y(0):.1f} Z')
            parts.append(f'<path d="{area}" fill="var(--c-usa)" opacity="0.10"/>')
        parts.append(f'<polyline points="{line}" fill="none" stroke="var(--c-usa)" '
                     f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    # gap notches on the baseline
    for g in gaps:
        x = X(datetime.date.fromisoformat(g))
        parts.append(f'<line x1="{x:.1f}" y1="{Y(0) + 1:.1f}" x2="{x:.1f}" '
                     f'y2="{Y(0) + 5:.1f}" stroke="var(--muted)" stroke-width="1.5" '
                     f'opacity="0.6"/>')
    # hover targets (one thin column per week)
    for p in pulse:
        d = datetime.date.fromisoformat(p["date"])
        x = X(d)
        tip = (f'w/e {fmt_date(p["date"], True)} · {fmt(p["revenue"])}M SAR · '
               f'{fmt(p["tickets"], 0)}K tickets · {fmt(p["price"], 2)} SAR avg')
        parts.append(f'<rect x="{x - 3.4:.1f}" y="{mt}" width="6.8" '
                     f'height="{h - mb - mt}" fill="transparent" data-tip="{tip}"/>')
    # peak + endpoint direct labels (selective)
    peak = max(pulse, key=lambda p: p["revenue"])
    px, py = X(datetime.date.fromisoformat(peak["date"])), Y(peak["revenue"])
    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="var(--c-usa)" '
                 f'stroke="var(--surface)" stroke-width="2"/>')
    parts.append(f'<text x="{px:.1f}" y="{max(py - 8, 12):.1f}" class="dlabel" '
                 f'text-anchor="middle">{fmt(peak["revenue"])}M · '
                 f'{fmt_date(peak["date"])}</text>')
    lx, ly = X(d1), Y(pulse[-1]["revenue"])
    parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="var(--c-usa)" '
                 f'stroke="var(--surface)" stroke-width="2"/>')
    parts.append(f'<text x="{lx + 8:.1f}" y="{ly + 4:.1f}" class="dlabel">'
                 f'{fmt(pulse[-1]["revenue"])}M</text>')
    parts.append("</svg>")
    return "".join(parts)


def pace_chart(yoy_pace, latest_year, w=1000, h=230):
    """Cumulative revenue by ISO week; current year emphasized, others context."""
    ml, mr, mt, mb = 16, 110, 14, 30
    vmax = max(s[-1]["cum_revenue"] for s in yoy_pace.values())
    ticks = _nice_ticks(vmax)
    ymax = ticks[-1]

    def X(wk):
        return _scale(wk, 1, 53, ml, w - mr)

    def Y(v):
        return _scale(v, 0, ymax, h - mb, mt)

    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Cumulative revenue pace by week of year">']
    for t in ticks:
        y = Y(t)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{w - mr}" y2="{y:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
    for wk, lab in [(1, "Jan"), (14, "Apr"), (27, "Jul"), (40, "Oct"), (53, "Dec")]:
        parts.append(f'<text x="{X(wk):.1f}" y="{h - 8}" class="tick" '
                     f'text-anchor="middle">{lab}</text>')
    styles = {}
    years = sorted(yoy_pace)
    for y in years:
        if y == latest_year:
            styles[y] = ("var(--c-pace)", 2.5, 1.0)
        else:
            styles[y] = ("var(--muted)", 2, 0.55 if y == latest_year - 1 else 0.35)
    for y in years:
        color, sw, op = styles[y]
        s = yoy_pace[y]
        pts = [(X(p["week"]), Y(p["cum_revenue"])) for p in s]
        line = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in pts)
        parts.append(f'<polyline points="{line}" fill="none" stroke="{color}" '
                     f'stroke-width="{sw}" opacity="{op}" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        for p in s:
            tip = f'{y} · week {p["week"]} · {fmt(p["cum_revenue"])}M cumulative'
            parts.append(f'<circle cx="{X(p["week"]):.1f}" cy="{Y(p["cum_revenue"]):.1f}" '
                         f'r="7" fill="transparent" data-tip="{tip}"/>')
        ex, ey = pts[-1]
        weight = ' font-weight="600"' if y == latest_year else ""
        parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="{color}" '
                     f'opacity="{op}" stroke="var(--surface)" stroke-width="2"/>')
        parts.append(f'<text x="{ex + 8:.1f}" y="{ey + 4:.1f}" class="dlabel"{weight}>'
                     f'{y} · {fmt(s[-1]["cum_revenue"], 0)}M</text>')
    parts.append("</svg>")
    return "".join(parts)


def origin_chart(origin_monthly, w=1000, h=250):
    """100%-share stacked columns by month, 2px surface gaps between segments."""
    ml, mr, mt, mb = 40, 16, 14, 30
    n = len(origin_monthly)
    slot = (w - ml - mr) / n
    bw = min(30, slot * 0.55)

    def Y(v):
        return _scale(v, 0, 100, h - mb, mt)

    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Revenue share by film origin, monthly">']
    for t in (0, 25, 50, 75, 100):
        parts.append(f'<text x="{ml - 8}" y="{Y(t) + 3.5:.1f}" class="tick" '
                     f'text-anchor="end">{t}%</text>')
        parts.append(f'<line x1="{ml}" y1="{Y(t):.1f}" x2="{w - mr}" y2="{Y(t):.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
    for i, m in enumerate(origin_monthly):
        cx = ml + slot * i + slot / 2
        y, mm = int(m["month"][:4]), int(m["month"][5:7])
        base = 0.0
        for g in ORIGIN_GROUPS:
            v = m["share"][g]
            if v <= 0:
                continue
            y0, y1 = Y(base), Y(base + v)
            hh = max(y0 - y1 - 2, 0.8)  # 2px surface gap between segments
            tip = (f'{MONTHS_EN[mm]} {y} · {ORIGIN_LABEL[g]} {fmt(v)}% · month total '
                   f'{fmt(m["total"])}M SAR')
            parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{y1 + 1:.1f}" width="{bw:.1f}" '
                         f'height="{hh:.1f}" rx="1.5" fill="{ORIGIN_COLOR[g]}" '
                         f'data-tip="{tip}"/>')
            base += v
        lab = MONTHS_EN[mm] + (f" {str(y)[2:]}" if mm == 1 or i == 0 else "")
        parts.append(f'<text x="{cx:.1f}" y="{h - 8}" class="tick" '
                     f'text-anchor="middle">{lab}</text>')
    parts.append("</svg>")
    return "".join(parts)


def spotlight_chart(spot, w=560, h=200):
    """Weekly revenue columns for one film, value on each cap, rank below."""
    ml, mr, mt, mb = 14, 14, 26, 36
    weeksd = spot["weeks"]
    n = len(weeksd)
    vmax = max(p["revenue"] for p in weeksd) or 1
    slot = (w - ml - mr) / n
    bw = min(24, slot * 0.6)

    def Y(v):
        return _scale(v, 0, vmax, h - mb, mt)

    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="{spot["name"]} weekly revenue">']
    for i, p in enumerate(weeksd):
        cx = ml + slot * i + slot / 2
        y1, y0 = Y(p["revenue"]), Y(0)
        tip = (f'w/e {fmt_date(p["date"], True)} · {fmt(p["revenue"])}M SAR · '
               f'{fmt(p["tickets"], 0)}K tickets · rank {p["rank"]}')
        parts.append(f'<path d="M {cx - bw / 2:.1f},{y0:.1f} L {cx - bw / 2:.1f},'
                     f'{y1 + 4:.1f} Q {cx - bw / 2:.1f},{y1:.1f} {cx - bw / 2 + 4:.1f},'
                     f'{y1:.1f} L {cx + bw / 2 - 4:.1f},{y1:.1f} Q {cx + bw / 2:.1f},'
                     f'{y1:.1f} {cx + bw / 2:.1f},{y1 + 4:.1f} '
                     f'L {cx + bw / 2:.1f},{y0:.1f} Z" '
                     f'fill="var(--c-saudi)" data-tip="{tip}"/>')
        parts.append(f'<text x="{cx:.1f}" y="{y1 - 6:.1f}" class="dlabel" '
                     f'text-anchor="middle">{fmt(p["revenue"])}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 22}" class="tick" '
                     f'text-anchor="middle">wk {i + 1}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 8}" class="tick" '
                     f'text-anchor="middle">#{p["rank"]}</text>')
    parts.append("</svg>")
    return "".join(parts)


def genre_chart(genre_year, w=560, h=None):
    rows = genre_year
    rh, gap2, ml = 26, 10, 150
    h = h or (len(rows) * (rh + gap2) + 16)
    vmax = max(v for _, v in rows) or 1
    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Revenue by genre, this year">']
    for i, (g, v) in enumerate(rows):
        y = 8 + i * (rh + gap2)
        bw = _scale(v, 0, vmax, 0, w - ml - 70)
        parts.append(f'<text x="{ml - 10}" y="{y + rh / 2 + 4}" class="blabel" '
                     f'text-anchor="end">{g}</text>')
        parts.append(f'<path d="M {ml},{y} L {ml + bw - 4:.1f},{y} Q {ml + bw:.1f},{y} '
                     f'{ml + bw:.1f},{y + 4} L {ml + bw:.1f},{y + rh - 4} Q '
                     f'{ml + bw:.1f},{y + rh} {ml + bw - 4:.1f},{y + rh} L {ml},{y + rh} Z" '
                     f'fill="var(--c-usa)" data-tip="{g}: {fmt(v)}M SAR in top-10 weeks"/>')
        parts.append(f'<text x="{ml + bw + 8:.1f}" y="{y + rh / 2 + 4}" class="dlabel">'
                     f'{fmt(v, 0)}M</text>')
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------

DASH_CSS = """
:root{
  --page:#f4f4f1; --surface:#fcfcfb; --ink:#141513; --ink2:#52514e;
  --muted:#898781; --grid:#e8e7e0; --hair:#e1e0d9; --frame:#3a3d38;
  --accent:#0a6c3c; --good:#006300; --bad:#c03434;
  --c-saudi:#008300; --c-egypt:#eda100; --c-usa:#2a78d6; --c-india:#eb6834;
  --c-other:#a09e97; --c-pace:#4a3aa7;
}
@media (prefers-color-scheme: dark){
  :root{
    --page:#0e0e0d; --surface:#1a1a19; --ink:#f4f4ef; --ink2:#c3c2b7;
    --muted:#8b8a83; --grid:#2b2b28; --hair:#32322f; --frame:#d8d7cf;
    --accent:#3dbd82; --good:#2fbd6f; --bad:#e66767;
    --c-saudi:#1a9e46; --c-egypt:#c98500; --c-usa:#3987e5; --c-india:#d95926;
    --c-other:#75746e; --c-pace:#9085e9;
  }
}
*{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{background:var(--page);color:var(--ink);
  font:15px/1.5 -apple-system,system-ui,"Segoe UI",sans-serif;
  padding:clamp(14px,3vw,40px) clamp(12px,3vw,28px)}
.wrap{max-width:1060px;margin:0 auto}
.serif{font-family:ui-serif,"New York",Georgia,serif}
.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace}
header.mast{padding:6px 2px 18px}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);font-weight:600;display:flex;gap:10px;align-items:baseline;
  flex-wrap:wrap}
.eyebrow .ar{letter-spacing:0;font-weight:500}
h1{font-family:ui-serif,"New York",Georgia,serif;font-weight:600;
  font-size:clamp(28px,5vw,44px);line-height:1.12;margin:6px 0 4px}
.standfirst{color:var(--ink2);max-width:64ch}
.standfirst b{color:var(--ink)}
.stripbox{margin:16px 0 8px}
.strip{width:100%;height:34px;display:block}
.stripcap{font-size:12px;color:var(--muted);margin-top:5px}
.stripcap .hollow{display:inline-block;width:9px;height:9px;border:1px solid
  var(--muted);border-radius:2px;vertical-align:-1px;margin:0 3px}
section{margin-top:26px}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:12px;
  padding:18px 20px 14px}
h2{font-family:ui-serif,"New York",Georgia,serif;font-weight:600;font-size:21px;
  margin-bottom:2px}
.sub{font-size:13px;color:var(--ink2);margin-bottom:12px}
.sub b{color:var(--ink)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--surface);border:1px solid var(--hair);border-radius:12px;
  padding:14px 16px 10px}
.kpi .lab{font-size:12.5px;color:var(--ink2)}
.kpi .val{font-size:30px;font-weight:600;letter-spacing:-.01em;margin:1px 0 2px}
.kpi .val small{font-size:15px;font-weight:500;color:var(--ink2)}
.kpi .deltas{display:flex;gap:10px;flex-wrap:wrap;font-size:12.5px;margin:2px 0 6px}
.delta{font-weight:600;font-variant-numeric:tabular-nums}
.delta small{color:var(--muted);font-weight:400}
.delta.good{color:var(--good)}.delta.bad{color:var(--bad)}.delta.na{color:var(--muted)}
.chart{width:100%;height:auto;display:block}
.scrollx{overflow-x:auto;-webkit-overflow-scrolling:touch}
.scrollx .chart{min-width:640px}
.tick{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;
  fill:var(--muted)}
.dlabel{font-size:11.5px;font-weight:600;fill:var(--ink2)}
.blabel{font-size:12.5px;fill:var(--ink2)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);
  margin:8px 2px 2px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;
  margin-right:5px;vertical-align:-1px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;
  color:var(--muted);font-weight:600;text-align:left;padding:6px 8px;
  border-bottom:1px solid var(--hair);white-space:nowrap}
td{padding:8px;border-bottom:1px solid var(--grid);font-size:13.5px;
  vertical-align:middle}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right}
.mv{font-weight:700;font-size:12px}
.mv.up{color:var(--good)}.mv.dn{color:var(--bad)}.mv.eq{color:var(--muted)}
.newb{font-size:10px;font-weight:700;letter-spacing:.08em;color:var(--accent);
  border:1px solid var(--accent);border-radius:4px;padding:1px 5px;
  vertical-align:1px;margin-left:6px;white-space:nowrap}
.odot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}
.tname{font-weight:600}
.tar{color:var(--ink2);font-size:12px;margin-left:6px}
.wbar{background:var(--grid);border-radius:3px;height:6px;min-width:60px;
  overflow:hidden}
.wbar i{display:block;height:100%;background:var(--c-usa);border-radius:3px}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:760px){.duo{grid-template-columns:1fr}}
.statrow{display:flex;gap:22px;flex-wrap:wrap;margin:6px 0 10px}
.stat .l{font-size:12px;color:var(--ink2)}
.stat .v{font-size:20px;font-weight:600}
.leglist{list-style:none}
.leglist li{display:flex;justify-content:space-between;gap:10px;padding:6px 0;
  border-bottom:1px solid var(--grid);font-size:13.5px}
.leglist li:last-child{border-bottom:none}
.leglist .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.leglist .v{font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
footer{margin:34px 2px 8px;padding-top:14px;border-top:1px solid var(--hair);
  font-size:12.5px;color:var(--muted);line-height:1.7}
footer a{color:var(--accent)}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--page);
  font-size:12px;line-height:1.4;padding:6px 9px;border-radius:7px;max-width:280px;
  opacity:0;transition:opacity .12s;z-index:9;box-shadow:0 2px 10px rgba(0,0,0,.25)}
@media print{ #tip{display:none} body{background:#fff} }
@media (prefers-reduced-motion: reduce){ #tip{transition:none} }
"""

TIP_JS = """
(function(){
  var tip=document.getElementById('tip');
  function show(e){
    var t=e.target.closest('[data-tip]'); if(!t){tip.style.opacity=0;return;}
    tip.textContent=t.getAttribute('data-tip'); tip.style.opacity=1;
    var x=Math.min(e.clientX+14, window.innerWidth-tip.offsetWidth-8);
    var y=e.clientY+16;
    if(y+tip.offsetHeight>window.innerHeight-8) y=e.clientY-tip.offsetHeight-10;
    tip.style.left=x+'px'; tip.style.top=y+'px';
  }
  document.addEventListener('mousemove',show,{passive:true});
  document.addEventListener('touchstart',function(e){
    var t=e.target.closest('[data-tip]'); if(!t){tip.style.opacity=0;return;}
    tip.textContent=t.getAttribute('data-tip'); tip.style.opacity=1;
    var c=e.touches[0];
    var x=Math.min(c.clientX+10, window.innerWidth-tip.offsetWidth-8);
    tip.style.left=x+'px'; tip.style.top=(c.clientY-tip.offsetHeight-14)+'px';
  },{passive:true});
})();
"""


def _legend(groups=ORIGIN_GROUPS):
    return ('<div class="legend">' + "".join(
        f'<span><i style="background:{ORIGIN_COLOR[g]}"></i>{ORIGIN_LABEL[g]}</span>'
        for g in groups) + "</div>")


def render_dashboard(m) -> Path:
    latest = m["latest"]
    k = m["kpis"]
    pace = m["pace_vs_2025"]
    pace_word = "ahead of" if (pace["pct"] or 0) >= 0 else "behind"
    spot = m["spotlight"]
    share = m["share_now"]

    kpi_defs = [
        ("Tickets sold", f'{fmt(k["tickets"]["value"], 0)}<small>K</small>', "tickets"),
        ("Box office revenue", f'{fmt(k["revenue"]["value"])}<small>M SAR</small>', "revenue"),
        ("Average ticket", f'{fmt(k["price"]["value"], 2)}<small> SAR</small>', "price"),
        ("Films in cinemas", f'{fmt(k["films"]["value"], 0)}', "films"),
    ]
    kpi_html = ""
    for lab, val, key in kpi_defs:
        kk = k[key]
        kpi_html += (
            f'<div class="kpi"><div class="lab">{lab}</div>'
            f'<div class="val">{val}</div>'
            f'<div class="deltas">{delta_chip(kk["wow"], vs="wk")}'
            f'{delta_chip(kk["yoy"], vs="yr")}</div>'
            f'{sparkline(kk["spark"])}</div>')

    max_wr = max(f["week_revenue"] or 0 for f in m["top10"]) or 1
    rows_html = ""
    for f in m["top10"]:
        if f["prev_rank"] is None:
            mv = '<span class="mv eq">·</span>' if not f["is_new"] else ""
        elif f["prev_rank"] > f["rank"]:
            mv = f'<span class="mv up">▲{f["prev_rank"] - f["rank"]}</span>'
        elif f["prev_rank"] < f["rank"]:
            mv = f'<span class="mv dn">▼{f["rank"] - f["prev_rank"]}</span>'
        else:
            mv = '<span class="mv eq">=</span>'
        new = '<span class="newb">NEW</span>' if f["is_new"] else ""
        ar = (f'<span class="tar" dir="rtl">{f["title_ar"]}</span>'
              if f["title_ar"] and f["title_ar"] != f["name"] else "")
        barw = (f["week_revenue"] or 0) / max_wr * 100
        rows_html += (
            f'<tr><td class="num">{f["rank"]}</td><td>{mv}</td>'
            f'<td><span class="odot" style="background:{ORIGIN_COLOR[f["origin"]]}">'
            f'</span><span class="tname">{f["name"]}</span>{ar}{new}</td>'
            f'<td class="num">{fmt(f["weeks"], 0)}</td>'
            f'<td class="num">{fmt(f["week_revenue"])}</td>'
            f'<td style="width:14%"><div class="wbar"><i style="width:{barw:.0f}%">'
            f'</i></div></td>'
            f'<td class="num">{fmt(f["total_revenue"])}</td>'
            f'<td class="num">{delta_chip(f["wow_revenue"], vs="")}</td></tr>')

    def leglist(items, valfn):
        lis = "".join(
            f'<li><span class="n"><span class="odot" '
            f'style="background:{ORIGIN_COLOR[f["origin"]]}"></span>{f["name"]}</span>'
            f'<span class="v">{valfn(f)}</span></li>' for f in items[:7])
        return f'<ul class="leglist">{lis}</ul>'

    openings = ", ".join(f'<b>{f["name"]}</b>' for f in m["new_openings"]) or "none"
    top_mover = m["movers"][0] if m["movers"] else None
    mover_txt = (f'<b>{top_mover["name"]}</b> (+{fmt(top_mover["wow_revenue"], 0)}% '
                 f'week on week)') if top_mover and top_mover["wow_revenue"] > 0 else "none"
    gaps = m["gaps"]
    integ = m["integrity"]
    integ_txt = (f'{integ["passed"]} of {integ["total"]} integrity checks clean · '
                 f'{integ["issues"]} soft flags' if integ else "integrity report missing")

    spot_ar = (f' <span dir="rtl">{spot["title_ar"]}</span>'
               if spot["title_ar"] and spot["title_ar"] != spot["name"] else "")

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Saudi Box Office — week ending {fmt_date(latest["date_end"], True)}</title>
<style>{DASH_CSS}</style>
</head><body><div class="wrap">

<header class="mast">
  <div class="eyebrow"><span>Saudi Box Office · Weekly Brief</span>
    <span class="ar" dir="rtl">{latest["week_label_ar"]}</span></div>
  <h1>Week ending Saturday {fmt_date(latest["date_end"], True)}</h1>
  <p class="standfirst"><b>{fmt(k["tickets"]["value"], 0)}K tickets</b> ·
    <b>{fmt(k["revenue"]["value"])}M SAR</b> — 2026 is running
    <b>{fmt(abs(pace["pct"]))}% {pace_word} 2025</b> over the same
    {pace["weeks"]} published weeks. Saudi films took
    <b>{fmt(share["Saudi Arabia"])}%</b> of this week's top-10 revenue.</p>
  <div class="stripbox">
    {film_strip(m["all_saturdays"], gaps, latest["date_end"])}
    <div class="stripcap">Every Saturday since {fmt_date(m["first_week"], True)},
    one frame each — {m["weeks_count"]} captured, {len(gaps)} never published
    (<span class="hollow"></span> hollow frames). Hover any frame for its date.</div>
  </div>
</header>

<section class="kpis">{kpi_html}</section>

<section class="card">
  <h2>The pulse</h2>
  <p class="sub">Weekly box office revenue, full history. The line breaks where
  the Commission published nothing; notches on the baseline mark those weeks.</p>
  <div class="scrollx">{pulse_chart(m["pulse"], gaps)}</div>
</section>

<section class="card">
  <h2>The race against last year</h2>
  <p class="sub">Cumulative revenue by week of the year. Like-for-like
  ({pace["weeks"]} matching published weeks so far): 2026 <b>{fmt(pace["sum_b"], 0)}M</b>
  vs 2025 <b>{fmt(pace["sum_a"], 0)}M</b> —
  <b>{fmt(abs(pace["pct"]))}% {"ahead" if (pace["pct"] or 0) >= 0 else "behind"}</b>.
  2024 capture starts in May.</p>
  <div class="scrollx">{pace_chart(m["yoy_pace"], latest["year"])}</div>
</section>

<section class="card">
  <h2>This week's top 10</h2>
  <p class="sub">New this week: {openings}. Biggest riser: {mover_txt}.</p>
  <div style="overflow-x:auto"><table>
  <thead><tr><th class="num">#</th><th></th><th>Film</th><th class="num">Wks</th>
  <th class="num">Week M SAR</th><th></th><th class="num">Total M SAR</th>
  <th class="num">vs last wk</th></tr></thead>
  <tbody>{rows_html}</tbody></table></div>
  {_legend()}
</section>

<section class="card">
  <h2>Who owns the screen</h2>
  <p class="sub">Share of top-10 revenue by film origin, month by month.
  This week: Saudi <b>{fmt(share["Saudi Arabia"])}%</b> ·
  Egyptian <b>{fmt(share["Egypt"])}%</b> · Hollywood <b>{fmt(share["USA"])}%</b>.</p>
  <div class="scrollx">{origin_chart(m["origin_monthly"])}</div>
  {_legend()}
</section>

<section class="duo">
  <div class="card">
    <h2>Film spotlight — {spot["name"]}</h2>
    <p class="sub">{spot["country"]}{" · " + spot["genre"] if spot["genre"] else ""}
    {spot_ar} — top {"Saudi " if spot["country"] == "Saudi Arabia" else ""}film
    in this week's chart.</p>
    <div class="statrow">
      <div class="stat"><div class="l">Total to date</div>
        <div class="v">{fmt(spot["total_revenue"])}M SAR</div></div>
      <div class="stat"><div class="l">Tickets</div>
        <div class="v">{fmt(spot["total_tickets"], 0)}K</div></div>
      <div class="stat"><div class="l">Legs (total ÷ opening)</div>
        <div class="v">{fmt(spot["multiplier"], 2)}×</div></div>
      <div class="stat"><div class="l">Weeks charted</div>
        <div class="v">{len(spot["weeks"])}</div></div>
    </div>
    {spotlight_chart(spot)}
  </div>
  <div class="card">
    <h2>What sells, by genre</h2>
    <p class="sub">Top-10 revenue by genre, {latest["year"]} to date
    (from the tagged film registry).</p>
    {genre_chart(m["genre_year"])}
  </div>
</section>

<section class="duo">
  <div class="card">
    <h2>Biggest films on record</h2>
    <p class="sub">Best cumulative total while charting, all {m["weeks_count"]} weeks.</p>
    {leglist(m["legs_by_total"], lambda f: fmt(f["total"]) + "M")}
  </div>
  <div class="card">
    <h2>Longest legs</h2>
    <p class="sub">Total ÷ opening week — the word-of-mouth champions
    (films with 3+ charted weeks and a 1M+ opening).</p>
    {leglist(m["legs_by_mult"], lambda f: fmt(f["multiplier"], 2) + "×")}
  </div>
</section>

<footer>
  Coverage {m["weeks_count"]} of {len(m["all_saturdays"])} Saturdays
  ({fmt_date(m["first_week"], True)} → {fmt_date(latest["date_end"], True)}) ·
  {m["n_films"]} films tracked · {integ_txt}.<br>
  Source: Saudi Film Commission weekly reports,
  <a href="https://film.moc.gov.sa/Box-Office">film.moc.gov.sa/Box-Office</a> ·
  tickets in thousands, revenue in millions of SAR ·
  <span class="mono">generated {m["generated"]}</span>
</footer>

</div><div id="tip" role="status"></div>
<script>{TIP_JS}</script>
</body></html>"""
    out = ROOT / "Saudi_Box_Office_Dashboard.html"
    out.write_text(html, encoding="utf-8")
    return out


# --------------------------------------------------------------------------
# data brief (analyst briefing, regenerated every run)
# --------------------------------------------------------------------------

def render_brief(m) -> Path:
    latest = m["latest"]
    yearly_rows = "\n".join(
        f'| {y["year"]} | {y["weeks"]} | {fmt(y["tickets"])} | {fmt(y["revenue"])} | '
        f'{fmt(y["price"], 2)} |' for y in m["yearly"])
    gaps = m["gaps"]
    clusters, cur = [], [gaps[0]]
    for a, b in zip(gaps, gaps[1:]):
        if (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days == 7:
            cur.append(b)
        else:
            clusters.append(cur)
            cur = [b]
    clusters.append(cur)
    gap_txt = "; ".join(
        (f"{fmt_date(c[0], True)}" if len(c) == 1 else
         f"{len(c)} weeks {fmt_date(c[0], True)} → {fmt_date(c[-1], True)}")
        for c in clusters)

    text = f"""# Saudi Box Office Dataset — Briefing for Analysis

This document describes `Saudi_Box_Office_Weekly.xlsx` so it can be analyzed without
seeing how it was built. Read this first, then work from the spreadsheet.
*Regenerated automatically on {m["generated"]} — numbers below are always current.*

## What the data is

Weekly cinema box office for Saudi Arabia, taken from the Saudi Film Commission's
official weekly reports (Ministry of Culture). One row per published week, plus the
top 10 films for each of those weeks. Source: https://film.moc.gov.sa/Box-Office

- **Coverage:** {fmt_date(m["first_week"], True)} to {fmt_date(latest["date_end"], True)}.
- **Weeks captured:** {m["weeks_count"]} (of {len(m["all_saturdays"])} Saturdays in the
  range — {len(gaps)} were never published; see caveat 3).
- **Unique films tracked:** {m["n_films"]} (via the canonical film registry — the same
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

### 1. Weekly Summary ({m["weeks_count"]} rows, newest first)
One row per week: week ending date, year/month/week keys, films in cinema, tickets
(thousands), revenue (million SAR), average ticket price, Arabic week label, trading
date range, source image and URL.

### 2. Top 10 Films ({m["n_film_rows"]} rows)
One row per film per week: week keys, rank 1–10, Arabic + English title, country,
weeks in cinema, that week's revenue/tickets, cumulative revenue/tickets, source image.

### 3. Films by Title ({m["n_films"]} rows)
One row per unique film (canonical identity), aggregated across all its weeks:
first/last week seen, weeks in top 10, best rank, best single-week revenue, best
cumulative revenue and tickets.

### 4. Monthly Totals ({m["n_months"]} rows)
Aggregated per year+month: weeks counted, tickets, revenue, avg films/week, avg price.

### 5. Yearly Totals
| Year | Weeks captured | Tickets (K) | Revenue (M SAR) | Avg ticket (SAR) |
|---|---|---|---|---|
{yearly_rows}

(First and last years are partial.)

### 6. About
Provenance and method notes.

### 7. Coverage Calendar
Per-Saturday capture map — green captured, red missing. Use it to see exactly which
weeks any period is missing before summing.

## Countries present
{", ".join(m["countries"])}.

## Caveats the analyst must respect

1. **Partial years.** Capture starts {fmt_date(m["first_week"], True)}; the current
   year runs through {fmt_date(latest["date_end"], True)}. Do not compare full-year
   totals without normalizing (use weeks-captured, or compare like periods).
2. **Weeks captured per year differ** ({" / ".join(str(y["weeks"]) for y in m["yearly"])}).
   Divide by weeks captured for fair per-week comparisons, not by 52.
3. **History has gaps — exactly {len(gaps)} missing Saturdays:** {gap_txt}.
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
"""
    out = ROOT / "Saudi_Box_Office_DATA_BRIEF.md"
    out.write_text(text, encoding="utf-8")
    return out


# --------------------------------------------------------------------------
# static charts (matplotlib PNGs — used by the rich email twin, reusable in decks)
# --------------------------------------------------------------------------

LIGHT = {"page": "#ffffff", "ink": "#141513", "ink2": "#52514e", "muted": "#898781",
         "grid": "#e8e7e0", "saudi": "#008300", "egypt": "#eda100", "usa": "#2a78d6",
         "india": "#eb6834", "other": "#a09e97", "pace": "#4a3aa7"}


def render_charts(m) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    CHARTS.mkdir(parents=True, exist_ok=True)
    C = LIGHT
    plt.rcParams.update({
        "font.family": "Helvetica Neue", "text.color": C["ink"],
        "axes.edgecolor": C["grid"], "axes.labelcolor": C["ink2"],
        "xtick.color": C["muted"], "ytick.color": C["muted"],
        "axes.grid": True, "grid.color": C["grid"], "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "figure.facecolor": C["page"],
        "axes.facecolor": C["page"], "font.size": 10,
    })
    out = []

    # 1. pulse — weekly revenue, line broken at gaps
    fig, ax = plt.subplots(figsize=(8, 3), dpi=200)
    dates = [datetime.date.fromisoformat(p["date"]) for p in m["pulse"]]
    revs = [p["revenue"] for p in m["pulse"]]
    seg_x, seg_y = [dates[0]], [revs[0]]
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days > 7:
            ax.plot(seg_x, seg_y, color=C["usa"], lw=1.8, solid_capstyle="round")
            ax.fill_between(seg_x, seg_y, color=C["usa"], alpha=0.08)
            seg_x, seg_y = [], []
        seg_x.append(dates[i])
        seg_y.append(revs[i])
    ax.plot(seg_x, seg_y, color=C["usa"], lw=1.8, solid_capstyle="round")
    ax.fill_between(seg_x, seg_y, color=C["usa"], alpha=0.08)
    ax.plot([dates[-1]], [revs[-1]], "o", ms=5, color=C["usa"])
    ax.annotate(f'{fmt(revs[-1])}M', (dates[-1], revs[-1]), textcoords="offset points",
                xytext=(6, 2), fontsize=9, fontweight="bold", color=C["ink2"])
    ax.set_ylim(0, None)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.set_title("Weekly box office revenue, M SAR — full history",
                 loc="left", fontsize=11, fontweight="bold", color=C["ink"])
    fig.tight_layout()
    p = CHARTS / "pulse.png"
    fig.savefig(p)
    plt.close(fig)
    out.append(p)

    # 2. YoY cumulative pace
    fig, ax = plt.subplots(figsize=(8, 3), dpi=200)
    latest_year = m["latest"]["year"]
    for y, s in sorted(m["yoy_pace"].items()):
        wk = [p["week"] for p in s]
        cum = [p["cum_revenue"] for p in s]
        if y == latest_year:
            ax.plot(wk, cum, color=C["pace"], lw=2.4)
        else:
            ax.plot(wk, cum, color=C["muted"],
                    lw=1.6, alpha=0.65 if y == latest_year - 1 else 0.4)
        ax.annotate(f'{y} · {fmt(cum[-1], 0)}M', (wk[-1], cum[-1]),
                    textcoords="offset points", xytext=(6, -2), fontsize=9,
                    fontweight="bold" if y == latest_year else "normal",
                    color=C["ink2"])
    ax.set_xlim(1, 60)
    ax.set_ylim(0, None)
    ax.set_xticks([1, 14, 27, 40, 53])
    ax.set_xticklabels(["Jan", "Apr", "Jul", "Oct", "Dec"])
    ax.set_title("Cumulative revenue by week of year, M SAR",
                 loc="left", fontsize=11, fontweight="bold", color=C["ink"])
    fig.tight_layout()
    p = CHARTS / "pace.png"
    fig.savefig(p)
    plt.close(fig)
    out.append(p)

    # 3. origin share, monthly stack
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=200)
    months = [x["month"] for x in m["origin_monthly"]]
    xs = range(len(months))
    base = [0.0] * len(months)
    colors = {"Saudi Arabia": C["saudi"], "Egypt": C["egypt"], "USA": C["usa"],
              "India": C["india"], "Other": C["other"]}
    for g in ORIGIN_GROUPS:
        vals = [x["share"][g] for x in m["origin_monthly"]]
        ax.bar(xs, vals, bottom=base, width=0.62, color=colors[g],
               label=ORIGIN_LABEL[g], edgecolor=C["page"], linewidth=1.2)
        base = [b + v for b, v in zip(base, vals)]
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{MONTHS_EN[int(mm[5:7])]}" +
                        (f" {mm[2:4]}" if int(mm[5:7]) == 1 or i == 0 else "")
                        for i, mm in enumerate(months)], fontsize=8.5)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=5, frameon=False,
              fontsize=9)
    ax.set_title("Share of top-10 revenue by film origin",
                 loc="left", fontsize=11, fontweight="bold", color=C["ink"])
    fig.tight_layout()
    p = CHARTS / "origin_share.png"
    fig.savefig(p)
    plt.close(fig)
    out.append(p)
    return out


# --------------------------------------------------------------------------
# weekly email digest
#   email_draft_body.html — pure HTML/CSS, no images (Gmail strips data URIs)
#   weekly_email.html     — rich local twin with the PNG charts embedded
# --------------------------------------------------------------------------

EA = 'style="color:#0c7a44;font-weight:bold"'   # good delta, email-safe inline
EB = 'style="color:#c03434;font-weight:bold"'   # bad delta


def _edelta(p, up_good=True):
    if p is None:
        return '<span style="color:#898781">—</span>'
    good = (p >= 0) == up_good
    return (f'<span {EA if good else EB}>{"▲" if p >= 0 else "▼"} '
            f'{fmt(abs(p))}%</span>')


def render_email(m) -> tuple:
    latest = m["latest"]
    k = m["kpis"]
    pace = m["pace_vs_2025"]
    ahead = "ahead of" if (pace["pct"] or 0) >= 0 else "behind"
    subject = (f'Saudi Box Office — w/e {fmt_date(latest["date_end"], True)}: '
               f'{fmt(k["tickets"]["value"], 0)}K tickets, '
               f'{fmt(k["revenue"]["value"])}M SAR '
               f'({"+" if k["revenue"]["wow"] >= 0 else ""}{fmt(k["revenue"]["wow"])}% WoW)')

    td = 'style="padding:7px 10px;border-bottom:1px solid #eceae4;font-size:14px"'
    tdr = td[:-1] + ';text-align:right"'
    th = ('style="padding:6px 10px;font-size:11px;text-transform:uppercase;'
          'letter-spacing:.05em;color:#898781;text-align:left"')
    thr = th[:-1].replace("text-align:left", "text-align:right") + '"'

    kpi_rows = ""
    for lab, key, unit, dec, up_good in [
            ("Tickets sold", "tickets", "K", 0, True),
            ("Revenue", "revenue", "M SAR", 1, True),
            ("Average ticket", "price", "SAR", 2, True),
            ("Films in cinemas", "films", "", 0, True)]:
        kk = k[key]
        kpi_rows += (f'<tr><td {td}>{lab}</td>'
                     f'<td {tdr}><b>{fmt(kk["value"], dec)}{unit and " " + unit}</b></td>'
                     f'<td {tdr}>{_edelta(kk["wow"], up_good)}</td>'
                     f'<td {tdr}>{_edelta(kk["yoy"], up_good)}</td></tr>')

    max_wr = max(f["week_revenue"] or 0 for f in m["top10"]) or 1
    film_rows_html = ""
    for f in m["top10"][:5]:
        w = (f["week_revenue"] or 0) / max_wr * 100
        newb = (' <span style="font-size:10px;color:#0c7a44;border:1px solid #0c7a44;'
                'border-radius:3px;padding:0 4px;font-weight:bold">NEW</span>'
                if f["is_new"] else "")
        film_rows_html += (
            f'<tr><td {tdr}>{f["rank"]}</td>'
            f'<td {td}><b>{f["name"]}</b>{newb}</td>'
            f'<td {tdr}>{fmt(f["week_revenue"])}M</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #eceae4;width:110px">'
            f'<div style="background:#eceae4;border-radius:3px;height:8px">'
            f'<div style="background:#2a78d6;border-radius:3px;height:8px;'
            f'width:{w:.0f}%"></div></div></td>'
            f'<td {tdr}>{_edelta(f["wow_revenue"])}</td></tr>')

    sh_now, sh_prev = m["share_now"], m["share_prev"]
    share_bits = []
    for g in ("Saudi Arabia", "Egypt", "USA"):
        d = round(sh_now[g] - sh_prev[g], 1)
        arrow = "▲" if d >= 0 else "▼"
        share_bits.append(f'<b>{ORIGIN_LABEL[g]} {fmt(sh_now[g])}%</b> '
                          f'({arrow}{fmt(abs(d))} pt)')
    share_line = " · ".join(share_bits)

    openings = ", ".join(f'<b>{f["name"]}</b> ({f["country"]}, opened at '
                         f'{fmt(f["week_revenue"])}M)' for f in m["new_openings"]) or "none"
    mover = m["movers"][0] if m["movers"] and m["movers"][0]["wow_revenue"] > 0 else None
    mover_line = (f'<b>{mover["name"]}</b>, +{fmt(mover["wow_revenue"], 0)}% week on week'
                  if mover else "no big risers")
    dropped = ", ".join(d["name"] for d in m["dropped"]) or "none"
    spot = m["spotlight"]

    body_core = f"""
<div style="max-width:600px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;
color:#141513;background:#ffffff;padding:8px 4px">
  <p style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:#0c7a44;font-weight:bold;margin:14px 0 2px">Saudi Box Office · Weekly Digest</p>
  <h1 style="font-size:24px;margin:0 0 4px;font-family:Georgia,'Times New Roman',serif">
  Week ending Saturday {fmt_date(latest["date_end"], True)}</h1>
  <p style="font-size:14px;color:#52514e;margin:0 0 14px">
  {fmt(k["tickets"]["value"], 0)}K tickets · {fmt(k["revenue"]["value"])}M SAR ·
  2026 running <b>{fmt(abs(pace["pct"]))}% {ahead} 2025</b> like-for-like.</p>

  <table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;
  margin-bottom:18px">
    <tr><th {th}>This week</th><th {thr}>Value</th><th {thr}>vs last wk</th>
    <th {thr}>vs last yr</th></tr>
    {kpi_rows}
  </table>

  <h2 style="font-size:17px;margin:0 0 6px;font-family:Georgia,serif">Top 5 films</h2>
  <table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;
  margin-bottom:6px">
    <tr><th {thr}>#</th><th {th}>Film</th><th {thr}>Week</th><th {th}></th>
    <th {thr}>WoW</th></tr>
    {film_rows_html}
  </table>
  <p style="font-size:12px;color:#898781;margin:0 0 18px">Bars compare each film's
  week revenue to this week's #1.</p>

  <table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;
  background:#f6f6f2;border-radius:8px;margin-bottom:18px">
    <tr><td style="padding:12px 14px;font-size:13.5px;line-height:1.6">
      <b>New this week:</b> {openings}<br>
      <b>Biggest riser:</b> {mover_line}<br>
      <b>Dropped out:</b> {dropped}<br>
      <b>Screen share:</b> {share_line}<br>
      <b>Spotlight:</b> {spot["name"]} — {fmt(spot["total_revenue"])}M SAR total,
      {fmt(spot["multiplier"], 2)}× its opening week.
    </td></tr>
  </table>
"""
    footer = f"""
  <p style="font-size:12px;color:#898781;border-top:1px solid #eceae4;
  padding-top:10px;line-height:1.6">
  Full dashboard (charts, history, spotlight): open
  <b>Saudi_Box_Office_Dashboard.html</b> in the box office folder on the Mac.<br>
  Coverage {m["weeks_count"]} of {len(m["all_saturdays"])} Saturdays ·
  {m["n_films"]} films tracked · tickets in thousands, revenue in millions SAR ·
  generated {m["generated"]}.</p>
</div>"""

    draft_body = body_core + footer
    (REPORTS / "email_draft_body.html").write_text(draft_body, encoding="utf-8")
    (REPORTS / "email_subject.txt").write_text(subject, encoding="utf-8")

    # plain-text digest — what the Mac's Mail app auto-sends (standing yes, 13 Jul 2026)
    def updown(p, dec=1):
        if p is None:
            return "n/a"
        return f'{"up" if p >= 0 else "down"} {fmt(abs(p), dec)}%'
    plain_films = "\n".join(
        f'{f["rank"]}. {f["name"]} — {fmt(f["week_revenue"])}M '
        f'({"NEW" if f["is_new"] else updown(f["wow_revenue"]) if f["wow_revenue"] is not None else "—"})'
        for f in m["top10"][:5])
    share_plain = " · ".join(
        f'{ORIGIN_LABEL[g]} {fmt(sh_now[g])}% '
        f'({"+" if sh_now[g] - sh_prev[g] >= 0 else "-"}{fmt(abs(round(sh_now[g] - sh_prev[g], 1)))}pt)'
        for g in ("Saudi Arabia", "Egypt", "USA"))
    plain = f"""SAUDI BOX OFFICE — WEEKLY DIGEST
Week ending Saturday {fmt_date(latest["date_end"], True)}

{fmt(k["tickets"]["value"], 0)}K tickets · {fmt(k["revenue"]["value"])}M SAR · 2026 running {fmt(abs(pace["pct"]))}% {ahead} 2025 like-for-like.

THIS WEEK
- Tickets sold: {fmt(k["tickets"]["value"], 0)}K ({updown(k["tickets"]["wow"])} vs last wk, {updown(k["tickets"]["yoy"])} vs last yr)
- Revenue: {fmt(k["revenue"]["value"])}M SAR ({updown(k["revenue"]["wow"])} wk, {updown(k["revenue"]["yoy"])} yr)
- Average ticket: {fmt(k["price"]["value"], 2)} SAR ({updown(k["price"]["wow"])} wk, {updown(k["price"]["yoy"])} yr)
- Films in cinemas: {fmt(k["films"]["value"], 0)} ({updown(k["films"]["wow"])} wk, {updown(k["films"]["yoy"])} yr)

TOP 5 FILMS (week revenue)
{plain_films}

New this week: {", ".join(f'{f["name"]} ({f["country"]}, {fmt(f["week_revenue"])}M)' for f in m["new_openings"]) or "none"}
Biggest riser: {mover["name"] + f', +{fmt(mover["wow_revenue"], 0)}% week on week' if mover else "none"}
Dropped out: {dropped}
Screen share: {share_plain}
Spotlight: {spot["name"]} — {fmt(spot["total_revenue"])}M SAR total, {fmt(spot["multiplier"], 2)}x its opening week.

Full dashboard: attached — tap Saudi_Box_Office_Dashboard.html to open it (works on Mac and iPhone).
Coverage {m["weeks_count"]} of {len(m["all_saturdays"])} Saturdays · {m["n_films"]} films tracked · tickets in thousands, revenue in millions SAR.
Sent automatically by the box office pipeline · generated {m["generated"]}.
"""
    (REPORTS / "email_plain.txt").write_text(plain, encoding="utf-8")

    # rich twin: same digest + embedded chart images (data URIs, self-contained)
    import base64
    imgs = ""
    for name, cap in [("pulse.png", "Weekly revenue, full history"),
                      ("pace.png", "The race against last year"),
                      ("origin_share.png", "Who owns the screen")]:
        p = CHARTS / name
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            imgs += (f'<img src="data:image/png;base64,{b64}" alt="{cap}" '
                     f'style="width:100%;max-width:600px;display:block;'
                     f'margin:0 0 14px;border:1px solid #eceae4;border-radius:8px">')
    rich = (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{subject}</title></head><body style="margin:0;background:#ffffff">'
            + body_core + imgs + footer + "</body></html>")
    (REPORTS / "weekly_email.html").write_text(rich, encoding="utf-8")
    return subject, REPORTS / "email_draft_body.html", REPORTS / "weekly_email.html"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    m = compute()
    dash = render_dashboard(m)
    brief = render_brief(m)
    try:
        charts = render_charts(m)
    except ImportError:
        charts = []
        print("matplotlib missing — skipped PNG charts (email twin will have no images)")
    subject, draft, rich = render_email(m)
    print(f"insights: dashboard, brief, {len(charts)} charts, email digest rebuilt "
          f"(w/e {m['latest']['date_end']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
