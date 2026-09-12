"""Build photo-tear-hole mask (+ matching torn border) from border interior.

Source of truth:
  assets/photo-torn-border.png — white stroke; hole = everything INSIDE that stroke
  assets/photo-fill-mask.png  — used only to validate the interior region

The fill art is inset from the border on left/right; deriving the hole from the
border interior makes the photo stretch into the full aperture (no L/R gaps).

Outputs (torn-inner pixel size, used under .photo-torn-inner):
  assets/photo-tear-hole-mask-alpha.png
  assets/photo-tear-hole-mask.png
  assets/photo-torn-border-fit.png  — border resized to the same canvas
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "cover_template"
ASSETS = PACKAGE / "assets"

# Match .photo-frame / .photo-torn / .photo-torn-inner CSS (rounded).
# .photo-torn matches ttl_cover_html (photo-mask.svg box).
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

# Grow hole a few px into the stroke so photo tucks under the white rim (no hairline).
HOLE_TUCK_PX = 5


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


def _resize_white(src: Image.Image, tw: int, th: int) -> np.ndarray:
    resized = src.convert("RGBA").resize((tw, th), Image.Resampling.LANCZOS)
    white = _white_mask(resized)
    if float(white.mean()) < 0.01:
        raise RuntimeError(f"No white ink after resize ({src})")
    return white


def _flood_exterior(blocked: np.ndarray) -> np.ndarray:
    """True where reachable from the canvas edge without crossing blocked (stroke)."""
    th, tw = blocked.shape
    exterior = np.zeros((th, tw), dtype=bool)
    q: deque[tuple[int, int]] = deque()

    def seed(y: int, x: int) -> None:
        if blocked[y, x] or exterior[y, x]:
            return
        exterior[y, x] = True
        q.append((y, x))

    for x in range(tw):
        seed(0, x)
        seed(th - 1, x)
    for y in range(th):
        seed(y, 0)
        seed(y, tw - 1)

    while q:
        y, x = q.popleft()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < th and 0 <= nx < tw and not blocked[ny, nx] and not exterior[ny, nx]:
                exterior[ny, nx] = True
                q.append((ny, nx))
    return exterior


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy * dy + dx * dx > radius * radius:
                continue
            shifted = np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
            # Do not wrap around the canvas edge.
            if dy > 0:
                shifted[:dy, :] = False
            elif dy < 0:
                shifted[dy:, :] = False
            if dx > 0:
                shifted[:, :dx] = False
            elif dx < 0:
                shifted[:, dx:] = False
            out |= shifted
    return out


def _rgba_from_mask(mask: np.ndarray, *, stroke: bool) -> Image.Image:
    th, tw = mask.shape
    out = np.zeros((th, tw, 4), dtype=np.uint8)
    if stroke:
        out[mask, :3] = 254
    else:
        out[mask, :3] = 255
    out[mask, 3] = 255
    return Image.fromarray(out, "RGBA")


def main() -> None:
    if not FILL_SRC.is_file():
        raise FileNotFoundError(f"Missing fill mask source: {FILL_SRC}")
    if not BORDER_SRC.is_file():
        raise FileNotFoundError(f"Missing border source: {BORDER_SRC}")

    tw, th = _torn_inner_size()
    print(f"torn-inner target {tw}×{th}")

    fill_white = _resize_white(Image.open(FILL_SRC), tw, th)
    stroke_white = _resize_white(Image.open(BORDER_SRC), tw, th)
    print("fill% after resize", f"{float(fill_white.mean()):.3%}")
    print("stroke% after resize", f"{float(stroke_white.mean()):.3%}")

    exterior = _flood_exterior(stroke_white)
    interior = ~exterior & ~stroke_white
    # Keep the component that overlaps the authored fill (guards against leaks).
    if float((interior & fill_white).mean()) < 0.2:
        raise RuntimeError("Border interior does not overlap fill mask — stroke may be open")
    hole = interior | fill_white
    # Tuck a few pixels under the white rim so L/R seams do not show beige.
    hole = hole | (_dilate(hole, HOLE_TUCK_PX) & stroke_white)

    fill_pct = float(hole.mean())
    if fill_pct < 0.35 or fill_pct > 0.95:
        raise RuntimeError(f"Hole fill {fill_pct:.3%} outside expected range")

    hole_img = _rgba_from_mask(hole, stroke=False)
    stroke_img = _rgba_from_mask(stroke_white, stroke=True)

    alpha = Image.fromarray((hole.astype(np.uint8) * 255), mode="L")
    Image.merge("RGB", (alpha, alpha, alpha)).save(ASSETS / "photo-tear-hole-mask.png")
    hole_img.save(ASSETS / "photo-tear-hole-mask-alpha.png")
    stroke_img.save(ASSETS / "photo-torn-border-fit.png")
    print(f"Wrote hole masks fill%={fill_pct:.3%} and photo-torn-border-fit.png")


if __name__ == "__main__":
    main()
