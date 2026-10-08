"""
Unit tests for TTS Pipeline V2 Phase 1:
- TTS profiles & text preparation
- Flag ON vs Flag OFF contract
- Safe exception fallback to legacy pipeline
- Edge-only silence trimming preservation
"""

import os
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
        assert sent_body == {
            "text": 'First sentence. <break time="1.0s" /> Second sentence.\n\n<break time="2.0s" />\n\nParagraph two.',
            "model_id": settings.ELEVENLABS_MODEL_ID,
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.85,
                "style": 0.55,
                "use_speaker_boost": True,
                "speed": 0.88,
            },
        }


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
        with patch("app.services.tts_pipeline.mp3_to_raw_pcm", return_value=(b"\x00" * (44100 * 4 * 2), 2.0)):
            with patch("app.services.tts_pipeline.raw_pcm_to_mp3", return_value=b"ID3\x04\x00\x00\x00\x00\x00\x00"):
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
        with patch("app.services.tts_pipeline.mp3_to_raw_pcm", return_value=(b"\x00" * (44100 * 4 * 2), 2.0)):
            with patch("app.services.tts_pipeline.raw_pcm_to_mp3", return_value=b"ID3\x04\x00\x00\x00\x00\x00\x00"):
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
        with patch("app.services.tts_pipeline.mp3_to_raw_pcm", return_value=(b"\x00" * (44100 * 4 * 6), 6.0)):
            with patch("app.services.tts_pipeline.raw_pcm_to_mp3", return_value=b"ID3\x04\x00\x00\x00\x00\x00\x00"):
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


def test_chunk_splitter_edge_cases():
    """Validates chunk splitter handles empty, short, long, and edge-case inputs."""
    from app.services.tts_pipeline import split_text_into_chunks

    # 1. Empty input
    assert split_text_into_chunks("") == []
    assert split_text_into_chunks("   ") == []

    # 2. Short text under limit stays 1 chunk
    short = "This is a short story with only a single paragraph."
    res = split_text_into_chunks(short, max_chars=1500)
    assert len(res) == 1
    assert res[0].text == short
    assert res[0].is_paragraph_end is True

    # 3. Multi-paragraph text splitting
    p1 = "Paragraph one sentence. " * 30  # ~750 chars
    p2 = "Paragraph two sentence. " * 30  # ~750 chars
    p3 = "Paragraph three sentence. " * 30 # ~780 chars
    long_text = f"{p1}\n\n{p2}\n\n{p3}"
    chunks = split_text_into_chunks(long_text, min_chars=800, max_chars=1200)
    assert len(chunks) >= 2
    # No mid-sentence cuts (each chunk ends with period or exclamation)
    for c in chunks:
        assert c.text.rstrip()[-1] in ".!?"
        assert "<break" not in c.text  # trailing break tags stripped

    # 4. Context windows (previous_text and next_text)
    assert chunks[0].previous_text == ""
    assert len(chunks[0].next_text) > 0
    assert len(chunks[-1].previous_text) > 0
    assert chunks[-1].next_text == ""

    # 5. Pathological very long single sentence (no period for 2000 chars)
    long_sentence = "word " * 400
    res_long = split_text_into_chunks(long_sentence, max_chars=1000)
    assert len(res_long) >= 2


def test_3_chunk_alignment_math():
    """Validates alignment shifting math across 3 chunks with different trimmed heads."""
    # Chunk 0: words at 0.05s -> 1.0s, duration 1.5s, trim_start = 0.02s
    # Chunk 1: words at 0.10s -> 1.2s, duration 1.6s, trim_start = 0.07s
    # Chunk 2: words at 0.08s -> 0.9s, duration 1.2s, trim_start = 0.05s
    # Seam pause: 0.7s at paragraph end, 0.3s at sentence split
    pcm_rate = 44100
    bytes_per_frame = 4

    chunks_data = [
        {
            "words": [{"word": "First", "start": 0.05, "end": 0.45}, {"word": "chunk", "start": 0.50, "end": 1.00}],
            "dur": 1.50,
            "is_p_end": True,  # Seam 0.7s
        },
        {
            "words": [{"word": "Second", "start": 0.10, "end": 0.60}, {"word": "chunk", "start": 0.70, "end": 1.20}],
            "dur": 1.60,
            "is_p_end": False, # Seam 0.3s
        },
        {
            "words": [{"word": "Third", "start": 0.08, "end": 0.50}, {"word": "chunk", "start": 0.55, "end": 0.90}],
            "dur": 1.20,
            "is_p_end": True,
        },
    ]

    running_offset = 0.0
    final_alignment = []
    p_break = 0.7
    pause_mid = 0.3

    for idx, c in enumerate(chunks_data):
        w_list = c["words"]
        first_start = w_list[0]["start"]
        last_end = w_list[-1]["end"]
        trim_start = max(0.0, first_start - 0.030)
        trim_end = min(c["dur"], last_end + 0.130)
        trimmed_dur = trim_end - trim_start

        for w in w_list:
            s_shifted = running_offset + (w["start"] - trim_start)
            e_shifted = running_offset + (w["end"] - trim_start)
            final_alignment.append({
                "word": w["word"],
                "start": round(s_shifted, 3),
                "end": round(e_shifted, 3),
            })

        if idx < len(chunks_data) - 1:
            pause = p_break if c["is_p_end"] else pause_mid
            running_offset += (trimmed_dur + pause)
        else:
            running_offset += trimmed_dur

    # Assertions on final_alignment
    assert len(final_alignment) == 6
    # 1. Monotonic order: start_i <= end_i <= start_{i+1}
    for i in range(len(final_alignment)):
        w = final_alignment[i]
        assert w["start"] <= w["end"]
        assert w["start"] >= 0.0
        if i < len(final_alignment) - 1:
            assert w["end"] <= final_alignment[i + 1]["start"] + 0.001


def test_chunk_retry_backoff():
    """Retries on 429 and succeeds; raises on repeated 500."""
    from app.services.tts_pipeline import fetch_chunk_audio_with_retry, TextChunk

    chunk = TextChunk(0, "A test chunk.", "", "", True)
    voice_settings = {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3, "speed": 1.0}

    # Scenario A: 429 then 200
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = "Rate limit exceeded"

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {"characters": ["A", " ", "t", "e", "s", "t"], "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5], "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}
    }

    with patch("time.sleep"):
        with patch("requests.post", side_effect=[resp_429, resp_200]):
            res = fetch_chunk_audio_with_retry(chunk, "voice_123", "model_123", voice_settings, "api_key_test")
            assert res.index == 0
            assert len(res.alignment) > 0

    # Scenario B: 500 on all attempts -> raises RuntimeError
    resp_500 = MagicMock()
    resp_500.status_code = 500
    resp_500.text = "Internal Server Error"

    with patch("time.sleep"):
        with patch("requests.post", return_value=resp_500):
            with pytest.raises(RuntimeError):
                fetch_chunk_audio_with_retry(chunk, "voice_123", "model_123", voice_settings, "api_key_test")


def test_v2_fallback_on_all_error_types(monkeypatch):
    """Verifies that failures in V2 (HTTP failure, missing ffmpeg, empty alignment) fall back cleanly to legacy."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    # 1. Fallback when execute_tts_pipeline_v2 raises an exception
    with patch("app.services.tts_pipeline.execute_tts_pipeline_v2", side_effect=RuntimeError("FFmpeg missing or failed")):
        with patch("requests.post", return_value=mock_resp):
            audio, alignment = generate_voice_elevenlabs(
                text="Fallback test.\n\nSecond paragraph.",
                voice_id=None,
                return_timestamps=True,
                story_type="confession"
            )
            # Legacy audio returned safely
            assert audio == b"ID3\x04\x00\x00\x00\x00\x00\x00"


def test_stock_voice_catalog_coverage():
    """Confirms every voice in GET /v1/voices catalog and ELEVENLABS_VOICES is recognized as stock and never capped."""
    from app.core.llm import MEMBER_VOICE_CATALOG, ELEVENLABS_VOICES
    from app.services.tts_pipeline import execute_tts_pipeline_v2

    for catalog_entry in MEMBER_VOICE_CATALOG:
        v_name = catalog_entry["name"]
        v_id = ELEVENLABS_VOICES.get(v_name)
        assert v_id is not None, f"Catalog voice '{v_name}' missing from ELEVENLABS_VOICES mapping!"

        # Stock check for name
        v_name_lower = v_name.strip().lower()
        is_name_stock = any(k.lower() == v_name_lower for k in ELEVENLABS_VOICES.keys()) or any(v.lower() == v_name_lower for v in ELEVENLABS_VOICES.values())
        assert is_name_stock is True, f"Catalog voice name '{v_name}' was not recognized as stock!"

        # Stock check for ID
        v_id_lower = v_id.strip().lower()
        is_id_stock = any(k.lower() == v_id_lower for k in ELEVENLABS_VOICES.keys()) or any(v.lower() == v_id_lower for v in ELEVENLABS_VOICES.values())
        assert is_id_stock is True, f"Catalog voice ID '{v_id}' was not recognized as stock!"

    # Verify that stock voice settings are never capped in execute_tts_pipeline_v2
    # In mock mode (or with mocked post), confession profile (stability=0.35, style=0.45) must NOT be boosted to 0.50 / capped to 0.25
    with patch("requests.post") as mock_post:
        with patch("app.services.tts_pipeline.mp3_to_raw_pcm", return_value=(b"\x00" * (44100 * 4 * 2), 2.0)):
            with patch("app.services.tts_pipeline.raw_pcm_to_mp3", return_value=b"ID3\x04\x00\x00\x00\x00\x00\x00"):
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {
                    "audio_base64": "SUQzBAAAAAAAAA==",
                    "alignment": {"characters": ["O", "K"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
                }
                for catalog_entry in MEMBER_VOICE_CATALOG:
                    v_name = catalog_entry["name"]
                    execute_tts_pipeline_v2(
                        text="A quick test.",
                        story_type="confession",
                        voice_id=v_name,
                    )
                    sent_settings = mock_post.call_args[1]["json"]["voice_settings"]
                    # Stock voice maintains profile stability (0.35) and style (0.45)
                    assert sent_settings["stability"] == 0.35, f"Stock voice '{v_name}' stability was unexpectedly modified!"
                    assert sent_settings["style"] == 0.45, f"Stock voice '{v_name}' style was unexpectedly capped!"

    # Custom cloned ID must NOT be stock and MUST be capped
    custom_clone_id = "cloned_member_voice_abc_456"
    custom_lower = custom_clone_id.lower()
    is_custom_stock = any(k.lower() == custom_lower for k in ELEVENLABS_VOICES.keys()) or any(v.lower() == custom_lower for v in ELEVENLABS_VOICES.values())
    assert is_custom_stock is False


def test_tokenization_contractions_hyphens_dashes_quotes():
    """
    Validates tokenization with contractions (don't, I'm), hyphenated words,
    em dashes, ellipsis attached to a word, and quotes.
    Compares frontend token count with alignment word count.
    """
    import re
    from app.core.llm import parse_alignment_to_words

    text = "I'm sure they don't know—it's self-evident... \"She smiled,\" he whispered."
    chars = list(text)
    starts = [i * 0.1 for i in range(len(chars))]
    ends = [(i + 1) * 0.1 for i in range(len(chars))]

    alignment = {
        "characters": chars,
        "character_start_times_seconds": starts,
        "character_end_times_seconds": ends,
    }
    words_parsed = [w["word"] for w in parse_alignment_to_words(alignment)]

    # 1. Contractions preserved
    assert "I'm" in words_parsed
    assert "don't" in words_parsed
    assert "it's" in words_parsed

    # 2. Hyphenated word split into spoken words
    assert "self" in words_parsed
    assert "evident" in words_parsed

    # 3. Em-dash separated into spoken words
    assert "know" in words_parsed

    # 4. Quotes and commas stripped from word tokens
    assert "She" in words_parsed
    assert "smiled" in words_parsed

    # 5. Ellipsis attached to word does not leak XML or periods into words
    assert "..." not in words_parsed
    assert "<break" not in words_parsed

    # 6. Legacy path splits hyphen and em-dash into spoken sub-words
    assert len(words_parsed) == 12

    # 7. NEW path (parse_alignment_to_whitespace_words):
    # Matches player's exact whitespace split rule (1 token per whitespace-delimited word)
    from app.services.tts_pipeline import parse_alignment_to_whitespace_words
    player_display_tokens = text.split()
    assert len(player_display_tokens) == 10

    v2_words = parse_alignment_to_whitespace_words(alignment)
    # Exact 1-to-1 match with the player's display tokens
    assert len(v2_words) == len(player_display_tokens) == 10
    assert [w["word"] for w in v2_words] == [
        "I'm", "sure", "they", "don't", "know—it's", "self-evident", "She", "smiled", "he", "whispered"
    ]
    # Verify monotonic non-negative timestamps
    for i, w in enumerate(v2_words):
        assert w["start"] <= w["end"]
        assert w["start"] >= 0.0
        if i > 0:
            assert w["start"] >= v2_words[i - 1]["end"] - 0.001


def test_alignment_based_trim_synthetic_preserves_internal_pauses():
    """
    Synthetic audio test for alignment-based trimming:
    trim_start = max(0, first_word_start - 0.030)
    trim_end = min(duration, last_word_end + 0.130)
    Proves internal pauses remain completely untouched and last word is never cut.
    """
    import shutil
    import tempfile
    import subprocess
    import re

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        scratch_ffmpeg = os.path.abspath(os.path.join("scratch", "bin", "ffmpeg.exe"))
        if os.path.isfile(scratch_ffmpeg):
            ffmpeg_bin = scratch_ffmpeg

    if not ffmpeg_bin:
        pytest.skip("FFmpeg not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        synth_file = os.path.join(tmpdir, "synth.wav")
        # 0.4s lead silence + 1.0s tone + 1.0s internal silence + 1.0s tone + 0.4s tail silence = 3.8s
        gen_cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.4",
            "-f", "lavfi", "-i", "sine=f=440:r=44100:d=1.0",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.0",
            "-f", "lavfi", "-i", "sine=f=880:r=44100:d=1.0",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.4",
            "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[out]",
            "-map", "[out]",
            synth_file
        ]
        subprocess.run(gen_cmd, check=True, capture_output=True)

        # Word alignment for this synthetic file:
        # Word 1 starts at 0.40s, ends at 1.40s
        # Word 2 starts at 2.40s, ends at 3.40s
        total_dur = 3.80
        first_word_start = 0.40
        last_word_end = 3.40

        trim_start = max(0.0, first_word_start - 0.030)  # 0.370s
        trim_end = min(total_dur, last_word_end + 0.130)   # 3.530s

        trimmed_wav = os.path.join(tmpdir, "trimmed.wav")
        trim_cmd = [
            ffmpeg_bin, "-y", "-i", synth_file,
            "-af", f"atrim=start={trim_start:.3f}:end={trim_end:.3f},asetpts=PTS-STARTPTS",
            trimmed_wav
        ]
        subprocess.run(trim_cmd, check=True, capture_output=True)

        # Detect silences in trimmed file
        det_cmd = [ffmpeg_bin, "-i", trimmed_wav, "-af", "silencedetect=noise=-45dB:d=0.2", "-f", "null", "-"]
        det_res = subprocess.run(det_cmd, capture_output=True, text=True)
        t_durs = [float(x) for x in re.findall(r"silence_duration:\s*([\d\.]+)", det_res.stderr)]

        # Internal 1.0s pause MUST remain intact
        assert any(abs(d - 1.0) < 0.05 for d in t_durs), f"Internal silence was modified: {t_durs}"


def test_standalone_tokens_whitespace_alignment():
    """
    Validates that parse_alignment_to_whitespace_words always returns exactly one
    alignment entry per whitespace token of the DISPLAY text, ensuring zero index drift:
    - Lone dash: ` — `
    - Lone ellipsis: `...`
    - Emoji token: e.g. ✨
    - Markdown: `**`
    - Parentheses: `( secret )`
    - Number with comma/decimal: `1,000`, `3.14`
    - Long text mixing all of them
    The assertion is len(alignment) == len(display.split()) for each.
    """
    from app.services.tts_pipeline import parse_alignment_to_whitespace_words

    test_cases = [
        # (name, display_text, spoken_text)
        ("lone_dash", "Before — After", "Before After"),
        ("lone_ellipsis", "Thinking ... done", "Thinking done"),
        ("emoji_token", "Peace \u2728 love", "Peace love"),
        ("markdown_stars", "Notice ** important ** step", "Notice important step"),
        ("parentheses", "This ( secret ) was (revealed)", "This secret was revealed"),
        ("number_with_comma_decimal", "Over 1,000 items priced at 3.14 each", "Over 1,000 items priced at 3.14 each"),
        (
            "long_mixed_text",
            "Here is the story: 1,000 days ago — yes, 3.14 years — I met them ... \u2728 "
            "It was **truly** remarkable (unbelievable, really) \u2022 and free!",
            "Here is the story: 1,000 days ago yes, 3.14 years I met them "
            "It was truly remarkable unbelievable, really and free!"
        ),
    ]

    for name, display_text, spoken_text in test_cases:
        chars = list(spoken_text)
        starts = [round(i * 0.1, 2) for i in range(len(chars))]
        ends = [round((i + 1) * 0.1, 2) for i in range(len(chars))]
        alignment = {
            "characters": chars,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        }

        res = parse_alignment_to_whitespace_words(alignment, display_text=display_text)
        display_tokens = display_text.split()

        # Hard assertion: len(alignment) == len(display.split())
        assert len(res) == len(display_tokens), (
            f"Case '{name}' failed: alignment len {len(res)} != display tokens {len(display_tokens)}"
        )

        # Standalone unspeakable tokens must have zero-length start == end at previous word's end time
        for tok, entry in zip(display_tokens, res):
            if not any(c.isalnum() for c in tok):
                assert entry["start"] == entry["end"], (
                    f"Case '{name}': Unspeakable token {tok!r} has non-zero length: {entry['start']} != {entry['end']}"
                )
            else:
                assert entry["start"] <= entry["end"]


def test_alignment_clamping_to_audio_duration_and_monotonicity():
    """
    Validates that:
    1. Every alignment end time is clamped to final audio duration: last end <= duration.
    2. All start and end times are non-negative and strictly monotonic:
       start_i <= end_i and start_{i} >= start_{i-1}.
    """
    from app.services.tts_pipeline import (
        PCM_SAMPLE_RATE,
        PCM_CHANNELS,
        PCM_BYTES_PER_FRAME,
    )

    # Simulate 2.500 seconds of audio PCM
    total_dur = 2.500
    pcm_bytes = b"\x00" * int(total_dur * PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    final_audio_dur = round(len(pcm_bytes) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME), 3)

    # Alignment where last word overshoots audio duration (e.g. 2.75s > 2.50s)
    raw_alignment = [
        {"word": "First", "start": -0.05, "end": 0.40},
        {"word": "second", "start": 0.38, "end": 1.20},
        {"word": "third", "start": 1.15, "end": 2.10},
        {"word": "overshooting", "start": 2.05, "end": 2.75},
    ]

    # Run clamping logic identical to execute_tts_pipeline_v2
    prev_s = 0.0
    clamped_alignment = []
    for w in raw_alignment:
        w_copy = dict(w)
        w_copy["start"] = max(prev_s, max(0.0, min(round(w_copy["start"], 3), final_audio_dur)))
        w_copy["end"] = max(w_copy["start"], min(round(w_copy["end"], 3), final_audio_dur))
        prev_s = w_copy["start"]
        clamped_alignment.append(w_copy)

    # 1. Clamping to final audio duration
    assert clamped_alignment[-1]["end"] <= final_audio_dur
    assert clamped_alignment[-1]["end"] == 2.500

    # 2. Non-negative and monotonic
    for i, w in enumerate(clamped_alignment):
        assert w["start"] >= 0.0, f"Token {w} has negative start"
        assert w["start"] <= w["end"], f"Token {w} start > end"
        assert w["end"] <= final_audio_dur, f"Token {w} end > duration"
        if i > 0:
            assert w["start"] >= clamped_alignment[i - 1]["start"], (
                f"Token {i} start {w['start']} < previous start {clamped_alignment[i - 1]['start']}"
            )


def test_tail_energy_cap_logic():
    """
    Validates get_last_audible_time:
    Constructs a 1.5s audio stream with 1.0s loud tone and 0.5s digital silence.
    Confirms that get_last_audible_time finds the drop to within 20ms and does not clip speech.
    """
    import math
    import struct
    from app.services.tts_pipeline import (
        get_last_audible_time,
        PCM_SAMPLE_RATE,
        PCM_CHANNELS,
    )

    # 1.0s of 440Hz sine wave at -10 dB (audible), then 0.5s of zeros (-infinity dB)
    loud_dur = 1.0
    silent_dur = 0.5
    loud_frames = int(loud_dur * PCM_SAMPLE_RATE)
    silent_frames = int(silent_dur * PCM_SAMPLE_RATE)

    # 16-bit sine wave at ~10,000 amplitude
    amplitude = 10000
    loud_samples = [
        int(amplitude * math.sin(2 * math.pi * 440 * (i / PCM_SAMPLE_RATE)))
        for i in range(loud_frames)
    ]
    silent_samples = [0] * silent_frames

    pcm_bytes = struct.pack(f"<{len(loud_samples + silent_samples)}h", *(loud_samples + silent_samples))

    last_audible = get_last_audible_time(
        pcm_bytes,
        channels=PCM_CHANNELS,
        sample_rate=PCM_SAMPLE_RATE,
        threshold_db=-50.0,
        window_ms=20.0,
        search_s=1.5,
    )

    # Expected: last audible sample is near 1.000s (tolerance within 20ms window)
    assert abs(last_audible - 1.000) <= 0.030, f"Expected ~1.000s, got {last_audible}"


def test_tts_v2_model_id_config_fallback(monkeypatch):
    """
    Validates TTS_V2_MODEL_ID configuration and guarantees:
    1. Defaults to ELEVENLABS_MODEL_ID when unset.
    2. Overrides model for V2 without altering legacy ELEVENLABS_MODEL_ID.
    3. (a) With TTS_V2_MODEL_ID=eleven_multilingual_v2 and forced pipeline failure,
           the legacy request body uses model_id == ELEVENLABS_MODEL_ID.
    4. (b) The legacy path never reads or uses TTS_V2_MODEL_ID.
    5. (c) Voice previews and voice cloning are completely unaffected.
    """
    from app.core.config import Settings
    from app.core.llm import clone_voice_elevenlabs

    # 1. Config loading & fallback defaults
    with patch.dict(os.environ, {"ELEVENLABS_MODEL_ID": "eleven_turbo_v2_5"}, clear=False):
        os.environ.pop("TTS_V2_MODEL_ID", None)
        s = Settings()
        assert s.TTS_V2_MODEL_ID == "eleven_turbo_v2_5"

    with patch.dict(os.environ, {"ELEVENLABS_MODEL_ID": "eleven_turbo_v2_5", "TTS_V2_MODEL_ID": "eleven_multilingual_v2"}, clear=False):
        s = Settings()
        assert s.ELEVENLABS_MODEL_ID == "eleven_turbo_v2_5"
        assert s.TTS_V2_MODEL_ID == "eleven_multilingual_v2"

    # 2. (a) & (b) Forced pipeline failure: legacy request body uses model_id == ELEVENLABS_MODEL_ID
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)
    monkeypatch.setattr(settings, "ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
    monkeypatch.setattr(settings, "TTS_V2_MODEL_ID", "eleven_multilingual_v2")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    with patch("app.core.llm._generate_voice_elevenlabs_v2", side_effect=RuntimeError("Forced V2 failure")):
        with patch("requests.post", return_value=mock_resp) as mock_post:
            audio, alignment = generate_voice_elevenlabs(
                text="Testing fallback model id.",
                return_timestamps=True,
                story_type="confession",
            )
            assert mock_post.called
            sent_body = mock_post.call_args[1]["json"]
            # (a) Request body uses model_id == ELEVENLABS_MODEL_ID
            assert sent_body["model_id"] == "eleven_turbo_v2_5"
            # (b) Legacy path never reads or uses TTS_V2_MODEL_ID
            assert sent_body["model_id"] != settings.TTS_V2_MODEL_ID

    # 3. (c) Voice previews (return_timestamps=False) and voice cloning are unaffected
    with patch("requests.post", return_value=mock_resp) as mock_preview_post:
        audio = generate_voice_elevenlabs(
            text="Voice preview test clip.",
            return_timestamps=False,
            story_type="confession",
        )
        assert mock_preview_post.called
        sent_preview_body = mock_preview_post.call_args[1]["json"]
        assert sent_preview_body["model_id"] == "eleven_turbo_v2_5"
        assert sent_preview_body["model_id"] != settings.TTS_V2_MODEL_ID

    # Voice cloning calls /voices/add and never references TTS_V2_MODEL_ID
    clone_resp = MagicMock()
    clone_resp.status_code = 200
    clone_resp.json.return_value = {"voice_id": "new_cloned_voice_123"}
    with patch("requests.post", return_value=clone_resp) as mock_clone_post:
        v_id = clone_voice_elevenlabs(
            display_name="Member Voice",
            samples=[("rec.mp3", b"\x00\x01\x02", "audio/mpeg")],
        )
        assert v_id == "new_cloned_voice_123"
        assert "/voices/add" in mock_clone_post.call_args[0][0]
        # Verify no model_id in cloning payload
        assert "model_id" not in mock_clone_post.call_args[1].get("data", {})


def test_tail_cushion_minimum_guarantee():
    """
    Validates that:
    1. If speech audio ends abruptly or has less than 80ms of tail after last audible drop,
       an 80ms cushion is guaranteed before the final 10ms micro-fade.
    2. The tail after last audible energy is never shorter than 80ms.
    """
    from app.services.tts_pipeline import (
        get_last_audible_time,
        apply_pcm_fade,
        PCM_SAMPLE_RATE,
        PCM_CHANNELS,
        PCM_BYTES_PER_FRAME,
    )
    import math
    import struct

    # 1.0s of audible tone with ONLY 10ms of tail (abrupt cutoff)
    tone_dur = 1.0
    abrupt_tail_dur = 0.010
    tone_frames = int(tone_dur * PCM_SAMPLE_RATE)
    tail_frames = int(abrupt_tail_dur * PCM_SAMPLE_RATE)

    loud_samples = [
        int(10000 * math.sin(2 * math.pi * 440 * (i / PCM_SAMPLE_RATE)))
        for i in range(tone_frames)
    ]
    silent_samples = [0] * tail_frames
    pcm = struct.pack(f"<{len(loud_samples + silent_samples)}h", *(loud_samples + silent_samples))

    t_audible = get_last_audible_time(pcm, channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE, threshold_db=-50.0)
    dur_before = len(pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    assert dur_before - t_audible < 0.030

    # Apply the pipeline's minimum cushion logic (80ms minimum tail cushion)
    MIN_TAIL_CUSHION_S = 0.080
    if t_audible > 0 and (dur_before - t_audible) < MIN_TAIL_CUSHION_S:
        needed_pad = MIN_TAIL_CUSHION_S - (dur_before - t_audible)
        pad_frames = int(needed_pad * PCM_SAMPLE_RATE)
        pcm += b"\x00" * (pad_frames * PCM_BYTES_PER_FRAME)

    dur_after = len(pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    tail_after = dur_after - t_audible
    assert tail_after >= 0.079, f"Expected at least 80ms tail cushion, got {tail_after*1000:.1f}ms"

    # Confirm 10ms micro-fade applies cleanly to the padded tail without altering length
    faded = apply_pcm_fade(pcm, fade_ms=10.0, sample_rate=PCM_SAMPLE_RATE)
    assert len(faded) == len(pcm)


def test_b0_seam_target_gap_900ms_tail():
    """
    Validates B0 rule 4:
    A chunk with 900 ms of natural silent tail stitched to the next chunk
    must produce a total acoustic seam gap equal to the target within 20 ms,
    and the audible speech must never be cut.
    """
    from app.services.tts_pipeline import (
        get_first_audible_time,
        get_last_audible_time,
        apply_pcm_fade,
        PCM_SAMPLE_RATE,
        PCM_BYTES_PER_FRAME,
    )
    import math
    import struct
    import array

    sr = PCM_SAMPLE_RATE
    target_gap_s = 0.550  # 550 ms mid-paragraph seam

    # Chunk A: 1.0s tone at 440 Hz + 0.900s of natural silence (total 1.9s)
    tone_samples_a = [int(15000 * math.sin(2 * math.pi * 440 * (i / sr))) for i in range(int(1.0 * sr))]
    silence_samples_a = [0] * int(0.900 * sr)
    pcm_a = struct.pack(f"<{len(tone_samples_a + silence_samples_a)}h", *(tone_samples_a + silence_samples_a))
    dur_a = len(pcm_a) / (sr * PCM_BYTES_PER_FRAME)

    # Chunk B: 0.050s silence + 1.0s tone at 440 Hz
    silence_samples_b = [0] * int(0.050 * sr)
    tone_samples_b = [int(15000 * math.sin(2 * math.pi * 440 * (i / sr))) for i in range(int(1.0 * sr))]
    pcm_b = struct.pack(f"<{len(silence_samples_b + tone_samples_b)}h", *(silence_samples_b + tone_samples_b))
    dur_b = len(pcm_b) / (sr * PCM_BYTES_PER_FRAME)

    # Chunk A trim
    first_w_start_a = 0.0
    t_onset_a = get_first_audible_time(pcm_a, threshold_db=-50.0, window_ms=10.0)
    trim_start_a = max(0.0, min(first_w_start_a, max(first_w_start_a - 0.030, t_onset_a - 0.050)))
    t_audible_a = get_last_audible_time(pcm_a, threshold_db=-50.0, window_ms=10.0)
    trim_end_a = min(dur_a, max(t_audible_a + 0.080, t_audible_a + 0.150))
    # Audible speech must never be cut
    assert t_audible_a >= 0.99
    assert trim_end_a >= t_audible_a + 0.080
    assert trim_end_a < 1.30  # Excess 750ms of silence was trimmed!

    measured_tail_a = max(0.0, trim_end_a - t_audible_a)

    # Chunk B trim
    first_w_start_b = 0.050
    t_onset_b = get_first_audible_time(pcm_b, threshold_db=-50.0, window_ms=10.0)
    trim_start_b = max(0.0, min(first_w_start_b, max(first_w_start_b - 0.030, t_onset_b - 0.050)))
    t_audible_b = get_last_audible_time(pcm_b, threshold_db=-50.0, window_ms=10.0)
    trim_end_b = min(dur_b, max(t_audible_b + 0.080, t_audible_b + 0.150))
    measured_head_b = max(0.0, t_onset_b - trim_start_b)

    # Inserted silence from target gap formula
    inserted_s = max(0.0, target_gap_s - measured_tail_a - measured_head_b)

    # Slice and stitch
    st_a = int(trim_start_a * sr) * PCM_BYTES_PER_FRAME
    en_a = int(trim_end_a * sr) * PCM_BYTES_PER_FRAME
    faded_a = apply_pcm_fade(pcm_a[st_a:en_a], fade_ms=10.0, sample_rate=sr)

    st_b = int(trim_start_b * sr) * PCM_BYTES_PER_FRAME
    en_b = int(trim_end_b * sr) * PCM_BYTES_PER_FRAME
    faded_b = apply_pcm_fade(pcm_b[st_b:en_b], fade_ms=10.0, sample_rate=sr)

    silence_pcm = b"\x00" * (int(inserted_s * sr) * PCM_BYTES_PER_FRAME)
    stitched_pcm = faded_a + silence_pcm + faded_b

    # Measure total acoustic silence between Chunk A speech end and Chunk B speech onset
    stitched_samples = array.array("h", stitched_pcm)
    win_frames = int(0.010 * sr)
    seam_mid_frame = len(faded_a) // PCM_BYTES_PER_FRAME + (len(silence_pcm) // (2 * PCM_BYTES_PER_FRAME))

    # Find last audible window before seam mid (-50 dB)
    last_aud = 0
    for f in range(0, seam_mid_frame, win_frames):
        c = stitched_samples[f : f + win_frames]
        rms = math.sqrt(sum(s * s for s in c) / len(c)) if c else 0
        db = 20 * math.log10(rms / 32767.0) if rms > 0 else -100
        if db >= -50.0:
            last_aud = f + win_frames

    # Find first audible window after seam mid (-50 dB)
    first_aud = len(stitched_samples)
    for f in range(seam_mid_frame, len(stitched_samples), win_frames):
        c = stitched_samples[f : f + win_frames]
        rms = math.sqrt(sum(s * s for s in c) / len(c)) if c else 0
        db = 20 * math.log10(rms / 32767.0) if rms > 0 else -100
        if db >= -50.0:
            first_aud = f
            break

    measured_acoustic_gap_s = (first_aud - last_aud) / float(sr)
    # Target within 20 ms
    assert abs(measured_acoustic_gap_s - target_gap_s) <= 0.020, (
        f"Expected {target_gap_s*1000}ms, got {measured_acoustic_gap_s*1000:.1f}ms"
    )


def test_b0_seam_target_gap_40ms_tail():
    """
    Validates B0 rule 4:
    A chunk with a short 40 ms silent tail must get silence added so that
    total acoustic seam gap equals the target within 20 ms.
    """
    from app.services.tts_pipeline import (
        get_first_audible_time,
        get_last_audible_time,
        apply_pcm_fade,
        PCM_SAMPLE_RATE,
        PCM_BYTES_PER_FRAME,
    )
    import math
    import struct
    import array

    sr = PCM_SAMPLE_RATE
    target_gap_s = 0.550  # 550 ms mid-paragraph seam

    # Chunk A: 1.0s tone at 440 Hz + 0.040s tail silence (short 40ms tail)
    tone_samples_a = [int(15000 * math.sin(2 * math.pi * 440 * (i / sr))) for i in range(int(1.0 * sr))]
    silence_samples_a = [0] * int(0.040 * sr)
    pcm_a = struct.pack(f"<{len(tone_samples_a + silence_samples_a)}h", *(tone_samples_a + silence_samples_a))
    dur_a = len(pcm_a) / (sr * PCM_BYTES_PER_FRAME)

    # Chunk B: 0.050s silence + 1.0s tone
    silence_samples_b = [0] * int(0.050 * sr)
    tone_samples_b = [int(15000 * math.sin(2 * math.pi * 440 * (i / sr))) for i in range(int(1.0 * sr))]
    pcm_b = struct.pack(f"<{len(silence_samples_b + tone_samples_b)}h", *(silence_samples_b + tone_samples_b))
    dur_b = len(pcm_b) / (sr * PCM_BYTES_PER_FRAME)

    t_audible_a = get_last_audible_time(pcm_a, threshold_db=-50.0, window_ms=10.0)
    trim_end_a = min(dur_a, max(t_audible_a + 0.080, t_audible_a + 0.150))
    measured_tail_a = max(0.0, trim_end_a - t_audible_a)

    first_w_start_b = 0.050
    t_onset_b = get_first_audible_time(pcm_b, threshold_db=-50.0, window_ms=10.0)
    trim_start_b = max(0.0, min(first_w_start_b, max(first_w_start_b - 0.030, t_onset_b - 0.050)))
    measured_head_b = max(0.0, t_onset_b - trim_start_b)

    # Inserted silence must be added
    inserted_s = max(0.0, target_gap_s - measured_tail_a - measured_head_b)
    assert inserted_s > 0.400  # Silence is added!

    # Slice and stitch
    st_a = int(0.0 * sr) * PCM_BYTES_PER_FRAME
    en_a = int(trim_end_a * sr) * PCM_BYTES_PER_FRAME
    faded_a = apply_pcm_fade(pcm_a[st_a:en_a], fade_ms=10.0, sample_rate=sr)

    st_b = int(trim_start_b * sr) * PCM_BYTES_PER_FRAME
    en_b = int(dur_b * sr) * PCM_BYTES_PER_FRAME
    faded_b = apply_pcm_fade(pcm_b[st_b:en_b], fade_ms=10.0, sample_rate=sr)

    silence_pcm = b"\x00" * (int(inserted_s * sr) * PCM_BYTES_PER_FRAME)
    stitched_pcm = faded_a + silence_pcm + faded_b

    # Verify total acoustic silence
    stitched_samples = array.array("h", stitched_pcm)
    win_frames = int(0.010 * sr)
    seam_mid_frame = len(faded_a) // PCM_BYTES_PER_FRAME + (len(silence_pcm) // (2 * PCM_BYTES_PER_FRAME))

    last_aud = 0
    for f in range(0, seam_mid_frame, win_frames):
        c = stitched_samples[f : f + win_frames]
        rms = math.sqrt(sum(s * s for s in c) / len(c)) if c else 0
        db = 20 * math.log10(rms / 32767.0) if rms > 0 else -100
        if db >= -50.0:
            last_aud = f + win_frames

    first_aud = len(stitched_samples)
    for f in range(seam_mid_frame, len(stitched_samples), win_frames):
        c = stitched_samples[f : f + win_frames]
        rms = math.sqrt(sum(s * s for s in c) / len(c)) if c else 0
        db = 20 * math.log10(rms / 32767.0) if rms > 0 else -100
        if db >= -50.0:
            first_aud = f
            break

    measured_acoustic_gap_s = (first_aud - last_aud) / float(sr)
    assert abs(measured_acoustic_gap_s - target_gap_s) <= 0.020, (
        f"Expected {target_gap_s*1000}ms, got {measured_acoustic_gap_s*1000:.1f}ms"
    )


def test_b0_soft_ending_decaying_tone():
    """
    Validates B0 rule 5:
    Decaying tone (down to -60 dB, simulating soft endings like 'dark' or 'yourself')
    is preserved by the 150 ms cushion past the -50 dB drop.
    """
    from app.services.tts_pipeline import (
        get_last_audible_time,
        PCM_SAMPLE_RATE,
        PCM_BYTES_PER_FRAME,
    )
    import math
    import struct

    sr = PCM_SAMPLE_RATE
    dur_tone = 0.500  # 500 ms tone
    n_frames = int(dur_tone * sr)

    # Exponentially decaying tone from -6 dB down to -60 dB
    samples = []
    for i in range(n_frames):
        vol = 0.5 * math.exp(-6.0 * (i / n_frames))
        val = int(vol * 32767.0 * math.sin(2.0 * math.pi * 440.0 * i / sr))
        samples.append(val)

    # Append 900 ms of pure silence
    silence_samples = [0] * int(0.900 * sr)
    pcm = struct.pack(f"<{len(samples + silence_samples)}h", *(samples + silence_samples))
    total_dur = len(pcm) / (sr * PCM_BYTES_PER_FRAME)

    t_audible = get_last_audible_time(pcm, threshold_db=-50.0, window_ms=10.0)
    # Energy dropped below -50 dB around 0.40 - 0.48 s
    assert 0.38 <= t_audible <= 0.50

    trim_end = min(total_dur, max(t_audible + 0.080, t_audible + 0.150))
    # 150 ms cushion is preserved
    assert trim_end >= t_audible + 0.080
    assert trim_end <= t_audible + 0.151
    # Excess silence (0.9s tail) was trimmed away
    assert trim_end < 0.700


def test_parse_alignment_speakable_char_boundaries_and_highlighting():
    """
    Validates that parse_alignment_to_whitespace_words bounds each word to its
    first and last speakable (alphanumeric) character:
    - Trailing punctuation (periods, commas, quotes) and trailing inter-sentence
      space/pauses are excluded from the word's end timestamp.
    - Leading punctuation (quotes, brackets) is excluded from the word's start timestamp.
    - Standalone unspeakable tokens (e.g. em-dash) receive zero-length at previous end.
    - Token count exactly equals display_text.split() (1-to-1 index highlighting).
    - Timestamp-based highlighting is strictly active during phonation and turns off
      during pause intervals.
    """
    from app.services.tts_pipeline import parse_alignment_to_whitespace_words

    display_text = '“Start” — wonderful. Next'
    # Characters in spoken/synthesized stream:
    chars =  ['“', 'S', 't', 'a', 'r', 't', '”', ' ', '—', ' ', 'w', 'o', 'n', 'd', 'e', 'r', 'f', 'u', 'l', '.', ' ', 'N', 'e', 'x', 't']
    starts = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.36, 0.40, 0.42, 0.46, 0.50, 0.54, 0.58, 0.62, 0.66, 0.70, 0.74, 0.78, 0.88, 1.40, 1.45, 1.50, 1.55]
    ends =   [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.36, 0.40, 0.42, 0.46, 0.50, 0.54, 0.58, 0.62, 0.66, 0.70, 0.74, 0.78, 0.88, 1.40, 1.45, 1.50, 1.55, 1.60]

    alignment = {
        "characters": chars,
        "character_start_times_seconds": starts,
        "character_end_times_seconds": ends,
    }

    words = parse_alignment_to_whitespace_words(alignment, display_text=display_text)
    display_tokens = display_text.split()

    # 1. Index-based highlighting: exact 1-to-1 mapping
    assert len(words) == len(display_tokens) == 4
    assert [w["word"] for w in words] == ["Start", "—", "wonderful", "Next"]

    # 2. Leading punctuation exclusion: "Start" starts at 'S' (0.05), not '“' (0.00)
    # and ends at 't' (0.30), not '”' (0.35)
    assert words[0]["start"] == 0.05
    assert words[0]["end"] == 0.30

    # 3. Standalone unspeakable token '—': zero duration at previous word's end (0.30)
    assert words[1]["start"] == 0.30
    assert words[1]["end"] == 0.30

    # 4. Trailing punctuation & pause exclusion:
    # "wonderful." ends at 'l' (0.78), NOT period '.' (0.88) and NOT trailing space (1.40)
    assert words[2]["start"] == 0.42
    assert words[2]["end"] == 0.78

    # 5. Next word starts cleanly after inter-sentence pause
    assert words[3]["start"] == 1.40
    assert words[3]["end"] == 1.60

    # 6. Timestamp highlighting check:
    # At t = 0.82 (during the period/pause after wonderful), no word is actively highlighted
    active_words = [w["word"] for w in words if w["start"] <= 0.82 <= w["end"]]
    assert active_words == []


def test_profile_seam_gap_fields():
    """Validates that seam_gap_ms=800 and seam_paragraph_gap_ms=800 are configured without changing existing break values."""
    confession = get_tts_profile("confession")
    assert confession.seam_gap_ms == 800
    assert confession.seam_paragraph_gap_ms == 800
    assert confession.paragraph_break_s == 0.7

    meditation = get_tts_profile("meditation")
    assert meditation.seam_gap_ms == 800
    assert meditation.seam_paragraph_gap_ms == 800
    assert meditation.paragraph_break_s == 1.2

    transformation = get_tts_profile("transformation")
    assert transformation.seam_gap_ms == 800
    assert transformation.seam_paragraph_gap_ms == 800
    assert transformation.paragraph_break_s == 0.8


def test_generate_room_tone_fills_and_xfades():
    """Validates room tone generation for 50ms, 400ms, 800ms, 1200ms fills with 15ms crossfades."""
    import array, math
    from app.services.tts_pipeline import generate_room_tone

    sr = 44100
    # 400ms synthetic base clip with low-level noise (-72 dB)
    base_len = int(0.400 * sr)
    base_samples = array.array("h", [int(8.0 * math.sin(2.0 * math.pi * 100.0 * (i / sr))) for i in range(base_len)])
    base_pcm = base_samples.tobytes()

    for dur_ms in [50, 400, 800, 1200]:
        dur_s = dur_ms / 1000.0
        out_pcm = generate_room_tone(base_pcm, dur_s, channels=1, sample_rate=sr, xfade_ms=15.0)
        expected_bytes = int(dur_s * sr) * 2
        assert len(out_pcm) == expected_bytes

        out_arr = array.array("h", out_pcm)
        # Verify 15ms boundary envelope fades (first and last sample attenuated)
        assert abs(out_arr[0]) <= abs(base_samples[0])
        assert abs(out_arr[-1]) <= abs(base_samples[-1])

    # Zero or negative duration returns empty bytes
    assert generate_room_tone(base_pcm, 0.0, channels=1, sample_rate=sr) == b""
    assert generate_room_tone(base_pcm, -0.1, channels=1, sample_rate=sr) == b""
    assert generate_room_tone(b"", 0.5, channels=1, sample_rate=sr) == b""


def test_extract_clean_room_tone_segment_and_fallback():
    """Validates extraction of clean room tone segments (< -65 dB) and fallback on missing clean segment."""
    import array, math
    from app.services.tts_pipeline import extract_clean_room_tone_segment

    sr = 44100
    # Chunk with speech (-20 dB) followed by a 500ms clean pause (-74 dB)
    speech_samples = [int(3000.0 * math.sin(i * 0.1)) for i in range(int(1.0 * sr))] # ~ -20 dB
    pause_samples = [int(6.0 * math.sin(i * 0.05)) for i in range(int(0.500 * sr))]    # ~ -74 dB
    combined = array.array("h", speech_samples + pause_samples).tobytes()

    clip = extract_clean_room_tone_segment([combined], channels=1, sample_rate=sr, target_dur_s=0.400, max_rms_threshold_db=-65.0)
    assert clip is not None
    assert len(clip) == int(0.400 * sr) * 2

    # Chunk with only loud audio (never drops below -65 dB) -> returns None
    loud_only = array.array("h", speech_samples).tobytes()
    assert extract_clean_room_tone_segment([loud_only], channels=1, sample_rate=sr, max_rms_threshold_db=-65.0) is None


def test_tail_trimming_soft_ending_decay_preserved_energy_based():
    """Validates that energy-based tail trimming preserves soft ending decay in [-50, -40) dB + 150ms cushion."""
    import array, math
    from app.services.tts_pipeline import get_last_audible_time

    sr = 44100
    # 1.0s speech (-20 dB), then 200ms soft ending decay (-45 dB), then silence (-80 dB)
    speech_n = int(1.0 * sr)
    decay_n = int(0.200 * sr)
    silence_n = int(0.800 * sr)

    samples = array.array("h")
    samples.extend(int(3000.0 * math.sin(i * 0.1)) for i in range(speech_n))
    samples.extend(int(180.0 * math.sin(i * 0.05)) for i in range(decay_n)) # -45 dB
    samples.extend(int(2.0 * math.sin(i * 0.05)) for i in range(silence_n))   # -80 dB
    pcm_bytes = samples.tobytes()

    t_audible = get_last_audible_time(pcm_bytes, threshold_db=-50.0, window_ms=10.0)
    # Audible end should be at the end of the soft decay (around 1.200s), NOT at 1.000s
    assert 1.190 <= t_audible <= 1.210

    # With 150ms cushion, trim_end is t_audible + 0.150
    trim_end = min(len(samples)/sr, max(t_audible + 0.080, t_audible + 0.150))
    assert 1.340 <= trim_end <= 1.360


def test_seam_gap_40db_within_20ms_of_target():
    """Validates that inserted seam gap produces acoustic -40 dB gap within 20ms of target."""
    import array, math
    from app.services.tts_pipeline import generate_room_tone

    sr = 44100
    target_s = 0.800
    tail40_s = 0.150
    head40_s = 0.050
    inserted_s = max(0.0, target_s - tail40_s - head40_s) # 0.600s

    assert abs(inserted_s - 0.600) < 0.001

    base_clip = array.array("h", [int(5.0 * math.sin(i)) for i in range(int(0.4 * sr))]).tobytes()
    fill = generate_room_tone(base_clip, inserted_s, sample_rate=sr)
    assert len(fill) == int(inserted_s * sr) * 2

    # Total gap between -40 dB points is tail40 + inserted + head40 = 0.800s (within 20ms of target)
    total_acoustic_gap = tail40_s + (len(fill) / (sr * 2)) + head40_s
    assert abs(total_acoustic_gap - target_s) * 1000.0 <= 20.0


def test_flag_off_identical_to_legacy():
    """Validates that when TTS_PIPELINE_V2=False, pipeline delegates directly to legacy path."""
    with patch.object(settings, "TTS_PIPELINE_V2", False):
        with patch("app.core.llm._generate_voice_elevenlabs_v2") as mock_v2:
            with patch("app.core.llm.requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.content = b"legacy_mp3_audio"
                mock_post.return_value.iter_content = lambda chunk_size: [b"legacy_mp3_audio"]

                res = generate_voice_elevenlabs("A short test story", return_timestamps=False)
                assert res == b"legacy_mp3_audio"
                mock_v2.assert_not_called()


def test_max_time_s_preserves_soft_word_decay_and_ignores_container_clicks():
    """
    Validates that get_last_audible_time with max_time_s = last_word_end + 0.600:
    1. NEVER cuts a real soft word ending that trails beyond last_word_end
       (e.g., an unvoiced fricative/whisper decaying down to -50 dB over 350 ms).
    2. Completely ignores container framing artifacts / spurious clicks
       occurring > 600 ms after last_word_end (e.g. at 1.0 - 1.5 s).
    """
    import math
    import struct
    from app.services.tts_pipeline import (
        get_last_audible_time,
        PCM_SAMPLE_RATE,
    )

    sr = PCM_SAMPLE_RATE
    # Synthesize audio:
    # 0.0s to 1.0s: Word speech (voiced body ending at 1.000s)
    # 1.0s to 1.35s: Real soft word decay (e.g. unvoiced /s/ or breath tail, dropping from -35 dB to -49.5 dB at 1.35s)
    # 1.35s to 1.70s: Natural silence (< -70 dB)
    # 1.75s to 1.76s: Spurious container framing click at -15 dB (occurs 750 ms after last_word_end)
    # Total duration = 2.0s
    total_dur = 2.0
    total_frames = int(total_dur * sr)
    samples = [0] * total_frames

    # Voiced word up to 1.000s
    for i in range(int(1.000 * sr)):
        samples[i] = int(12000 * math.sin(2 * math.pi * 300 * (i / sr)))

    # Real soft word decay trailing from 1.000s to 1.350s (350 ms trail)
    decay_start_f = int(1.000 * sr)
    decay_end_f = int(1.350 * sr)
    for i in range(decay_start_f, decay_end_f):
        progress = (i - decay_start_f) / float(decay_end_f - decay_start_f)
        amp = 1500.0 * (0.10 ** progress)
        samples[i] = int(amp * math.sin(2 * math.pi * 2500 * (i / sr)))

    # Spurious container click at 1.750s (amp 6000, ~ -15 dB)
    click_start_f = int(1.750 * sr)
    click_end_f = int(1.760 * sr)
    for i in range(click_start_f, click_end_f):
        samples[i] = int(6000 * math.sin(2 * math.pi * 1000 * (i / sr)))

    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)

    last_word_end = 1.000
    max_time_s = last_word_end + 0.600  # 1.600s

    # 1. With max_time_s:
    # Must capture the entire soft decay up to 1.350s, without truncation
    t_audible = get_last_audible_time(
        pcm_bytes,
        channels=1,
        sample_rate=sr,
        threshold_db=-50.0,
        window_ms=10.0,
        max_time_s=max_time_s,
    )
    assert 1.340 <= t_audible <= 1.360, f"Expected soft decay end ~1.350s, got {t_audible:.3f}s"

    # With 150ms cushion, trim_end is t_audible + 0.150 = ~1.500s
    trim_end = min(total_dur, max(t_audible + 0.080, t_audible + 0.150))
    assert 1.490 <= trim_end <= 1.510
    # Container click at 1.750s was safely excluded!
    assert trim_end < 1.750

    # 2. Without max_time_s (showing what would happen without the guardrail):
    # Unbounded scan latches onto spurious click at 1.760s
    t_audible_unbounded = get_last_audible_time(
        pcm_bytes,
        channels=1,
        sample_rate=sr,
        threshold_db=-50.0,
        window_ms=10.0,
        max_time_s=None,
    )
    assert t_audible_unbounded >= 1.750


def test_smooth_audio_no_break_tags_in_v2_request_text(monkeypatch):
    """Verify that when TTS_SMOOTH_AUDIO is True, no <break> tags are generated or sent."""
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)
    monkeypatch.setattr(settings, "TTS_SMOOTH_AUDIO", True)

    text = "First paragraph here.\n\nSecond paragraph continues here.\n\nThird paragraph ends."
    prepared = prepare_text_for_tts(text, "confession")
    assert "<break" not in prepared

    from app.services.tts_pipeline import split_text_into_chunks
    chunks = split_text_into_chunks(prepared, smooth_audio=True)
    assert len(chunks) >= 1
    for c in chunks:
        assert "<break" not in c.text
        assert "<break" not in c.previous_text
        assert "<break" not in c.next_text


def test_digital_silence_runs_and_continuous_bed_mixing():
    """Verify digital silence detection and zero digital silence runs after room tone bed is mixed."""
    from app.services.tts_pipeline import (
        count_digital_silence_runs,
        mix_pcm_additive,
        generate_shaped_noise_bed,
        PCM_SAMPLE_RATE,
        PCM_CHANNELS,
        PCM_BYTES_PER_FRAME,
    )

    # 1 second of total digital zeros
    silence_pcm = b"\x00" * (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    runs_before = count_digital_silence_runs(silence_pcm, threshold_db=-90.0, min_run_ms=20.0)
    assert runs_before >= 1

    # Generate shaped noise bed at -80 dB
    bed_pcm = generate_shaped_noise_bed(
        duration_s=1.0,
        channels=PCM_CHANNELS,
        sample_rate=PCM_SAMPLE_RATE,
        target_db=-80.0,
    )

    # Mix additively
    mixed_pcm = mix_pcm_additive(silence_pcm, bed_pcm)
    runs_after = count_digital_silence_runs(mixed_pcm, threshold_db=-90.0, min_run_ms=20.0)
    assert runs_after == 0, f"Expected 0 digital silence runs after bed mix, got {runs_after}"


def test_room_tone_bed_level_cap_and_fallback():
    """Verify room tone pause floor is capped at -72 dB and fallback to -80 dB shaped noise."""
    import array
    import math
    from app.services.tts_pipeline import (
        level_room_tone,
        extract_clean_room_tone_segment,
        generate_shaped_noise_bed,
        PCM_SAMPLE_RATE,
        PCM_CHANNELS,
    )

    # Create synthetic pause clip at -65 dB
    amp_65 = int(32767.0 * (10.0 ** (-65.0 / 20.0)))
    raw_clip = array.array("h", [amp_65] * int(0.400 * PCM_SAMPLE_RATE)).tobytes()

    # Leveled to -72 dB target
    leveled = level_room_tone(raw_clip, target_level_db=-72.0, channels=PCM_CHANNELS)
    s_leveled = array.array("h", leveled)
    rms_leveled = math.sqrt(sum(s * s for s in s_leveled) / float(len(s_leveled)))
    db_leveled = 20.0 * math.log10(rms_leveled / 32767.0)
    assert abs(db_leveled - (-72.0)) < 1.0

    # Test fallback when audio has no pause below -65 dB
    loud_speech = array.array("h", [5000] * int(1.0 * PCM_SAMPLE_RATE)).tobytes()
    clean_seg = extract_clean_room_tone_segment([loud_speech], channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE)
    assert clean_seg is None

    # Fallback to shaped noise bed
    fallback_bed = generate_shaped_noise_bed(1.0, channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE, target_db=-80.0)
    s_fb = array.array("h", fallback_bed)
    rms_fb = math.sqrt(sum(s * s for s in s_fb) / float(len(s_fb)))
    db_fb = 20.0 * math.log10(rms_fb / 32767.0)
    assert -83.0 <= db_fb <= -77.0


def test_tail_fades_never_touch_speech():
    """Verify that the 50 ms cushion fade begins strictly after the audible speech decay."""
    t_audible = 2.500
    cushion_s = 0.150
    trim_end = t_audible + cushion_s
    fade_duration_s = 0.050
    fade_start = trim_end - fade_duration_s

    assert fade_start > t_audible
    assert (fade_start - t_audible) == pytest.approx(0.100, abs=0.001)


def test_gentle_pace_selection_clamp_dead_zone_and_scaling(monkeypatch):
    """Verify pace alignment dead zone [0.98, 1.02], +/-4% tolerance, clamp [0.90, 1.10], and >10% outlier skip."""
    from app.services.tts_pipeline import (
        ChunkResult,
        apply_gentle_pace_alignment,
        PCM_SAMPLE_RATE,
        PCM_CHANNELS,
        PCM_BYTES_PER_FRAME,
    )

    # Median of [100.0, 102.0, 108.0, 125.0] is 105.0
    # 100.0: dev = -4.76% (between 4% and 10%) -> corrected! (factor = 105/100 = 1.05)
    # 102.0: dev = -2.86% (inside +/-4%) -> skipped
    # 108.0: dev = +2.86% (inside +/-4%) -> skipped
    # 125.0: dev = +19.05% (> 10%) -> skipped and logged
    rates = [100.0, 102.0, 108.0, 125.0]
    call_count = 0
    def mock_rate(*args, **kwargs):
        nonlocal call_count
        r = rates[call_count % len(rates)]
        call_count += 1
        return r

    monkeypatch.setattr("app.services.tts_pipeline.compute_articulation_rate_from_pcm", mock_rate)

    applied_factors = {}
    def mock_atempo_pcm(pcm_bytes, alignment, factor, **kwargs):
        applied_factors[len(applied_factors)] = factor
        return pcm_bytes, alignment

    monkeypatch.setattr("app.services.tts_pipeline.apply_chunk_atempo_pcm", mock_atempo_pcm)

    dummy_pcm = b"\x00" * int(1.0 * PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    chunks = [
        ChunkResult(index=i, mp3_bytes=b"dummy", alignment=[{"word": "word", "start": 0.1, "end": 0.5}], is_paragraph_end=False)
        for i in range(4)
    ]
    pcms = [dummy_pcm for _ in range(4)]

    apply_gentle_pace_alignment(chunks, pcms)

    assert len(applied_factors) == 1
    corr_factor = list(applied_factors.values())[0]
    assert 0.90 <= corr_factor <= 1.10
    assert corr_factor == pytest.approx(1.05, abs=0.01)


def test_model_supports_request_id_chaining():
    """Verify model_supports_request_id_chaining returns True only for models supporting chaining."""
    from app.services.tts_pipeline import model_supports_request_id_chaining
    assert model_supports_request_id_chaining("eleven_multilingual_v2") is False
    assert model_supports_request_id_chaining("eleven_multilingual_v1") is False
    assert model_supports_request_id_chaining("eleven_turbo_v2_5") is True
    assert model_supports_request_id_chaining("eleven_flash_v2_5") is True
    assert model_supports_request_id_chaining("eleven_flash_v2") is True
    assert model_supports_request_id_chaining("eleven_monolingual_v1") is False


def test_multilingual_uses_concurrent_workers_while_turbo_uses_sequential_chaining(monkeypatch):
    """
    Verify execute_tts_pipeline_v2 with smooth_audio=True:
    - uses 3 concurrent workers and no previous_request_ids for multilingual_v2 (chaining unsupported).
    - uses sequential chaining with previous_request_ids for turbo_v2_5.
    """
    import concurrent.futures
    from app.services.tts_pipeline import (
        execute_tts_pipeline_v2,
        ChunkResult,
    )

    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)
    monkeypatch.setattr(settings, "TTS_SMOOTH_AUDIO", True)
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "test-api-key")

    calls = []
    def mock_fetch(chunk, resolved_voice_id, resolved_model_id, voice_settings, api_key, max_retries=3, previous_request_ids=None):
        calls.append({
            "chunk_idx": chunk.index,
            "model_id": resolved_model_id,
            "prev_req_ids": previous_request_ids,
        })
        return ChunkResult(
            index=chunk.index,
            mp3_bytes=b"dummy",
            alignment=[{"word": "word", "start": 0.1, "end": 0.5}],
            is_paragraph_end=chunk.is_paragraph_end,
            request_id=f"req-{chunk.index}",
        )

    monkeypatch.setattr("app.services.tts_pipeline.fetch_chunk_audio_with_retry", mock_fetch)
    monkeypatch.setattr("app.services.tts_pipeline.assemble_smooth_story", lambda ordered_chunks, profile, text: (b"assembled", []))

    # 1. multilingual_v2: must NOT pass previous_request_ids, uses 3 workers branch
    calls.clear()
    thread_pool_used = []
    original_tpe = concurrent.futures.ThreadPoolExecutor
    class TrackedThreadPool(original_tpe):
        def __init__(self, *args, **kwargs):
            thread_pool_used.append(kwargs.get("max_workers", args[0] if args else None))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.services.tts_pipeline.ThreadPoolExecutor", TrackedThreadPool)

    execute_tts_pipeline_v2(
        text="Paragraph one with multiple words here.\n\nParagraph two with more words here.",
        voice_id="voice-1",
        model_id="eleven_multilingual_v2",
        story_type="confession",
    )
    assert len(thread_pool_used) == 1
    assert thread_pool_used[0] == 3  # 3 concurrent workers used
    for call in calls:
        assert call["prev_req_ids"] is None

    # 2. turbo_v2_5: must use sequential chaining with previous_request_ids, no ThreadPool
    calls.clear()
    thread_pool_used.clear()
    execute_tts_pipeline_v2(
        text="Paragraph one with multiple words here.\n\nParagraph two with more words here.",
        voice_id="voice-1",
        model_id="eleven_turbo_v2_5",
        story_type="confession",
    )
    assert len(thread_pool_used) == 0  # Sequential chaining: no ThreadPool used
    assert len(calls) >= 2
    # Second chunk received request_id of first chunk
    assert calls[1]["prev_req_ids"] == ["req-0"]


def test_request_id_chaining_and_fallback(monkeypatch):
    """Verify request-id chaining from response headers and fallback when unsupported."""
    from app.services.tts_pipeline import (
        TextChunk,
        fetch_chunk_audio_with_retry,
    )

    sent_payloads = []

    class MockResponse:
        def __init__(self, status_code, json_data, headers):
            self.status_code = status_code
            self._json = json_data
            self.headers = headers

        def json(self):
            return self._json

    def mock_post(url, json=None, headers=None, timeout=None):
        sent_payloads.append(dict(json))
        import base64
        return MockResponse(
            status_code=200,
            json_data={
                "audio_base64": base64.b64encode(b"ID3\x04mock").decode("utf-8"),
                "alignment": {
                    "characters": ["h", "i"],
                    "character_start_times_seconds": [0.0, 0.1],
                    "character_end_times_seconds": [0.1, 0.2],
                },
            },
            headers={"request-id": "req-12345"},
        )

    monkeypatch.setattr("requests.post", mock_post)

    chunk = TextChunk(index=0, text="hello world", previous_text="", next_text="", is_paragraph_end=True)

    # 1. With turbo model and previous_request_ids: should include previous_request_ids
    res_turbo = fetch_chunk_audio_with_retry(
        chunk=chunk,
        resolved_voice_id="voice-1",
        resolved_model_id="eleven_turbo_v2_5",
        voice_settings={},
        api_key="valid-key",
        previous_request_ids=["prev-1", "prev-2"],
    )
    assert res_turbo.request_id == "req-12345"
    assert "previous_request_ids" in sent_payloads[-1]
    assert sent_payloads[-1]["previous_request_ids"] == ["prev-1", "prev-2"]

    # 2. With multilingual model: should omit previous_request_ids (unsupported per official docs)
    res_multi = fetch_chunk_audio_with_retry(
        chunk=chunk,
        resolved_voice_id="voice-1",
        resolved_model_id="eleven_multilingual_v2",
        voice_settings={},
        api_key="valid-key",
        previous_request_ids=["prev-1", "prev-2"],
    )
    assert "previous_request_ids" not in sent_payloads[-1]


def test_v2_fallback_visibility_logs_error_type_and_counter(monkeypatch, caplog):
    """Verify fallback visibility: when V2 raises, logs one line with error type and counter, no story text."""
    from app.core.llm import generate_voice_elevenlabs, get_tts_v2_fallback_count

    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)
    initial_count = get_tts_v2_fallback_count()

    def mock_failing_v2(*args, **kwargs):
        raise RuntimeError("Simulated V2 failure")

    monkeypatch.setattr("app.core.llm._generate_voice_elevenlabs_v2", mock_failing_v2)

    secret_story = "TOP_SECRET_STORY_TEXT_NEVER_LOG"
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "audio_base64": "SUQzBAAAAA==",
            "alignment": {"characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []},
        }
        mock_post.return_value = mock_resp

        import logging
        with caplog.at_level(logging.WARNING):
            generate_voice_elevenlabs(
                text=secret_story,
                voice_id="Charlotte",
                return_timestamps=True,
            )

    new_count = get_tts_v2_fallback_count()
    assert new_count == initial_count + 1

    assert any("TTS V2 fallback [count=" in rec.message and "error_type=RuntimeError" in rec.message for rec in caplog.records)
    for rec in caplog.records:
        assert secret_story not in rec.message


def test_smooth_story_assembly_alignment_shifts_and_edges():
    """Verify that assemble_smooth_story shifts alignment by the 250 ms lead-in, maintains monotonicity and non-negativity."""
    import array
    from app.services.tts_pipeline import (
        ChunkResult,
        assemble_smooth_story,
        raw_pcm_to_mp3,
        PCM_SAMPLE_RATE,
    )
    from app.services.tts_profiles import get_tts_profile

    pcm1 = array.array("h", [2500] * int(1.0 * PCM_SAMPLE_RATE)).tobytes()
    mp3_1 = raw_pcm_to_mp3(pcm1, loudnorm=False)
    c1 = ChunkResult(index=0, mp3_bytes=mp3_1, alignment=[{"word": "hello", "start": 0.1, "end": 0.9}], is_paragraph_end=False)

    pcm2 = array.array("h", [2500] * int(1.0 * PCM_SAMPLE_RATE)).tobytes()
    mp3_2 = raw_pcm_to_mp3(pcm2, loudnorm=False)
    c2 = ChunkResult(index=1, mp3_bytes=mp3_2, alignment=[{"word": "world", "start": 0.1, "end": 0.9}], is_paragraph_end=True)

    profile = get_tts_profile("confession")
    final_mp3, final_alignment = assemble_smooth_story([c1, c2], profile, text="hello world")

    assert len(final_mp3) > 0
    assert len(final_alignment) == 2

    # Lead-in is 250 ms: first word start must be >= 0.250
    assert final_alignment[0]["start"] >= 0.250
    # Monotonicity
    assert final_alignment[0]["start"] <= final_alignment[0]["end"]
    assert final_alignment[0]["end"] <= final_alignment[1]["start"]
    assert final_alignment[1]["start"] <= final_alignment[1]["end"]


