#!/usr/bin/env python3
"""Render the isolated HTML cover template to a PNG. Does not call DALL-E."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cover_template.render import SAMPLE_DATA, render_cover_png_sync  # noqa: E402


def main() -> None:
    out = ROOT / "scratch" / "cover_template_preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    render_cover_png_sync(SAMPLE_DATA, output_path=out)
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
