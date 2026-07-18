#!/usr/bin/env python3
"""Crop a weekly report image into the three pieces Claude reads with vision:
header band (summary numbers) and two film strips (ranks 1–5, ranks 6–10).

Usage:
    python3 scripts/crop_report.py images/<report>.png [out_dir]

Writes <out_dir>/hdr.png, films_top.png, films_bot.png (default out_dir: /tmp).
Crop ratios per KNOWLEDGE_BASE.md: header = top 25% (upscaled 2x),
top strip = 27%–64%, bottom strip = 60%–100%.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp")
    out_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(src)
    w, h = img.size

    hdr = img.crop((0, 0, w, int(h * 0.25)))
    hdr = hdr.resize((hdr.width * 2, hdr.height * 2))
    hdr.save(out_dir / "hdr.png")

    img.crop((0, int(h * 0.27), w, int(h * 0.64))).save(out_dir / "films_top.png")
    img.crop((0, int(h * 0.60), w, h)).save(out_dir / "films_bot.png")

    print(f"Cropped {src.name} ({w}x{h}) -> {out_dir}/hdr.png, films_top.png, films_bot.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
