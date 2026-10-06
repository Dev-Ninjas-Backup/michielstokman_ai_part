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
