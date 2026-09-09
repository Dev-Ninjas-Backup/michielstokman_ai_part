"""Render the TTL HTML cover to PNG via Playwright. Isolated from DALL-E.

The page uses window.Cover.set({...}) — no server-side placeholder substitution.
Playwright loads index.html from a loopback static server so ./assets and ./fonts resolve.
Viewport is always 2160×2160 so Cover.fit() scale is 1.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse
from urllib.request import urlopen

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
INDEX_PATH = PACKAGE_DIR / "index.html"
ASSETS_DIR = PACKAGE_DIR / "assets"
DEFAULT_PHOTO = ASSETS_DIR / "photo.png"

CANVAS_WIDTH = 2160
CANVAS_HEIGHT = 2160

SAMPLE_DATA = {
    "title": "To Wasteland\nOn My Own",
    "subtitle": "A Night That\nLiberated My Essence",
    "description": "A confession about\nshame, desire and\nfinally choosing me.",
    "author_name": "Lisa",
    "age": "28",
    "gender": "female",
    "orientation": "bisexual",
    "city": "Barcelona",
    "country": "Spain",
    "is_explicit": True,
    "photo_url": None,
}


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _data_uri_bytes(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/jpeg")
    with urlopen(url, timeout=30) as resp:  # noqa: S310 — caller-supplied test URL
        data = resp.read()
        header = resp.headers.get_content_type()
        if header and header.startswith("image/"):
            mime = header
    return data, mime


def resolve_photo_data_uri(photo_url: str | None) -> str | None:
    """Return a data URI to swap into .photo-image img, or None to keep photo.png."""
    if not photo_url:
        return None
    if photo_url.startswith(("http://", "https://")):
        raw, mime = _fetch_bytes(photo_url)
        return _data_uri_bytes(raw, mime)
    if photo_url.startswith("data:"):
        return photo_url
    local = Path(photo_url)
    if local.is_file():
        return _data_uri(local)
    if DEFAULT_PHOTO.is_file():
        return _data_uri(DEFAULT_PHOTO)
    return None


def _split_two_lines(value: str) -> tuple[str, str]:
    """Split a newline-separated title/subtitle into Cover.set line1/line2."""
    parts = [p.strip() for p in str(value or "").replace("\r\n", "\n").split("\n")]
    parts = [p for p in parts if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def payload_to_cover_set(data: dict[str, Any]) -> dict[str, Any]:
    """Map test-route fields onto window.Cover.set() keys.

    Query/body params (unchanged): title, subtitle, description, author_name,
    age, gender, orientation, city, country, is_explicit, photo_url.

    title / subtitle: first newline → line1, remaining lines joined → line2.
    description → confession. author_name → author. role is always "author".
    is_explicit True → explicit True (label "explicit"); False/None → False (hide).
    photo_url is applied separately as photoUrl (data URI); omitted keeps assets/photo.png.
    """
    title_l1, title_l2 = _split_two_lines(str(data.get("title") or ""))
    sub_l1, sub_l2 = _split_two_lines(str(data.get("subtitle") or ""))
    explicit_flag = data.get("is_explicit")
    cover: dict[str, Any] = {
        "titleLine1": title_l1,
        "titleLine2": title_l2,
        "subtitleLine1": sub_l1,
        "subtitleLine2": sub_l2,
        "confession": str(data.get("description") or ""),
        "city": str(data.get("city") or "").strip().rstrip(","),
        "country": str(data.get("country") or "").strip(),
        "author": str(data.get("author_name") or ""),
        "role": "author",
        "age": str(data.get("age") or ""),
        "gender": str(data.get("gender") or "").strip().lower(),
        "orientation": str(data.get("orientation") or "").strip().lower(),
        "explicit": True if explicit_flag else False,
    }
    photo = resolve_photo_data_uri(data.get("photo_url"))
    if photo:
        cover["photoUrl"] = photo
    return cover


class _QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PACKAGE_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


@contextmanager
def _static_server() -> Iterator[str]:
    """Serve app/cover_template on 127.0.0.1 so relative ./assets ./fonts work."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


_WAIT_ASSETS_JS = """() => Promise.all([
    document.fonts.ready,
    ...[...document.images].map((img) =>
        img.complete && img.naturalWidth
            ? Promise.resolve()
            : new Promise((res) => {
                img.onload = res;
                img.onerror = res;
            })
    ),
])"""


async def render_cover_png(data: dict[str, Any] | None = None) -> bytes:
    """Load index.html in headless Chromium at 2160×2160 and return a PNG."""
    from playwright.async_api import async_playwright

    if not INDEX_PATH.is_file():
        raise FileNotFoundError(f"Cover template missing: {INDEX_PATH}")

    payload = {**SAMPLE_DATA, **(data or {})}
    cover_set = payload_to_cover_set(payload)

    with _static_server() as origin:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = await browser.new_page(
                viewport={"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
                device_scale_factor=1,
            )
            await page.goto(f"{origin}/index.html", wait_until="load")
            await page.wait_for_function(
                "() => window.Cover && typeof window.Cover.set === 'function'"
            )
            await page.evaluate(
                """(fields) => {
                    window.Cover.set(fields);
                    window.Cover.fit();
                }""",
                cover_set,
            )
            await page.evaluate(_WAIT_ASSETS_JS)
            inner = await page.evaluate(
                "() => ({ w: window.innerWidth, h: window.innerHeight, "
                "scale: document.getElementById('cover').style.transform })"
            )
            if inner["w"] != CANVAS_WIDTH or inner["h"] != CANVAS_HEIGHT:
                logger.warning("Cover viewport is not 2160×2160: %s", inner)
            png = await page.locator("#cover").screenshot(type="png")
            await browser.close()
    return png


def render_cover_png_sync(data: dict[str, Any] | None = None, output_path: Path | None = None) -> bytes:
    """Sync wrapper for the CLI script."""
    import asyncio

    png = asyncio.run(render_cover_png(data))
    if output_path is not None:
        output_path.write_bytes(png)
        logger.info("Wrote cover preview to %s", output_path)
    return png
