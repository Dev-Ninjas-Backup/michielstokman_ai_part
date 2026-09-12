#!/usr/bin/env python3
"""Generate 3 confession DALL-E covers to visually check the fixed photo style.

Safe: does NOT create/update Story rows. Only calls OpenAI + optional S3 upload
(same as normal cover gen), then downloads images to a local folder.

Usage (machine that has OPENAI_API_KEY, e.g. EC2 api container):

  cd ~/michielstokman_ai_part   # or /app inside the container
  python scripts/gen_confession_style_covers.py

  # or one sample only:
  python scripts/gen_confession_style_covers.py --sample 2

Outputs under scratch/confession_style_tests/ (prompt txt + jpg + results.json).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.utils.confession_style_preview import (  # noqa: E402
    SAMPLES,
    generate_sample_cover,
)

OUT = ROOT / "scratch" / "confession_style_tests"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=int,
        choices=range(1, len(SAMPLES) + 1),
        default=None,
        help="Generate only this 1-based sample (default: all three)",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if not settings.OPENAI_API_KEY:
        print(
            "OPENAI_API_KEY is not set in this process. "
            "On EC2 use: docker compose exec api python scripts/gen_confession_style_covers.py",
            file=sys.stderr,
        )
        return 1

    indices = [args.sample] if args.sample else list(range(1, len(SAMPLES) + 1))
    results = []
    for index in indices:
        print(f"Generating sample {index}…", flush=True)
        result = generate_sample_cover(index)
        sample = result["sample"]
        slug = sample["slug"]
        prompt_path = OUT / f"{slug}_prompt.txt"
        prompt_path.write_text(result["prompt"] + "\n", encoding="utf-8")

        image_path = None
        if result["image_bytes"]:
            # OpenAI returns jpeg for dall-e-3 URL downloads; S3 key often .jpg
            ext = "jpg"
            if (result["cover_key"] or "").endswith(".png"):
                ext = "png"
            image_path = OUT / f"{slug}.{ext}"
            image_path.write_bytes(result["image_bytes"])
            print(f"  wrote {image_path} ({len(result['image_bytes'])} bytes)", flush=True)
        else:
            print(f"  no image bytes (url={result['cover_url']!r})", flush=True)

        results.append(
            {
                "slug": slug,
                "title": sample["title"],
                "author_name": sample["author_name"],
                "gender": sample["gender"],
                "age": sample["age"],
                "location": sample["location"],
                "prompt_file": str(prompt_path),
                "image_file": str(image_path) if image_path else None,
                "cover_url": result["cover_url"],
                "cover_key": result["cover_key"],
                "prompt_words": len(result["prompt"].split()),
            }
        )
        print(f"  -> {result['cover_url'] or 'FAILED'}", flush=True)

    summary = OUT / "results.json"
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {summary}")
    return 0 if all(r.get("cover_url") for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
