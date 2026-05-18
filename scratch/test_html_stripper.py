import sys
from pathlib import Path

# Force stdout to use utf-8 to prevent emoji encoding errors on Windows terminals
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas.schema_liberation import StepSummary, StepDetail, DayGenerateResponse
from app.schemas.schema_liberation_catalog import DayThemeItem

def test_html_stripping():
    dirty_html = (
        "<p>Find the nearest source of light — a window, the sky, even a lamp. "
        "Look up toward it. Take 3 slow breaths. Then gently turn your head left… center… right. "
        "Drop your shoulders. Reach your arms up for a 10-second gratitude stretch.<br><br>"
        "1.Look up toward the nearest light source<br>"
        "2.Take 3 slow, deep breaths — thank the new day<br>"
        "3.Gentle neck turns: slowly left, center, right<br>"
        "4.Drop your shoulders and release tension<br>"
        "5.Arms up for a 10-second gratitude stretch</p><p></p>"
    )
    
    dirty_theme = "🌿 \"Hey friend, <p>let's do something simple</p> that lets your body sing again.\""
    
    print("\n--- 1. Testing StepSummary (day_theme HTML stripping) ---")
    summary = StepSummary(
        day_number=1,
        day_theme=dirty_theme,
        status="completed"
    )
    print(f"Original theme: {dirty_theme}")
    print(f"Cleaned theme:  {summary.day_theme}")
    assert "<p>" not in summary.day_theme
    assert "</p>" not in summary.day_theme
    
    print("\n--- 2. Testing StepDetail (HTML stripping on themes, greetings, and exercises) ---")
    detail = StepDetail(
        day_number=1,
        day_theme=dirty_theme,
        status="completed",
        ai_greeting="<p>Hey friend, thank you for showing up today.</p>",
        ai_exercise_text=dirty_html,
        ai_why_text="<p>Light is the oldest signal to your body.</p>"
    )
    print(f"Cleaned greeting: {repr(detail.ai_greeting)}")
    print(f"Cleaned exercise: {repr(detail.ai_exercise_text)}")
    print(f"Cleaned why:      {repr(detail.ai_why_text)}")
    
    assert "<p>" not in detail.ai_greeting
    assert "<br>" not in detail.ai_exercise_text
    assert "<p>" not in detail.ai_exercise_text
    assert "\n\n1.Look up" in detail.ai_exercise_text
    
    print("\n--- 3. Testing DayGenerateResponse (HTML stripping on all fields) ---")
    gen_response = DayGenerateResponse(
        day_number=1,
        day_theme=dirty_theme,
        ai_greeting="<p>Welcome to Day 1</p>",
        ai_exercise_text=dirty_html,
        ai_why_text="<p>Resets your nervous system</p>"
    )
    assert "<p>" not in gen_response.ai_greeting
    assert "<p>" not in gen_response.ai_exercise_text
    
    print("\n--- 4. Testing DayThemeItem (Catalog schema HTML stripping) ---")
    catalog_item = DayThemeItem(
        day_number=1,
        day_theme=dirty_theme,
        exercise_text=dirty_html,
        why_text="<p>Catalog details are clean</p>"
    )
    assert "<p>" not in catalog_item.day_theme
    assert "<p>" not in catalog_item.exercise_text
    assert "<p>" not in catalog_item.why_text

    print("\n[ALL TESTS PASSED] HTML is beautifully stripped and formatted into clean text!")

if __name__ == "__main__":
    test_html_stripping()
