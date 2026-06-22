from unittest.mock import MagicMock, patch
import sys

# We will patch SQLAlchemy's session and ElevenLabs post request
def run_dry_run():
    print("Initiating mock dry run for seed_new_meditations.py...")
    
    mock_session = MagicMock()
    # Mock db.query(Story).filter(...).first() to return None (so it proceeds to seed)
    mock_session.query.return_value.filter.return_value.first.return_value = None
    
    # We patch SessionLocal to return our mock session
    with patch("app.core.db.SessionLocal", return_value=mock_session):
        # We patch requests.post inside generate_voice_elevenlabs to return a mock response
        with patch("requests.post") as mock_post:
            import base64
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "audio_base64": base64.b64encode(b"mock mp3 data").decode("utf-8"),
                "alignment": {
                    "characters": ["h", "e", "l", "l", "o"],
                    "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4],
                    "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5]
                }
            }
            mock_post.return_value = mock_resp
            
            # Patch save_audio to avoid actual file saving during this test
            with patch("app.core.llm.save_audio", return_value="media/audio/mock_seeded.mp3") as mock_save:
                # Patch get_mp3_duration to return a fixed duration
                with patch("scratch.seed_new_meditations.get_mp3_duration", return_value=120):
                    # Import and run main
                    import scratch.seed_new_meditations as seeder
                    seeder.main()
                    
    print("\nDry run completed successfully! No errors encountered.")
    
    # Assertions
    print(f"Mock DB add calls count: {mock_session.add.call_count}")
    print(f"Mock DB commit calls count: {mock_session.commit.call_count}")
    assert mock_session.add.call_count == 6
    assert mock_session.commit.call_count == 6
    print("Verification checklist items validated!")

if __name__ == "__main__":
    run_dry_run()
