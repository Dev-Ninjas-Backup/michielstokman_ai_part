"""
Regenerate unique AI covers for existing completed stories.

Uses the brand collage frame + a photograph scene taken from each story.
Never overwrites a member-uploaded cover.

    env PYTHONPATH=. .venv/bin/python scratch/regenerate_story_covers.py
    env PYTHONPATH=. .venv/bin/python scratch/regenerate_story_covers.py --limit 20
    env PYTHONPATH=. .venv/bin/python scratch/regenerate_story_covers.py --only-defaults
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("regen_covers")


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate unique story covers")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--only-defaults",
        action="store_true",
        help="Only stories with a missing or admin-default cover",
    )
    args = parser.parse_args()

    from app.core.db import SessionLocal
    from app.utils.story_image_prompt import (
        cover_regeneration_worker,
        list_stories_for_cover_regen,
    )

    db = SessionLocal()
    try:
        stories = list_stories_for_cover_regen(
            db,
            limit=args.limit,
            only_missing_or_default=args.only_defaults,
        )
        story_ids = [str(story.id) for story in stories]
        logger.info("Regenerating covers for %s stor(ies)", len(story_ids))
        for story in stories:
            logger.info("  %s  %s  source=%s", story.id, story.title, story.image_source)
    finally:
        db.close()

    if not story_ids:
        logger.info("Nothing to do.")
        return 0

    cover_regeneration_worker(story_ids)
    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
