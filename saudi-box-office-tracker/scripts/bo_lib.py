#!/usr/bin/env python3
"""Shared library for the Saudi Box Office pipeline.

Raw JSONL files are append-only and never rewritten; film identity is resolved
at load time against config/films_canonical.json.
"""
from __future__ import annotations
import json
import re
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_WEEKS = ROOT / "data" / "weekly_data.jsonl"
SRC_FILMS = ROOT / "data" / "films_data.jsonl"
CANON = ROOT / "config" / "films_canonical.json"
URL_QUIRKS = ROOT / "config" / "url_quirks.json"
EID_CAL = ROOT / "config" / "eid_calendar.json"

PAGE = "https://film.moc.gov.sa/Box-Office"
IMG_BASE = "https://film.moc.gov.sa/-/media/Project/Ministries/Commission/film/Tickets/Tickets/"
IMG_BASE_ALT = "https://film.moc.gov.sa/-/media/"

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


# ---------- loading ----------

def load_records(path: Path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_weeks():
    return load_records(SRC_WEEKS)


def load_films_raw():
    return load_records(SRC_FILMS)


# ---------- canonical film identity ----------

def normalize_title(s: str) -> str:
    s = s or ""
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = s.translate(_AR_DIGITS)
    s = re.sub(r"[؟،؛ـ]", "", s)  # Arabic punctuation / tatweel
    return re.sub(r"[^0-9A-Za-z؀-ۿ]+", "", s).lower()


class Canon:
    def __init__(self, path: Path = CANON):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.films = self.data["films"]
        self._by_en = {}
        self._by_ar = {}
        for slug, f in self.films.items():
            for alias in f.get("aliases", []):
                en = normalize_title(alias.get("title_en", ""))
                ar = normalize_title(alias.get("title_ar", ""))
                if en:
                    self._by_en[en] = slug
                if ar:
                    self._by_ar[ar] = slug
            # the canonical titles themselves also resolve
            if normalize_title(f.get("title_en", "")):
                self._by_en.setdefault(normalize_title(f["title_en"]), slug)
            if normalize_title(f.get("title_ar", "")):
                self._by_ar.setdefault(normalize_title(f["title_ar"]), slug)

    def resolve(self, title_en: str, title_ar: str):
        """Return film_id (slug) or None if unresolved."""
        en = normalize_title(title_en)
        ar = normalize_title(title_ar)
        return self._by_en.get(en) or self._by_ar.get(ar) or None

    def get(self, film_id: str) -> dict:
        return self.films[film_id]


def load_canon() -> Canon:
    return Canon()


# ---------- flat per-film-per-week rows ----------

def film_rows(weeks=None, films_by_week=None, canon: Canon | None = None):
    """Flat rows, one per (week, rank), newest week first, rank ascending.

    Each row carries film_id (resolved via the canonical registry; None if
    unresolved) alongside the raw titles.
    """
    weeks = weeks if weeks is not None else load_weeks()
    films_by_week = films_by_week if films_by_week is not None else load_films_raw()
    canon = canon or load_canon()

    week_by_filename = {w["filename"]: w for w in weeks}
    rows = []
    for fw in films_by_week:
        fname = fw["filename"]
        wkrec = week_by_filename.get(fname, {})
        week_end = fw.get("date_end") or wkrec.get("date_end") or ""
        year = wkrec.get("year") or (int(week_end[:4]) if week_end else "")
        month = wkrec.get("month") or (int(week_end[5:7]) if week_end else "")
        for film in fw.get("films", []):
            en = (film.get("title_en") or "").strip()
            ar = (film.get("title_ar") or "").strip()
            rows.append({
                "week_end": week_end, "year": year, "month": month,
                "rank": film.get("rank"),
                "film_id": canon.resolve(en, ar),
                "title_ar": ar, "title_en": en,
                "country": film.get("country") or "",
                "weeks_in_cinema": film.get("weeks_in_cinema"),
                "week_revenue_M": film.get("week_revenue_M"),
                "week_tickets_K": film.get("week_tickets_K"),
                "total_revenue_M": film.get("total_revenue_M"),
                "total_tickets_K": film.get("total_tickets_K"),
                "filename": fname,
            })
    # stable two-pass sort: rank ascending within week, newest week first
    rows.sort(key=lambda r: (r["rank"] or 0))
    rows.sort(key=lambda r: r["week_end"] or "", reverse=True)
    return rows


def unresolved_titles(rows=None):
    """Unique (title_en, title_ar) pairs that don't resolve to a film_id."""
    rows = rows if rows is not None else film_rows()
    seen = {}
    for r in rows:
        if r["film_id"] is None and (r["title_en"] or r["title_ar"]):
            seen[(r["title_en"], r["title_ar"])] = r["week_end"]
    return sorted(seen.items(), key=lambda kv: kv[1], reverse=True)


# ---------- provenance / coverage ----------

def img_url(filename: str) -> str:
    base = filename.split("_", 1)[1] if "_" in filename else filename
    try:
        quirks = set(json.loads(URL_QUIRKS.read_text())["root_path_files"])
    except (OSError, KeyError, json.JSONDecodeError):
        quirks = set()
    return (IMG_BASE_ALT if base in quirks else IMG_BASE) + base


def known_gaps(weeks=None):
    """Missing Saturdays between first and last captured week, as a list of
    ISO dates. Computed from data — no hardcoded lists."""
    weeks = weeks if weeks is not None else load_weeks()
    have = sorted({w["date_end"] for w in weeks if w.get("date_end")})
    if not have:
        return []
    first = datetime.date.fromisoformat(have[0])
    last = datetime.date.fromisoformat(have[-1])
    have_set = set(have)
    gaps = []
    d = first
    while d <= last:
        if d.isoformat() not in have_set:
            gaps.append(d.isoformat())
        d += datetime.timedelta(days=7)
    return gaps


def eid_window(date: datetime.date) -> str:
    """Tag a date with its seasonal window from config/eid_calendar.json.
    Returns 'normal' if the config doesn't exist yet (Phase 3)."""
    try:
        cal = json.loads(EID_CAL.read_text(encoding="utf-8"))
    except OSError:
        return "normal"
    for w in cal.get("windows", []):
        if w["start"] <= date.isoformat() <= w["end"]:
            return w["tag"]
    return "normal"
