import sys
import os
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.db import SessionLocal
from app.model.user import User
from app.model.story import Story, StoryType, GenerationStatus, ModerationStatus
from app.model.feedback import StoryFeedback
from app.api.v1.endpoints.routes_user_dashboard import get_story_detail, get_discovery_feed
from app.api.v1.endpoints.routes_feedback import submit_story_feedback
from app.schemas.schema_feedback import StoryFeedbackRequest

def run_test():
    print("==================================================")
    print("RUNNING STORY METRICS & RATINGS UNIT TEST")
    print("==================================================")
    
    db = SessionLocal()
    user_id = None
    story_id = None
    
    try:
        # 1. Create a test user
        user = User(
            id=uuid.uuid4(),
            email=f"metrics_test_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        print(f"Created test user: {user.email}")
        
        # 2. Create a completed approved story
        story = Story(
            id=uuid.uuid4(),
            story_type=StoryType.confession,
            title="Test Metrics Story",
            story_text="This is a test story content for testing views and feedback ratings.",
            generation_status=GenerationStatus.completed,
            moderation_status=ModerationStatus.approved,
            views_count=0,
            pulse_score=0.0,
            reflections_count=0
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        story_id = story.id
        print(f"Created approved story: {story.title} (ID: {story.id})")
        print(f"Initial story stats - Views: {story.views_count}, Pulse: {story.pulse_score}, Reflections: {story.reflections_count}")
        
        # 3. Simulate calling GET /stories/{story_id} to increment views
        print("\n--- Simulating 3 Detail Page views ---")
        for i in range(3):
            res = get_story_detail(story_id=str(story_id), db=db, current_user=user)
            # The function returns ApiResponse[StoryDetailUserResponse]
            # Since ApiResponse might wrap result in a custom class, let's refresh the story and check views_count
            db.refresh(story)
            print(f"View {i+1} - Story views_count is now: {story.views_count}")
        
        assert story.views_count == 3, f"Expected views_count to be 3, got {story.views_count}"
        
        # 4. Simulate submitting feedback
        print("\n--- Submitting feedback ---")
        feedback_req = StoryFeedbackRequest(
            touch_score=8.0,      # Resonance score (0 to 10)
            star_rating=4.0,      # Rating (0 to 5)
            resonance_tags=["Calm", "Peaceful"],
            reaction="warm",
            feedback_text="Beautiful experience"
        )
        
        # Call the endpoint function directly
        submit_story_feedback(story_id=str(story_id), request=feedback_req, db=db, current_user=user)
        
        # Refresh story and check that pulse_score and reflections_count updated
        db.refresh(story)
        print(f"Post-feedback story stats - Pulse: {story.pulse_score}, Reflections: {story.reflections_count}")
        
        assert story.pulse_score == 8.0, f"Expected pulse_score to be 8.0, got {story.pulse_score}"
        assert story.reflections_count == 1, f"Expected reflections_count to be 1, got {story.reflections_count}"
        
        # 5. Check discovery feed response
        print("\n--- Querying discovery feed ---")
        feed_res = get_discovery_feed(story_type=None, db=db, current_user=user)
        
        # Parse the feed_res to find our story item
        # feed_res is a dict, and feed_res["data"] is a DiscoveryFeedResponse Pydantic model
        feed_items = feed_res["data"].items
        matching_item = None
        for item in feed_items:
            if getattr(item, "id", None) == str(story_id):
                matching_item = item
                break
                
        assert matching_item is not None, "Expected test story to be in discovery feed items"
        print(f"Discovery Feed Item stats for '{matching_item.title}':")
        print(f"  Rating (out of 5): {matching_item.rating}")
        print(f"  Listened Count: {matching_item.listened_count}")
        
        # rating should be the average star_rating (4.0)
        assert matching_item.rating == 4.0, f"Expected rating to be 4.0, got {matching_item.rating}"
        assert matching_item.listened_count == 3, f"Expected listened_count to be 3, got {matching_item.listened_count}"
        
        print("\nALL METRICS TESTS PASSED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if story_id or user_id:
            print("\nCleaning up database...")
            if story_id:
                db.query(StoryFeedback).filter(StoryFeedback.story_id == story_id).delete()
                db.query(Story).filter(Story.id == story_id).delete()
            if user_id:
                db.query(User).filter(User.id == user_id).delete()
            db.commit()
            print("Cleanup complete!")
        db.close()

if __name__ == "__main__":
    run_test()
