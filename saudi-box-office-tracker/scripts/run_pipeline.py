#!/usr/bin/env python3
"""Orchestrator: everything after vision extraction, in order.

Usage:
    python3 scripts/run_pipeline.py                 # full run
    python3 scripts/run_pipeline.py --check-films   # film resolution check only
    python3 scripts/run_pipeline.py --skip-insights # fast Excel-only rebuild
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# Self-heal: always run under the project's own virtual environment so the
# pipeline doesn't break when Homebrew re-points the system `python3` to a new
# version that lacks openpyxl/Pillow/matplotlib. If a .venv exists and we're not
# already inside it, re-exec this script with the venv's Python.
_VENV = SCRIPTS.parent / ".venv"
_VENV_PY = _VENV / "bin" / "python"
# Compare sys.prefix (not the executable — a venv's python symlinks back to the
# base interpreter, so resolving the path would make them look identical).
if _VENV_PY.exists() and Path(sys.prefix).resolve() != _VENV.resolve():
    import os
    os.execv(str(_VENV_PY), [str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])

import bo_lib


def check_films() -> int:
    unresolved = bo_lib.unresolved_titles()
    if unresolved:
        print(f"UNRESOLVED FILMS ({len(unresolved)}) — add to config/films_canonical.json:")
        for (en, ar), week in unresolved:
            print(f"  en={en!r}  ar={ar!r}  (last seen {week})")
        return 1
    print("All film rows resolve to canonical IDs.")
    return 0


def run(script: str) -> None:
    print(f"\n=== {script} ===")
    subprocess.run([sys.executable, str(SCRIPTS / script)], check=True)


def main() -> int:
    args = set(sys.argv[1:])
    if "--check-films" in args:
        return check_films()

    # 1. film resolution (fail fast — extraction added an unknown title)
    if check_films() != 0:
        print("\nPipeline stopped: resolve the films above first.")
        return 1

    # 2. integrity checks + human-readable report
    run("integrity_check.py")

    # 3. main workbook
    run("build_excel.py")

    # 4. coverage calendar sheet (post-processes the workbook)
    run("build_calendar.py")

    # 5. insights layer (dashboard, brief, email, charts) — Phase 2
    if "--skip-insights" not in args:
        if (SCRIPTS / "build_insights.py").exists():
            run("build_insights.py")
        else:
            print("\n(build_insights.py not present yet — Phase 2)")

    # 6. Google Sheet export — Phase 2
    if (SCRIPTS / "export_films_tagged.py").exists():
        run("export_films_tagged.py")

    # 7. summary
    weeks = bo_lib.load_weeks()
    weeks.sort(key=lambda w: w.get("date_end") or "")
    gaps = bo_lib.known_gaps(weeks)
    latest = weeks[-1]
    print(
        f"\nSUMMARY: dataset current through {latest['date_end']} "
        f"({len(weeks)} weeks, {len(gaps)} known missing). "
        f"Latest week: {latest.get('films')} films, {latest.get('tickets_K')}K tickets, "
        f"{latest.get('revenue_M_SAR')}M SAR. Workbook, calendar and integrity report rebuilt."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
