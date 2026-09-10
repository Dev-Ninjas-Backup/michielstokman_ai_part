"""Build photo-tear-hole mask from the SAME photo-mask.svg used as the white overlay.

Rasters .photo-torn-inner (shared box with the live white stroke + photo), then
derives a paper silhouette clipped to the L's OUTER edge so the photo:
  - fills under every jagged bay (no beige gaps)
  - never extends past the stroke outer edge into the card beige
"""
from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "cover_template"
ASSETS = PACKAGE / "assets"
# Match .photo-frame CSS size (rounded) used as the build viewport.
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


def _dilate(mask: np.ndarray, radius_px: int) -> np.ndarray:
    if radius_px <= 0:
        return mask.astype(bool)
    size = 2 * radius_px + 1
    return (
        np.array(
            Image.fromarray((mask.astype(np.uint8) * 255)).filter(
                ImageFilter.MaxFilter(size)
            )
        )
        > 0
    )


async def _raster_ribbon_from_live_page() -> Image.Image:
    """Screenshot .photo-torn-inner with photo-mask.svg (no drop-shadow)."""
    from playwright.async_api import async_playwright

    src = (ASSETS / "photo-mask.svg").read_text(encoding="utf-8")
    stripped = src.replace('filter="url(#filter0_d_0_4)"', "")
    tmp_svg = ASSETS / "_photo-mask-noshadow.svg"
    tmp_svg.write_text(stripped, encoding="utf-8")

    html = f"""<!DOCTYPE html>
<html><head>
  <link rel="stylesheet" href="./styles.css" />
  <style>
    html, body {{ margin:0; background:transparent; width:{FRAME_W}px; height:{FRAME_H}px; overflow:hidden; }}
    #cover {{ width:{FRAME_W}px; height:{FRAME_H}px; transform:none !important; background:transparent; }}
    .photo-wrap {{
      left:0 !important; top:0 !important;
      width:{FRAME_W}px !important; height:{FRAME_H}px !important;
    }}
    .photo-rotator {{ transform:none !important; }}
    .photo-image, .photo-overlay, .photo-accent,
    .chip, .title-block, .subtitle-block, .confession,
    .logo, .underline-pink, .underline-orange, .vector-deco,
    .meta-row, .badge-explicit {{ display:none !important; }}
  </style>
</head>
<body>
  <div id="cover">
    <div class="photo-wrap">
      <div class="photo-rotator">
        <div class="photo-frame">
          <div class="photo-torn">
            <div class="photo-torn-inner">
              <img class="photo-torn-stroke" src="./assets/_photo-mask-noshadow.svg" alt="" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</body></html>"""
    index = PACKAGE / "_mask_build.html"
    index.write_text(html, encoding="utf-8")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = await browser.new_page(
                viewport={"width": FRAME_W, "height": FRAME_H},
                device_scale_factor=1,
            )
            await page.goto(index.as_uri(), wait_until="load")
            await page.wait_for_function(
                "() => { const i=document.querySelector('.photo-torn-stroke');"
                " return i && i.complete && i.naturalWidth; }"
            )
            png = await page.locator(".photo-torn-inner").screenshot(
                type="png", omit_background=True
            )
            await browser.close()
    finally:
        if index.exists():
            index.unlink()
        if tmp_svg.exists():
            tmp_svg.unlink()
    return Image.open(BytesIO(png)).convert("RGBA")


def _hole_from_ribbon(ribbon_rgba: Image.Image) -> Image.Image:
    arr = np.array(ribbon_rgba)
    h, w = arr.shape[0], arr.shape[1]

    alpha = arr[..., 3]
    rgb = arr[..., :3].astype(np.int16)
    barrier = (alpha > 200) & (rgb.min(axis=-1) > 200)
    if float(barrier.mean()) < 0.01:
        barrier = (arr[..., 0] > 250) & (arr[..., 1] > 250) & (arr[..., 2] > 250)

    # L topology in torn-inner space: vertical arm on the right, horizontal on bottom.
    vert = barrier.copy()
    vert[:, : w // 2] = False
    horiz = barrier.copy()
    horiz[: h // 2, :] = False
    ys, xs = np.where(vert)
    if len(xs) == 0 or not np.any(horiz):
        raise RuntimeError("photo-mask.svg did not rasterize into an L-shaped barrier")
    top_tip_y = int(ys.min())
    top_tip_x = int(xs[ys == top_tip_y].max())
    ys_h, xs_h = np.where(horiz)
    left_tip_x = int(xs_h.min())
    left_tip_y = int(ys_h[xs_h == left_tip_x].min())

    # Snap open edges to painted tips (CSS % can sit 1–3px outside the ink).
    box_l = 0
    box_t = top_tip_y

    right_edge = np.full(h, -1, dtype=np.int32)
    for y in range(h):
        xs_row = np.where(vert[y])[0]
        if len(xs_row):
            right_edge[y] = int(xs_row.max())
    last = -1
    for y in range(h):
        if right_edge[y] >= 0:
            last = right_edge[y]
        elif last >= 0 and y >= top_tip_y:
            right_edge[y] = last
    last = -1
    for y in range(h - 1, -1, -1):
        if right_edge[y] >= 0:
            last = right_edge[y]
        elif last >= 0 and y >= top_tip_y:
            right_edge[y] = last

    bottom_edge = np.full(w, -1, dtype=np.int32)
    for x in range(w):
        ys_col = np.where(horiz[:, x])[0]
        if len(ys_col):
            bottom_edge[x] = int(ys_col.max())
    last = -1
    for x in range(w):
        if bottom_edge[x] >= 0:
            last = bottom_edge[x]
        elif last >= 0 and x >= left_tip_x:
            bottom_edge[x] = last
    last = -1
    for x in range(w - 1, -1, -1):
        if bottom_edge[x] >= 0:
            last = bottom_edge[x]
        elif last >= 0 and x >= left_tip_x:
            bottom_edge[x] = last

    default_bottom = int(ys_h.max()) if len(ys_h) else h - 1
    default_right = int(xs.max()) if len(xs) else w - 1

    xs_grid = np.arange(w)[None, :]
    ys_grid = np.arange(h)[:, None]
    re = right_edge.astype(np.int32).copy()
    be = bottom_edge.astype(np.int32).copy()
    re[re < 0] = default_right
    tip_bottom = (
        int(bottom_edge[left_tip_x]) if bottom_edge[left_tip_x] >= 0 else default_bottom
    )
    be[:left_tip_x] = np.where(be[:left_tip_x] < 0, tip_bottom, be[:left_tip_x])
    be[be < 0] = default_bottom

    hole = (
        (ys_grid >= box_t)
        & (xs_grid >= box_l)
        & (xs_grid <= re[:, None])
        & (ys_grid <= be[None, :])
    )

    hole |= barrier & _dilate(hole, 2)
    hole = _dilate(hole, 2)
    for y in range(h):
        if right_edge[y] >= 0:
            hole[y, int(right_edge[y]) + 1 :] = False
    for x in range(w):
        if bottom_edge[x] >= 0:
            hole[int(bottom_edge[x]) + 1 :, x] = False
    hole[:top_tip_y, :] = False
    hole[:, :box_l] = False
    hole[: top_tip_y + 1, top_tip_x + 1 :] = False

    fill = float(hole.mean())
    if fill < 0.35 or fill > 0.95:
        raise RuntimeError(f"Hole fill {fill:.3%} outside expected range")

    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[hole, :3] = 255
    out[hole, 3] = 255
    return Image.fromarray(out, "RGBA")


async def main() -> None:
    print("Rasterizing photo-mask.svg via .photo-torn-inner…")
    ribbon = await _raster_ribbon_from_live_page()
    ribbon.save(ASSETS / "photo-mask-raster-debug.png")
    a = np.array(ribbon)
    print("ribbon opaque%", float((a[..., 3] > 200).mean()), "size", a.shape)
    hole = _hole_from_ribbon(ribbon)
    hole_arr = np.array(hole)
    print("hole fill%", float((hole_arr[..., 3] > 128).mean()), "size", hole_arr.shape)
    alpha = Image.fromarray(hole_arr[..., 3], mode="L")
    Image.merge("RGB", (alpha, alpha, alpha)).save(ASSETS / "photo-tear-hole-mask.png")
    hole.save(ASSETS / "photo-tear-hole-mask-alpha.png")
    print("Wrote masks from photo-mask.svg (torn-inner space)")


if __name__ == "__main__":
    asyncio.run(main())
