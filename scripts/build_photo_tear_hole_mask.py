"""Build photo-tear-hole mask from the SAME photo-mask.svg used as the white overlay.

Rasters the live cover template (real CSS for .photo-torn / .photo-torn-inner),
then derives the aperture as the complement of the SE exterior past the L stroke.
"""
from __future__ import annotations

import asyncio
from collections import deque
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "cover_template"
ASSETS = PACKAGE / "assets"
FRAME_W = 1470
FRAME_H = 1900

TORN_TOP = 0.1502
TORN_RIGHT = 0.0055
TORN_BOTTOM = 0.023
TORN_LEFT = 0.1249


async def _raster_ribbon_from_live_page() -> Image.Image:
    """Screenshot .photo-frame with photo-mask.svg path (no drop-shadow) via real CSS."""
    from playwright.async_api import async_playwright

    # Strip the drop-shadow filter for mask geometry — same path as the overlay,
    # without the soft brown fringe shifting the perceived inner edge.
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
              <img src="./assets/_photo-mask-noshadow.svg" alt="" />
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
                "() => { const i=document.querySelector('.photo-torn-inner img');"
                " return i && i.complete && i.naturalWidth; }"
            )
            png = await page.locator(".photo-frame").screenshot(
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
    if arr.shape[0] != FRAME_H or arr.shape[1] != FRAME_W:
        ribbon_rgba = ribbon_rgba.resize((FRAME_W, FRAME_H), Image.Resampling.NEAREST)
        arr = np.array(ribbon_rgba)

    alpha = arr[..., 3]
    rgb = arr[..., :3].astype(np.int16)
    barrier = (alpha > 200) & (rgb.min(axis=-1) > 200)
    if float(barrier.mean()) < 0.01:
        # opaque screenshot without alpha — use near-white RGB
        barrier = (arr[..., 0] > 250) & (arr[..., 1] > 250) & (arr[..., 2] > 250)

    torn_x = int(round(FRAME_W * TORN_LEFT))
    torn_y = int(round(FRAME_H * TORN_TOP))
    torn_w = int(round(FRAME_W * (1.0 - TORN_LEFT - TORN_RIGHT)))
    torn_h = int(round(FRAME_H * (1.0 - TORN_TOP - TORN_BOTTOM)))

    vert = barrier.copy()
    vert[:, : torn_x + int(0.50 * torn_w)] = False
    horiz = barrier.copy()
    horiz[: torn_y + int(0.50 * torn_h), :] = False
    ys, xs = np.where(vert)
    if len(xs) == 0 or not np.any(horiz):
        raise RuntimeError("photo-mask.svg did not rasterize into an L-shaped barrier")
    top_tip_y = int(ys.min())
    top_tip_x = int(xs[ys == top_tip_y].max())
    ys_h, xs_h = np.where(horiz)
    left_tip_x = int(xs_h.min())
    left_tip_y = int(ys_h[xs_h == left_tip_x].min())

    block = barrier.copy()
    block[: top_tip_y + 1, top_tip_x:] = True
    block[left_tip_y:, : left_tip_x + 1] = True

    exterior = np.zeros((FRAME_H, FRAME_W), dtype=bool)
    seed = (FRAME_W - 2, FRAME_H - 2)
    if block[seed[1], seed[0]]:
        seed = (FRAME_W - 5, FRAME_H - 5)
    q: deque[tuple[int, int]] = deque([seed])
    exterior[seed[1], seed[0]] = True
    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= FRAME_W or ny >= FRAME_H:
                continue
            if exterior[ny, nx] or block[ny, nx]:
                continue
            exterior[ny, nx] = True
            q.append((nx, ny))

    xx = np.arange(FRAME_W)[None, :]
    yy = np.arange(FRAME_H)[:, None]
    in_torn = (xx >= torn_x) & (yy >= torn_y)
    # Clip to the inner side of the L only (do not include ink — white overlay
    # paints on top). Exterior flood already stopped at the ribbon pixels.
    hole = (~exterior) & in_torn & (~barrier)

    fill = float(hole.mean())
    if fill < 0.35 or fill > 0.85:
        raise RuntimeError(f"Hole fill {fill:.3%} outside expected range")

    out = np.zeros((FRAME_H, FRAME_W, 4), dtype=np.uint8)
    out[hole, :3] = 255
    out[hole, 3] = 255
    return Image.fromarray(out, "RGBA")


async def main() -> None:
    print("Rasterizing photo-mask.svg via live cover CSS…")
    ribbon = await _raster_ribbon_from_live_page()
    ribbon.save(ASSETS / "photo-mask-raster-debug.png")
    a = np.array(ribbon)
    if a.shape[2] == 4:
        print("ribbon opaque%", float((a[..., 3] > 200).mean()), "size", a.shape)
    hole = _hole_from_ribbon(ribbon)
    hole_arr = np.array(hole)
    print("hole fill%", float((hole_arr[..., 3] > 128).mean()))

    alpha = Image.fromarray(hole_arr[..., 3], mode="L")
    Image.merge("RGB", (alpha, alpha, alpha)).save(ASSETS / "photo-tear-hole-mask.png")
    hole.save(ASSETS / "photo-tear-hole-mask-alpha.png")

    (ASSETS / "photo-tear-hole.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1469.848 1899.615">
  <!-- GENERATED — do not hand-edit.
       Hole mask PNGs are derived from assets/photo-mask.svg (same file as the
       white .photo-torn overlay) via scripts/build_photo_tear_hole_mask.py.
       Re-run after any photo-mask.svg or .photo-torn CSS change. -->
</svg>
""",
        encoding="utf-8",
    )
    print("Wrote masks from photo-mask.svg")


if __name__ == "__main__":
    asyncio.run(main())
