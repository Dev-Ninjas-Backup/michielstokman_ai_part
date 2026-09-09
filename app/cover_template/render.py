"""Render the Figma cover HTML to PNG via Playwright. Isolated from DALL-E."""
from __future__ import annotations

import base64
import html
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_PATH = PACKAGE_DIR / "template.html"

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


def _multiline(value: str) -> str:
    escaped = html.escape((value or "").strip())
    return escaped.replace("\n", "<br>")


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".ttf":
        mime = "font/ttf"
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


def resolve_photo_data_uri(photo_url: str | None) -> str:
    if not photo_url:
        return _data_uri(STATIC_DIR / "sample-photo.png")
    if photo_url.startswith(("http://", "https://")):
        raw, mime = _fetch_bytes(photo_url)
        return _data_uri_bytes(raw, mime)
    local = Path(photo_url)
    if local.is_file():
        return _data_uri(local)
    return _data_uri(STATIC_DIR / "sample-photo.png")


def build_html(data: dict[str, Any], *, photo_src: str) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    city = (data.get("city") or "").strip()
    country = (data.get("country") or "").strip()
    location = ", ".join(part for part in (city, country) if part) or "Unknown"
    explicit_class = "is-explicit" if data.get("is_explicit") else ""
    filled = (
        template.replace("__TITLE__", _multiline(str(data.get("title") or "")))
        .replace("__SUBTITLE__", _multiline(str(data.get("subtitle") or "")))
        .replace("__DESCRIPTION__", _multiline(str(data.get("description") or "")))
        .replace("__AUTHOR_NAME__", html.escape(str(data.get("author_name") or "")))
        .replace("__AGE__", html.escape(str(data.get("age") or "")))
        .replace("__GENDER__", html.escape(str(data.get("gender") or "").lower()))
        .replace("__ORIENTATION__", html.escape(str(data.get("orientation") or "").lower()))
        .replace("__LOCATION__", _multiline(location.upper()))
        .replace("__PHOTO_SRC__", photo_src)
        .replace("__EXPLICIT_CLASS__", explicit_class)
    )
    return _inline_static_assets(filled)


def _inline_static_assets(markup: str) -> str:
    """Embed local CSS/img assets as data URIs so Chromium does not depend on file://."""

    def replace_path(match: re.Match[str]) -> str:
        quote = match.group(1)
        rel = match.group(2)
        if rel.startswith("data:") or rel.startswith("http"):
            return match.group(0)
        path = STATIC_DIR / rel
        if not path.is_file():
            logger.warning("Cover template asset missing: %s", path)
            return match.group(0)
        return f"url({quote}{_data_uri(path)}{quote})"

    markup = re.sub(r"url\((['\"])([^'\"]+)\1\)", replace_path, markup)

    def replace_src(match: re.Match[str]) -> str:
        rel = match.group(1)
        if rel.startswith("data:") or rel.startswith("http") or rel.startswith("__"):
            return match.group(0)
        path = STATIC_DIR / rel
        if not path.is_file():
            logger.warning("Cover template asset missing: %s", path)
            return match.group(0)
        return f'src="{_data_uri(path)}"'

    return re.sub(r'src="([^"]+)"', replace_src, markup)


async def render_cover_png(data: dict[str, Any] | None = None) -> bytes:
    """Load the template in headless Chromium and return a 2160×2160 PNG."""
    from playwright.async_api import async_playwright

    payload = {**SAMPLE_DATA, **(data or {})}
    photo_src = resolve_photo_data_uri(payload.get("photo_url"))
    markup = build_html(payload, photo_src=photo_src)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page(
            viewport={"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
            device_scale_factor=1,
        )
        await page.set_content(markup, wait_until="load")
        await page.evaluate("document.fonts.ready")
        await page.evaluate(
            """() => Promise.all(
                [...document.images].map((img) =>
                    img.complete ? Promise.resolve() : new Promise((res, rej) => {
                        img.onload = res; img.onerror = rej;
                    })
                )
            )"""
        )
        png = await page.locator(".card").screenshot(type="png")
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
