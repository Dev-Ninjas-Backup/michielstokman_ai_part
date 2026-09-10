"""Build photo-tear-hole mask (+ matching torn border) from authoritative fill art.

Source of truth:
  assets/photo-fill-mask.png  — white = photo visible (white-inner-right-cropped)
  assets/photo-torn-border.png — white stroke only (decorative border)

Outputs (torn-inner pixel size, used under .photo-torn-inner):
  assets/photo-tear-hole-mask-alpha.png
  assets/photo-tear-hole-mask.png
  assets/photo-torn-border-fit.png  — border resized to the same canvas
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "cover_template"
ASSETS = PACKAGE / "assets"

# Match .photo-frame / .photo-torn / .photo-torn-inner CSS (rounded).
FRAME_W = 1470
FRAME_H = 1900
TORN_TOP = 0.1502
TORN_RIGHT = 0.0055
TORN_BOTTOM = 0.023
TORN_LEFT = 0.1249
INNER_TOP = 0.0
INNER_RIGHT = -0.0031
INNER_BOTTOM = -0.0083
INNER_LEFT = -0.0031

FILL_SRC = ASSETS / "photo-fill-mask.png"
BORDER_SRC = ASSETS / "photo-torn-border.png"


def _torn_inner_size() -> tuple[int, int]:
    torn_w = FRAME_W * (1.0 - TORN_LEFT - TORN_RIGHT)
    torn_h = FRAME_H * (1.0 - TORN_TOP - TORN_BOTTOM)
    inner_w = int(round(torn_w * (1.0 - INNER_LEFT - INNER_RIGHT)))
    inner_h = int(round(torn_h * (1.0 - INNER_TOP - INNER_BOTTOM)))
    return inner_w, inner_h


def _white_mask(rgba: Image.Image) -> np.ndarray:
    arr = np.array(rgba.convert("RGBA"))
    rgb = arr[..., :3].astype(np.int16)
    alpha = arr[..., 3]
    return (alpha > 128) & (rgb.min(axis=-1) > 200)


def _fit_to_canvas(src: Image.Image, tw: int, th: int, *, as_stroke: bool) -> Image.Image:
    """Resize source (881×1024 artboard) onto torn-inner canvas; keep binary edges."""
    # Stretch to torn-inner so fill + border stay pixel-aligned (same artboard).
    resized = src.convert("RGBA").resize((tw, th), Image.Resampling.LANCZOS)
    white = _white_mask(resized)
    if float(white.mean()) < 0.01:
        raise RuntimeError(f"No white ink after resize ({src})")

    out = np.zeros((th, tw, 4), dtype=np.uint8)
    if as_stroke:
        out[white, :3] = 254
        out[white, 3] = 255
    else:
        # Hole mask: opaque white where photo shows.
        out[white, :3] = 255
        out[white, 3] = 255
    return Image.fromarray(out, "RGBA")


def main() -> None:
    if not FILL_SRC.is_file():
        raise FileNotFoundError(f"Missing fill mask source: {FILL_SRC}")
    if not BORDER_SRC.is_file():
        raise FileNotFoundError(f"Missing border source: {BORDER_SRC}")

    tw, th = _torn_inner_size()
    print(f"torn-inner target {tw}×{th}")

    fill = Image.open(FILL_SRC)
    border = Image.open(BORDER_SRC)
    print("fill src", fill.size, "border src", border.size)

    hole = _fit_to_canvas(fill, tw, th, as_stroke=False)
    stroke = _fit_to_canvas(border, tw, th, as_stroke=True)

    hole_arr = np.array(hole)
    fill_pct = float((hole_arr[..., 3] > 128).mean())
    if fill_pct < 0.35 or fill_pct > 0.95:
        raise RuntimeError(f"Hole fill {fill_pct:.3%} outside expected range")

    alpha = Image.fromarray(hole_arr[..., 3], mode="L")
    Image.merge("RGB", (alpha, alpha, alpha)).save(ASSETS / "photo-tear-hole-mask.png")
    hole.save(ASSETS / "photo-tear-hole-mask-alpha.png")
    stroke.save(ASSETS / "photo-torn-border-fit.png")
    print(f"Wrote hole masks fill%={fill_pct:.3%} and photo-torn-border-fit.png")


if __name__ == "__main__":
    main()
