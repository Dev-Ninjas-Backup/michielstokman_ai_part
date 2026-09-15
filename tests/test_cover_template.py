"""Regression: cover photo must fill the torn hole with zero gap and zero overflow.

Locks the Playwright HTML cover-template clip/mask behavior so CSS/asset
changes cannot silently reintroduce beige gaps inside the hole or photo bleed
past the jagged boundary.
"""
from __future__ import annotations

import base64
import math
from io import BytesIO
import pytest
from PIL import Image

from app.cover_template.render import (
    ASSETS_DIR,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    SAMPLE_DATA,
    render_cover_png_sync,
)

# Geometry from app/cover_template/styles.css (.photo-wrap / .photo-rotator / .photo-frame)
_WRAP_L = 670.0
_WRAP_T = 10.0
_WRAP_W = 1782.6
_WRAP_H = 2129.597
_FRAME_W = 1469.848
_FRAME_H = 1899.615
_ANGLE = math.radians(1.0)
_SCALE = 1.15
_COS = math.cos(_ANGLE)
_SIN = math.sin(_ANGLE)
_OX = (_WRAP_W - _FRAME_W) / 2.0
_OY = (_WRAP_H - _FRAME_H) / 2.0
_CX = _WRAP_L + _WRAP_W / 2.0
_CY = _WRAP_T + _WRAP_H / 2.0

# .photo-torn / .photo-torn-inner — ttl_cover_html photo-mask.svg box
_TORN_TOP = 0.1502
_TORN_RIGHT = 0.0055
_TORN_BOTTOM = 0.023
_TORN_LEFT = 0.1249
_INNER_TOP = 0.0
_INNER_RIGHT = -0.0031
_INNER_BOTTOM = -0.0083
_INNER_LEFT = -0.0031
_TORN_X = _FRAME_W * _TORN_LEFT
_TORN_Y = _FRAME_H * _TORN_TOP
_TORN_W = _FRAME_W * (1.0 - _TORN_LEFT - _TORN_RIGHT)
_TORN_H = _FRAME_H * (1.0 - _TORN_TOP - _TORN_BOTTOM)
_INNER_L = _TORN_X + _TORN_W * _INNER_LEFT
_INNER_T = _TORN_Y + _TORN_H * _INNER_TOP
_INNER_W = _TORN_W * (1.0 - _INNER_LEFT - _INNER_RIGHT)
_INNER_H = _TORN_H * (1.0 - _INNER_TOP - _INNER_BOTTOM)

# Cover card beige (#f1ede4). Tight tol catches true gaps; loose tol is for
# solid-color sources where photo content cannot resemble the card background.
_BEIGE = (241, 237, 228)
_BEIGE_TOL_SOLID = 22
_BEIGE_TOL_NATURAL = 4
_HOLE_INSET_PX = 70
_MASK_PATH = ASSETS_DIR / "photo-tear-hole-mask-alpha.png"

# Saturated fill used for landscape / tiny sources so photo vs beige is unambiguous.
_PHOTO_RGB = (220, 20, 60)


def _is_beige(rgb: tuple[int, int, int], tol: int) -> bool:
    return max(abs(int(rgb[i]) - _BEIGE[i]) for i in range(3)) <= tol


def _is_saturated_photo(rgb: tuple[int, int, int]) -> bool:
    r, g, b = (int(c) for c in rgb)
    return r > 160 and g < 100 and b < 120


def _frame_to_canvas(fx: float, fy: float) -> tuple[float, float]:
    wx = _OX + fx
    wy = _OY + fy
    dx = (wx - _WRAP_W / 2.0) * _SCALE
    dy = (wy - _WRAP_H / 2.0) * _SCALE
    return _CX + dx * _COS - dy * _SIN, _CY + dx * _SIN + dy * _COS


def _canvas_to_frame(x: float, y: float) -> tuple[float, float]:
    dx = x - _CX
    dy = y - _CY
    lx = (dx * _COS + dy * _SIN) / _SCALE
    ly = (-dx * _SIN + dy * _COS) / _SCALE
    return lx + _WRAP_W / 2.0 - _OX, ly + _WRAP_H / 2.0 - _OY


def _load_hole_mask() -> tuple[Image.Image, int, int]:
    mask = Image.open(_MASK_PATH).convert("RGBA")
    return mask, mask.size[0], mask.size[1]


def _hole_at_frame(mask: Image.Image, mw: int, mh: int, fx: float, fy: float) -> bool:
    # Mask is authored in .photo-torn-inner coordinates (not full frame).
    lx = fx - _INNER_L
    ly = fy - _INNER_T
    if lx < 0 or ly < 0 or lx >= _INNER_W or ly >= _INNER_H:
        return False
    mx = int(round((lx / _INNER_W) * (mw - 1)))
    my = int(round((ly / _INNER_H) * (mh - 1)))
    mx = max(0, min(mw - 1, mx))
    my = max(0, min(mh - 1, my))
    return mask.getpixel((mx, my))[3] > 127


def _hole_on_canvas(mask: Image.Image, mw: int, mh: int, x: float, y: float) -> bool:
    fx, fy = _canvas_to_frame(x, y)
    return _hole_at_frame(mask, mw, mh, fx, fy)


def _mask_bbox(mask: Image.Image, mw: int, mh: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = mw, mh, -1, -1
    # Subsample for speed; hole edges are coarse enough for probe placement.
    for y in range(0, mh, 2):
        for x in range(0, mw, 2):
            if mask.getpixel((x, y))[3] > 127:
                if x < left:
                    left = x
                if y < top:
                    top = y
                if x > right:
                    right = x
                if y > bottom:
                    bottom = y
    if right < 0:
        raise AssertionError(f"Hole mask has no opaque pixels: {_MASK_PATH}")
    return left, top, right, bottom


def _m2f(mx: float, my: float, mw: int, mh: int) -> tuple[float, float]:
    """Mask pixel → frame coordinates (mask lives in torn-inner space)."""
    lx = mx / (mw - 1) * _INNER_W
    ly = my / (mh - 1) * _INNER_H
    return _INNER_L + lx, _INNER_T + ly


def _first_opaque_x(mask: Image.Image, mw: int, my: int, reverse: bool = False) -> int:
    xs = range(mw - 1, -1, -1) if reverse else range(mw)
    for x in xs:
        if mask.getpixel((x, my))[3] > 127:
            return x
    raise AssertionError(f"No hole pixels on mask row {my}")


def _first_opaque_y(mask: Image.Image, mh: int, mx: int, reverse: bool = False) -> int:
    ys = range(mh - 1, -1, -1) if reverse else range(mh)
    for y in ys:
        if mask.getpixel((mx, y))[3] > 127:
            return y
    raise AssertionError(f"No hole pixels on mask column {mx}")


def _inside_edge_probes(
    mask: Image.Image, mw: int, mh: int
) -> list[tuple[str, int, int]]:
    """Points just inside the hole near left/top/right/bottom (canvas space)."""
    left_m, top_m, right_m, bot_m = _mask_bbox(mask, mw, mh)
    inset_x = int(_HOLE_INSET_PX / _INNER_W * (mw - 1))
    inset_y = int(_HOLE_INSET_PX / _INNER_H * (mh - 1))
    probes: list[tuple[str, int, int]] = []

    for t in (0.35, 0.45, 0.55, 0.65):
        my = int(top_m + t * (bot_m - top_m))
        mx_l = _first_opaque_x(mask, mw, my) + inset_x
        fx, fy = _m2f(mx_l, my, mw, mh)
        x, y = _frame_to_canvas(fx, fy)
        xi, yi = int(round(x)), int(round(y))
        if (
            0 <= xi < CANVAS_WIDTH
            and 0 <= yi < CANVAS_HEIGHT
            and _hole_on_canvas(mask, mw, mh, xi, yi)
        ):
            probes.append(("left", xi, yi))

        mx_r = _first_opaque_x(mask, mw, my, reverse=True) - inset_x
        fx, fy = _m2f(mx_r, my, mw, mh)
        x, y = _frame_to_canvas(fx, fy)
        xi, yi = int(round(x)), int(round(y))
        # Scaled frame can push the right edge past the canvas; walk left.
        if yi < 0 or yi >= CANVAS_HEIGHT:
            continue
        yi = max(0, min(CANVAS_HEIGHT - 1, yi))
        if xi >= CANVAS_WIDTH:
            xi = CANVAS_WIDTH - 2
        for x_try in range(xi, max(-1, xi - 200), -2):
            if x_try < 0:
                break
            if _hole_on_canvas(mask, mw, mh, x_try, yi):
                probes.append(("right", x_try, yi))
                break

    for t in (0.30, 0.40, 0.50, 0.60):
        # Stay left of author/meta chips that sit on the upper-right hole.
        mx = int(left_m + t * (right_m - left_m) * 0.85)
        my_t = _first_opaque_y(mask, mh, mx) + inset_y
        my_b = _first_opaque_y(mask, mh, mx, reverse=True) - inset_y
        for side, my in (("top", my_t), ("bottom", my_b)):
            fx, fy = _m2f(mx, my, mw, mh)
            x, y = _frame_to_canvas(fx, fy)
            xi, yi = int(round(x)), int(round(y))
            if (
                0 <= xi < CANVAS_WIDTH
                and 0 <= yi < CANVAS_HEIGHT
                and _hole_on_canvas(mask, mw, mh, xi, yi)
            ):
                probes.append((side, xi, yi))

    by_side = {s: 0 for s in ("left", "right", "top", "bottom")}
    for side, _, _ in probes:
        by_side[side] += 1
    missing = [s for s, n in by_side.items() if n == 0]
    if missing:
        raise AssertionError(
            f"Could not place inside-hole probes on sides {missing}; "
            f"got {by_side}. Check mask/geometry constants."
        )
    return probes


def _outside_boundary_probes(
    mask: Image.Image, mw: int, mh: int
) -> list[tuple[str, int, int]]:
    """Just outside the hole past the L's outer edge (photo must not appear here)."""
    left_m, top_m, right_m, bot_m = _mask_bbox(mask, mw, mh)
    probes: list[tuple[str, int, int]] = []

    # Step a few pixels past the hole along frame-right and frame-bottom of the L.
    for t in (0.35, 0.45, 0.55, 0.65, 0.75):
        my = int(top_m + t * (bot_m - top_m))
        try:
            mx = _first_opaque_x(mask, mw, my, reverse=True) + 24
        except AssertionError:
            continue
        fx, fy = _m2f(mx, my, mw, mh)
        x, y = _frame_to_canvas(fx, fy)
        xi, yi = int(round(x)), int(round(y))
        if (
            0 <= xi < CANVAS_WIDTH
            and 0 <= yi < CANVAS_HEIGHT
            and not _hole_on_canvas(mask, mw, mh, xi, yi)
        ):
            probes.append(("outside-jagged", xi, yi))

    for t in (0.25, 0.40, 0.55, 0.70):
        mx = int(left_m + t * (right_m - left_m))
        try:
            my = _first_opaque_y(mask, mh, mx, reverse=True) + 24
        except AssertionError:
            continue
        fx, fy = _m2f(mx, my, mw, mh)
        x, y = _frame_to_canvas(fx, fy)
        xi, yi = int(round(x)), int(round(y))
        if (
            0 <= xi < CANVAS_WIDTH
            and 0 <= yi < CANVAS_HEIGHT
            and not _hole_on_canvas(mask, mw, mh, xi, yi)
        ):
            probes.append(("outside-jagged", xi, yi))

    if len(probes) < 4:
        raise AssertionError(
            f"Expected outside-boundary probes past the torn L; got {len(probes)}. "
            "Hole geometry may have changed."
        )
    return probes


def _solid_jpeg_data_uri(size: tuple[int, int], rgb: tuple[int, int, int] = _PHOTO_RGB) -> str:
    img = Image.new("RGB", size, rgb)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _render_cover(photo_url: str | None) -> Image.Image:
    payload = {**SAMPLE_DATA, "photo_url": photo_url, "is_explicit": False}
    png = render_cover_png_sync(payload)
    im = Image.open(BytesIO(png)).convert("RGB")
    assert im.size == (CANVAS_WIDTH, CANVAS_HEIGHT), im.size
    return im


def _assert_hole_fill_and_clip(label: str, cover: Image.Image, expect_saturated: bool) -> None:
    mask, mw, mh = _load_hole_mask()
    inside = _inside_edge_probes(mask, mw, mh)
    outside = _outside_boundary_probes(mask, mw, mh)
    beige_tol = _BEIGE_TOL_SOLID if expect_saturated else _BEIGE_TOL_NATURAL

    beige_inside: list[str] = []
    for side, x, y in inside:
        rgb = cover.getpixel((x, y))
        if _is_beige(rgb, beige_tol):
            beige_inside.append(f"{side}@({x},{y})={rgb}")
    assert not beige_inside, (
        f"[{label}] Photo does not fully fill the torn hole — cover beige visible "
        f"just inside the boundary (gap regression). Offending samples: "
        f"{', '.join(beige_inside[:8])}"
    )

    if expect_saturated:
        photo_hits = sum(
            1 for _, x, y in inside if _is_saturated_photo(cover.getpixel((x, y)))
        )
        assert photo_hits >= max(8, len(inside) // 2), (
            f"[{label}] Expected solid photo fill inside the hole; only {photo_hits}/"
            f"{len(inside)} probes matched {_PHOTO_RGB}."
        )

    overflow: list[str] = []
    for side, x, y in outside:
        rgb = cover.getpixel((x, y))
        if expect_saturated:
            if _is_saturated_photo(rgb):
                overflow.append(f"{side}@({x},{y})={rgb}")
        # Natural portrait: chips/badges sit near the L; only the solid-color
        # cases give an unambiguous overflow signal.
    assert not overflow, (
        f"[{label}] Photo overflows past the torn-hole mask (outside the white "
        f"border). Offending samples: {', '.join(overflow[:8])}"
    )


@pytest.mark.parametrize(
    "case,photo_url,expect_saturated",
    [
        ("portrait-default", None, False),
        ("landscape-wide", "WIDE", True),
        ("tiny-upscaled", "TINY", True),
        # DALL-E-like tall portrait (1024×1792) — hole is fixed; photo must cover.
        ("dalle-tall", "TALL", True),
    ],
)
def test_photo_fills_torn_hole_without_gap_or_overflow(
    case: str, photo_url: str | None, expect_saturated: bool
) -> None:
    """Photo must cover the hole (no beige gaps) and stay clipped (no R/B bleed)."""
    if not _MASK_PATH.is_file():
        pytest.fail(f"Missing hole mask asset required for geometry probes: {_MASK_PATH}")
    if not (ASSETS_DIR / "photo.png").is_file() and photo_url is None:
        pytest.fail("Default cover photo assets/photo.png is missing")

    if photo_url == "WIDE":
        photo_url = _solid_jpeg_data_uri((1600, 900))
    elif photo_url == "TINY":
        photo_url = _solid_jpeg_data_uri((48, 64))
    elif photo_url == "TALL":
        photo_url = _solid_jpeg_data_uri((1024, 1792))

    cover = _render_cover(photo_url)
    _assert_hole_fill_and_clip(case, cover, expect_saturated=expect_saturated)
