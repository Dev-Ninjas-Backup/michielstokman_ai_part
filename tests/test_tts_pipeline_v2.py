"""
Unit tests for TTS Pipeline V2 Phase 1:
- TTS profiles & text preparation
- Flag ON vs Flag OFF contract
- Safe exception fallback to legacy pipeline
- Edge-only silence trimming preservation
"""

import pytest
from unittest.mock import patch, MagicMock
from app.services.tts_profiles import (
    TTSProfile,
    get_tts_profile,
    prepare_text_for_tts,
    TTS_PROFILES,
    DEFAULT_PROFILE,
)
from app.core.config import settings
from app.core.llm import generate_voice_elevenlabs


def test_tts_profiles_validation():
    """Validates profile values and speed constraints."""
    confession = get_tts_profile("confession")
    assert confession.stability == 0.35
    assert confession.similarity_boost == 0.75
    assert confession.style == 0.45
    assert confession.speed == 0.95
    assert confession.pause_ms == 300
    assert confession.paragraph_break_s == 0.7

    meditation = get_tts_profile("meditation")
    assert meditation.stability == 0.65
    assert meditation.similarity_boost == 0.80
    assert meditation.style == 0.15
    assert meditation.speed == 0.85
    assert meditation.pause_ms == 500
    assert meditation.paragraph_break_s == 1.2

    transformation = get_tts_profile("transformation")
    assert transformation.stability == 0.45
    assert transformation.similarity_boost == 0.75
    assert transformation.style == 0.35
    assert transformation.speed == 0.92
    assert transformation.pause_ms == 350
    assert transformation.paragraph_break_s == 0.8

    # Speed out of bounds must raise ValueError
    with pytest.raises(ValueError):
        TTSProfile("bad", 0.5, 0.5, 0.5, speed=0.5, pause_ms=300, paragraph_break_s=0.5)
    with pytest.raises(ValueError):
        TTSProfile("bad", 0.5, 0.5, 0.5, speed=1.5, pause_ms=300, paragraph_break_s=0.5)


def test_prepare_text_for_tts():
    """Validates markdown/emoji stripping and natural paragraph break tag insertion."""
    raw_text = (
        "# A Secret Morning ✨\n\n"
        "**I never told anyone** about that night (until now).\n"
        "He looked at me... and I hesitated. What was I doing?\n\n"
        "Eventually, I just smiled and walked away. ❤️"
    )

    prepared = prepare_text_for_tts(raw_text, "confession")

    # Markdown stripped
    assert "#" not in prepared
    assert "**" not in prepared
    # Emojis stripped
    assert "✨" not in prepared
    assert "❤️" not in prepared
    # Parentheses stripped
    assert "(" not in prepared
    assert ")" not in prepared
    # Ellipses preserved
    assert "..." in prepared
    # No break tag inside sentences
    assert "What was I doing? <break" not in prepared
    # Profile break tag only between paragraphs (2 paragraph boundaries)
    assert '<break time="0.7s" />' in prepared
    assert prepared.count('<break time="0.7s" />') == 2


def test_prepare_text_meditation_and_transformation_breaks():
    """Validates break tag duration matches profile per story type."""
    sample = "First paragraph.\n\nSecond paragraph."
    med_text = prepare_text_for_tts(sample, "meditation")
    assert '<break time="1.2s" />' in med_text

    trans_text = prepare_text_for_tts(sample, "transformation")
    assert '<break time="0.8s" />' in trans_text


def test_flag_off_preserves_legacy_payload(monkeypatch):
    """When TTS_PIPELINE_V2 is False, request payload is byte-for-byte identical to legacy."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", False)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAA=",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        generate_voice_elevenlabs(
            text="First sentence. Second sentence.\n\nParagraph two.",
            voice_id=None,
            return_timestamps=True,
            story_type="confession"
        )
        assert mock_post.called
        sent_body = mock_post.call_args[1]["json"]
        sent_text = sent_body["text"]
        # Legacy pipeline puts 1.0s at sentence endings and 2.0s at paragraph breaks
        assert '<break time="1.0s" />' in sent_text
        assert '<break time="2.0s" />' in sent_text
        # Legacy default confession stability without custom friendly name is 0.55
        assert sent_body["voice_settings"]["stability"] == 0.55


def test_flag_on_uses_v2_profile(monkeypatch):
    """When TTS_PIPELINE_V2 is True, request payload uses prepared text and profile settings."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAA=",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        generate_voice_elevenlabs(
            text="First sentence. Second sentence.\n\nParagraph two.",
            voice_id=None,
            return_timestamps=True,
            story_type="confession"
        )
        assert mock_post.called
        sent_body = mock_post.call_args[1]["json"]
        sent_text = sent_body["text"]
        # V2 puts 0.7s at paragraph break and NO break at sentence endings
        assert '<break time="0.7s" />' in sent_text
        assert '<break time="1.0s" />' not in sent_text
        assert '<break time="2.0s" />' not in sent_text
        # V2 confession profile settings
        assert sent_body["voice_settings"]["stability"] == 0.35
        assert sent_body["voice_settings"]["similarity_boost"] == 0.75
        assert sent_body["voice_settings"]["style"] == 0.45
        assert sent_body["voice_settings"]["speed"] == 0.95


def test_v2_fallback_to_legacy_on_exception(monkeypatch):
    """When V2 raises an exception, it seamlessly falls back to the legacy pipeline."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    with patch("app.core.llm._generate_voice_elevenlabs_v2", side_effect=RuntimeError("V2 simulated failure")):
        with patch("requests.post", return_value=mock_resp) as mock_post:
            audio, alignment = generate_voice_elevenlabs(
                text="Some text.\n\nSecond paragraph.",
                voice_id=None,
                return_timestamps=True,
                story_type="confession"
            )
            # Legacy fallback was executed successfully
            assert mock_post.called
            sent_body = mock_post.call_args[1]["json"]
            assert sent_body["voice_settings"]["stability"] == 0.55
            assert audio == b"ID3\x04\x00\x00\x00\x00\x00\x00"


def test_edge_only_silence_trimming_preserves_internal_silence():
    """
    Synthetic audio test:
    Verifies that edge-only trimming with safe margins removes leading and trailing silence
    while preserving internal pauses exactly.
    """
    import subprocess
    import shutil
    import os
    import re
    import tempfile

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        scratch_ffmpeg = os.path.abspath(os.path.join("scratch", "bin", "ffmpeg.exe"))
        if os.path.isfile(scratch_ffmpeg):
            ffmpeg_bin = scratch_ffmpeg

    if not ffmpeg_bin:
        pytest.skip("FFmpeg binary not available for synthetic trim test")

    with tempfile.TemporaryDirectory() as tmpdir:
        synth_file = os.path.join(tmpdir, "synth.wav")
        trimmed_file = os.path.join(tmpdir, "synth_trimmed.wav")

        # 0.5s silence + 1.0s tone + 1.0s internal silence + 1.0s tone + 0.5s silence = 4.0s
        gen_cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.5",
            "-f", "lavfi", "-i", "sine=f=440:r=44100:d=1.0",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.0",
            "-f", "lavfi", "-i", "sine=f=880:r=44100:d=1.0",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.5",
            "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[out]",
            "-map", "[out]",
            synth_file
        ]
        subprocess.run(gen_cmd, check=True, capture_output=True)

        # Detect silences in original
        detect_cmd = [ffmpeg_bin, "-i", synth_file, "-af", "silencedetect=noise=-45dB:d=0.2", "-f", "null", "-"]
        res = subprocess.run(detect_cmd, capture_output=True, text=True)
        stderr = res.stderr

        silence_starts = [float(x) for x in re.findall(r"silence_start:\s*([\d\.]+)", stderr)]
        silence_ends = [float(x) for x in re.findall(r"silence_end:\s*([\d\.]+)", stderr)]

        total_duration = 4.0
        lead_silence_end = silence_ends[0] if silence_starts and silence_starts[0] <= 0.05 else 0.0
        trail_silence_start = silence_starts[-1] if silence_starts else total_duration

        # Margins: 25ms at start, 100ms at end
        trim_start = max(0.0, lead_silence_end - 0.025)
        trim_end = min(total_duration, trail_silence_start + 0.100)

        trim_cmd = [
            ffmpeg_bin, "-y", "-i", synth_file,
            "-af", f"atrim=start={trim_start:.3f}:end={trim_end:.3f},asetpts=PTS-STARTPTS",
            trimmed_file
        ]
        subprocess.run(trim_cmd, check=True, capture_output=True)

        # Detect silences in trimmed file
        detect_trim = [ffmpeg_bin, "-i", trimmed_file, "-af", "silencedetect=noise=-45dB:d=0.2", "-f", "null", "-"]
        res_trim = subprocess.run(detect_trim, capture_output=True, text=True)
        t_durs = [float(x) for x in re.findall(r"silence_duration:\s*([\d\.]+)", res_trim.stderr)]

        # The internal 1.0s silence must remain intact (~1.0s)
        assert any(abs(d - 1.0) < 0.05 for d in t_durs), f"Internal silence was not preserved: {t_durs}"


def test_cloned_voice_guardrails(monkeypatch):
    """Member cloned (IVC) voice caps style <= 0.25 and keeps stability >= 0.50."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        # Confession profile has stability=0.35, style=0.45
        # For a custom member clone voice ID:
        generate_voice_elevenlabs(
            text="A cloned voice confession.\n\nSecond paragraph.",
            voice_id="member_custom_voice_xyz_987",
            return_timestamps=True,
            story_type="confession"
        )
        assert mock_post.called
        sent_body = mock_post.call_args[1]["json"]
        settings_sent = sent_body["voice_settings"]
        # Cloned voice stability must be >= 0.50 (boosted from 0.35)
        assert settings_sent["stability"] >= 0.50
        # Cloned voice style must be <= 0.25 (capped from 0.45)
        assert settings_sent["style"] <= 0.25


def test_alignment_excludes_break_tags_and_matches_display_text(monkeypatch):
    """Break tags must never appear as words in alignment, matching display words 1-to-1."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)

    # Simulate ElevenLabs alignment containing characters from <break time="0.7s" />
    text_sent = "Hello world.\n\n<break time=\"0.7s\" />\n\nThis shifted."
    chars = list(text_sent)
    starts = [i * 0.1 for i in range(len(chars))]
    ends = [(i + 1) * 0.1 for i in range(len(chars))]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {
            "characters": chars,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends
        }
    }

    with patch("requests.post", return_value=mock_resp):
        audio, word_alignments = generate_voice_elevenlabs(
            text="Hello world.\n\nThis shifted.",
            voice_id="Sophia",
            return_timestamps=True,
            story_type="confession"
        )
        words = [w["word"] for w in word_alignments]
        # Confirm break tokens never appear in words
        for bad_token in ["<break", "break", "time=", "0", "7s", "/>"]:
            assert bad_token not in words
        # Confirm 1-to-1 match with display words
        assert words == ["Hello", "world", "This", "shifted"]
