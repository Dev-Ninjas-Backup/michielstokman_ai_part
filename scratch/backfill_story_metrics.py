"""
One-time backfill script to recalculate Story.pulse_score and Story.reflections_count
from existing StoryFeedback entries in the database.

Views cannot be backfilled since there's no historical view tracking — 
they will accumulate going forward after the fix is deployed.
"""
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import func
from app.core.db import SessionLocal
from app.model.story import Story, GenerationStatus
from app.model.feedback import StoryFeedback
from app.model.user import User
from app.model.billing import UserSubscription, PaymentTransaction, SubscriptionPlan
from app.model.profile import UserProfile
from app.model.credit import UserCredit
from app.model.cover_image import CoverImage
from app.model.liberation import UserJourney


def backfill_story_metrics():
    print("=" * 60)
    print("BACKFILL: Story pulse_score & reflections_count from feedback")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Get all stories that have at least one feedback entry
        stories_with_feedback = (
            db.query(
                StoryFeedback.story_id,
                func.avg(StoryFeedback.touch_score).label("avg_touch"),
                func.count(StoryFeedback.id).label("total_reflections"),
            )
            .group_by(StoryFeedback.story_id)
            .all()
        )
        
        print(f"Found {len(stories_with_feedback)} stories with feedback entries.")
        
        updated_count = 0
        for row in stories_with_feedback:
            story = db.query(Story).filter(Story.id == row.story_id).first()
            if story:
                old_pulse = story.pulse_score
                old_reflections = story.reflections_count
                
                story.pulse_score = float(row.avg_touch) if row.avg_touch else 0.0
                story.reflections_count = row.total_reflections or 0
                
                print(f"  Story '{story.title or story.id}': "
                      f"pulse {old_pulse} -> {story.pulse_score}, "
                      f"reflections {old_reflections} -> {story.reflections_count}")
                updated_count += 1
        
        db.commit()
        print(f"\nUpdated {updated_count} stories with recalculated metrics.")
        
        # Show new overall stats
        overall_pulse = db.query(func.avg(Story.pulse_score)).scalar()
        overall_views = db.query(func.sum(Story.views_count)).scalar()
        print(f"\nNew Overall Stats:")
        print(f"  Avg Resonance (pulse_score): {round(float(overall_pulse or 0.0), 1)}")
        print(f"  Total Views: {int(overall_views or 0)}")
        print(f"  (Views will accumulate going forward after deployment)")
        
        print("\nBACKFILL COMPLETE!")
        
    except Exception as e:
        db.rollback()
        print(f"\nBACKFILL FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    backfill_story_metrics()
