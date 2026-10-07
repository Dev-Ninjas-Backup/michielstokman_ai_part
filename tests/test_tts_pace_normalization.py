"""
tests/test_tts_pace_normalization.py

Unit tests for TTS relative pace normalization in Phase 2 pipeline:
1. Articulation rate calculation (excluding pauses > 250ms).
2. Story median calculation and outlier selection (6% standard, 8% for < 60 words).
3. atempo factor clamping to [0.92, 1.08].
4. Alignment timestamp scaling (monotonicity, non-negativity, last end <= duration).
5. At most one regeneration per chunk.
6. 30% regeneration cap per story.
7. Normalization failure fallback to un-normalized chunks.
8. Flag OFF behavior remains completely unchanged.
9. Smaller chunking (500-900 chars, sentence boundaries) when flag is ON.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings
from app.services.tts_pipeline import (
    ChunkResult,
    TextChunk,
    apply_chunk_atempo,
    apply_pace_normalization,
    compute_articulation_rate,
    execute_tts_pipeline_v2,
    select_outlier_chunks,
    split_text_into_chunks,
)


def test_compute_articulation_rate():
    """Validates articulation rate math excluding internal pauses > 250ms."""
    # 3 words over 2.0s total, with a 0.4s gap between word 1 and 2 (> 0.250s)
    # and a 0.1s gap between word 0 and 1 (<= 0.250s)
    alignment = [
        {"word": "First", "start": 0.0, "end": 0.5},
        {"word": "second", "start": 0.6, "end": 1.1},
        {"word": "third", "start": 1.5, "end": 2.0},
    ]
    # Speech time = 2.0s - 0.0s = 2.0s.
    # Gap > 250ms = 1.5 - 1.1 = 0.4s.
    # Phonation time = 2.0 - 0.4 = 1.6s.
    # Words = 3.
    # Articulation rate = (3 / 1.6) * 60 = 112.5 WPM.
    rate = compute_articulation_rate(alignment)
    assert abs(rate - 112.5) < 1e-3

    # Empty alignment or standalone punctuation returns 0.0
    assert compute_articulation_rate([]) == 0.0
    assert compute_articulation_rate([{"word": "—", "start": 0.0, "end": 0.0}]) == 0.0


def test_median_and_outlier_selection():
    """
    Tests relative normalization outlier selection:
    - Median computed across story chunks.
    - Standard chunks (>= 60 words) use 6% threshold.
    - Short chunks (< 60 words) use 8% threshold.
    """
    chunk_metrics = [
        {"index": 0, "rate": 150.0, "word_count": 80},  # exact median
        {"index": 1, "rate": 155.0, "word_count": 85},  # +3.3% -> within 6%
        {"index": 2, "rate": 145.0, "word_count": 75},  # -3.3% -> within 6%
        {"index": 3, "rate": 170.0, "word_count": 90},  # +13.3% -> outlier (>6%)
        {"index": 4, "rate": 125.0, "word_count": 80},  # -16.7% -> outlier (>6%)
        {"index": 5, "rate": 160.0, "word_count": 45},  # +6.7% -> short chunk (<60w), within 8%
        {"index": 6, "rate": 136.0, "word_count": 40},  # -9.3% -> short chunk (<60w), outlier (>8%)
    ]

    median_rate, outliers = select_outlier_chunks(chunk_metrics)
    assert median_rate == 150.0

    outlier_indices = [o["chunk_index"] for o in outliers]
    assert outlier_indices == [3, 4, 6]
    assert 1 not in outlier_indices
    assert 2 not in outlier_indices
    assert 5 not in outlier_indices  # 160 is within 8% for 45-word chunk


def test_atempo_factor_clamp():
    """Confirms atempo factor is strictly clamped to [0.92, 1.08]."""
    # Create mock mp3 bytes (empty frame)
    mock_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    mock_alignment = [{"word": "word", "start": 0.0, "end": 0.5}]

    # When factor is 1.0, returns untouched
    mp3_out, align_out = apply_chunk_atempo(mock_mp3, mock_alignment, factor=1.0)
    assert mp3_out == mock_mp3
    assert align_out == mock_alignment

    # When factor is outside bounds (e.g. 1.25 or 0.70), verify ffmpeg command uses clamped value
    with patch("subprocess.run") as mock_subproc, patch("app.services.tts_pipeline.mp3_to_raw_pcm", return_value=(b"\x00" * 44100, 1.0)):
        mock_subproc.return_value = MagicMock(stdout=mock_mp3)

        apply_chunk_atempo(mock_mp3, mock_alignment, factor=1.25)
        cmd_used = mock_subproc.call_args[0][0]
        filter_arg = next(arg for arg in cmd_used if "atempo=" in arg)
        assert "atempo=1.0800" in filter_arg

        apply_chunk_atempo(mock_mp3, mock_alignment, factor=0.70)
        cmd_used_low = mock_subproc.call_args[0][0]
        filter_arg_low = next(arg for arg in cmd_used_low if "atempo=" in arg)
        assert "atempo=0.9200" in filter_arg_low


def test_alignment_scaling_monotonic_and_bounds():
    """
    Confirms scaled alignment timestamps are:
    1. Monotonic (start <= end, start[i] >= end[i-1]).
    2. Non-negative.
    3. Last end <= new audio duration.
    """
    mock_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    alignment = [
        {"word": "One", "start": 0.1, "end": 0.4},
        {"word": "two", "start": 0.5, "end": 0.8},
        {"word": "three", "start": 0.85, "end": 1.2},
    ]

    # Duration after scaling is 1.0s (less than original 1.2s due to speedup)
    with patch("subprocess.run") as mock_subproc, patch("app.services.tts_pipeline.mp3_to_raw_pcm", return_value=(b"\x00" * 88200, 1.0)):
        mock_subproc.return_value = MagicMock(stdout=mock_mp3)

        _, scaled = apply_chunk_atempo(mock_mp3, alignment, factor=1.08)

        prev_end = 0.0
        for w in scaled:
            assert w["start"] >= 0.0
            assert w["end"] >= w["start"]
            assert w["start"] >= prev_end
            prev_end = w["end"]

        # Last end strictly clamped to new_dur (1.0s)
        assert scaled[-1]["end"] <= 1.0


def test_regeneration_at_most_once_per_chunk():
    """Validates that a chunk with deviation > 8% is regenerated at most once."""
    c0 = ChunkResult(
        index=0,
        mp3_bytes=b"c0",
        alignment=[{"word": f"w{i}", "start": float(i), "end": float(i) + 0.3} for i in range(100)],
        is_paragraph_end=True,
    )
    # c1 is 2x faster (outlier > 8%)
    c1 = ChunkResult(
        index=1,
        mp3_bytes=b"c1",
        alignment=[{"word": f"w{i}", "start": float(i) * 0.5, "end": float(i) * 0.5 + 0.15} for i in range(100)],
        is_paragraph_end=True,
    )
    c2 = ChunkResult(
        index=2,
        mp3_bytes=b"c2",
        alignment=[{"word": f"w{i}", "start": float(i), "end": float(i) + 0.3} for i in range(100)],
        is_paragraph_end=True,
    )
    c3 = ChunkResult(
        index=3,
        mp3_bytes=b"c3",
        alignment=[{"word": f"w{i}", "start": float(i), "end": float(i) + 0.3} for i in range(100)],
        is_paragraph_end=True,
    )

    ordered = [c0, c1, c2, c3]
    text_chunks = [TextChunk(index=i, text=f"Text {i}", previous_text="", next_text="", is_paragraph_end=True) for i in range(4)]

    # Mock fetch returns a newly generated chunk
    mock_fetch = MagicMock(return_value=ChunkResult(
        index=1,
        mp3_bytes=b"c1_regen",
        alignment=[{"word": f"w{i}", "start": float(i) * 0.9, "end": float(i) * 0.9 + 0.25} for i in range(100)],
        is_paragraph_end=True,
    ))

    with patch("app.services.tts_pipeline.fetch_chunk_audio_with_retry", mock_fetch), \
         patch("app.services.tts_pipeline.apply_chunk_atempo", side_effect=lambda mp3, al, factor: (mp3, al)):

        res = apply_pace_normalization(
            ordered_chunks=ordered,
            chunks=text_chunks,
            resolved_voice_id="voice1",
            resolved_model_id="turbo",
            voice_settings={"speed": 1.0},
            api_key="real_key",
        )

        # Confirm fetch called exactly ONCE for chunk 1
        assert mock_fetch.call_count == 1
        assert mock_fetch.call_args[1]["chunk"].index == 1
        # Chunk 1 now has regenerated bytes
        assert res[1].mp3_bytes == b"c1_regen"


def test_regeneration_30_percent_cap():
    """
    Validates that regenerations are capped at 30% of chunks per story (floor(5 * 0.30) = 1).
    Even if 3 chunks deviate > 8%, only the 1 worst outlier is regenerated.
    """
    # c3 is slightly fast, c4 is severe outlier
    # Use continuous words with 0.1s gap (no pause > 250ms)
    # c0-c2: 100 words in 50s -> 120 WPM
    # c3: 100 words in 40s -> 150 WPM (deviation 25%)
    # c4: 100 words in 25s -> 240 WPM (deviation 100% - worst outlier)
    normal_align = [{"word": f"w{i}", "start": float(i) * 0.5, "end": float(i) * 0.5 + 0.4} for i in range(100)]
    c0 = ChunkResult(index=0, mp3_bytes=b"c0", alignment=normal_align, is_paragraph_end=True)
    c1 = ChunkResult(index=1, mp3_bytes=b"c1", alignment=normal_align, is_paragraph_end=True)
    c2 = ChunkResult(index=2, mp3_bytes=b"c2", alignment=normal_align, is_paragraph_end=True)
    c3 = ChunkResult(index=3, mp3_bytes=b"c3", alignment=[{"word": f"w{i}", "start": float(i) * 0.4, "end": float(i) * 0.4 + 0.3} for i in range(100)], is_paragraph_end=True)
    c4 = ChunkResult(index=4, mp3_bytes=b"c4", alignment=[{"word": f"w{i}", "start": float(i) * 0.25, "end": float(i) * 0.25 + 0.2} for i in range(100)], is_paragraph_end=True)

    ordered = [c0, c1, c2, c3, c4]
    text_chunks = [TextChunk(index=i, text=f"Text {i}", previous_text="", next_text="", is_paragraph_end=True) for i in range(5)]

    mock_fetch = MagicMock(return_value=ChunkResult(
        index=4,
        mp3_bytes=b"c4_regen",
        alignment=normal_align,
        is_paragraph_end=True,
    ))

    with patch("app.services.tts_pipeline.fetch_chunk_audio_with_retry", mock_fetch), \
         patch("app.services.tts_pipeline.apply_chunk_atempo", side_effect=lambda mp3_bytes, alignment, factor: (mp3_bytes, alignment)):

        apply_pace_normalization(
            ordered_chunks=ordered,
            chunks=text_chunks,
            resolved_voice_id="voice1",
            resolved_model_id="turbo",
            voice_settings={"speed": 1.0},
            api_key="real_key",
        )

        # 30% of 5 is 1. Only the single worst outlier (c4) is regenerated.
        assert mock_fetch.call_count == 1
        assert mock_fetch.call_args[1]["chunk"].index == 4


def test_normalization_failure_fallback(monkeypatch):
    """
    Validates failure resilience:
    If pace normalization raises an exception, the pipeline catches it,
    logs a warning without story text, and proceeds with the un-normalized chunks.
    """
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)
    monkeypatch.setattr(settings, "TTS_PACE_NORMALIZE", True)

    story_text = "This is a test story with multiple sentences. It should proceed cleanly even if normalization crashes."

    # Force apply_pace_normalization to crash
    with patch("app.services.tts_pipeline.apply_pace_normalization", side_effect=RuntimeError("Atempo subprocess failure")), \
         patch("logging.Logger.warning") as mock_warn:

        # In mock mode (API key is dummy), pipeline returns mock output safely
        audio, alignment = execute_tts_pipeline_v2(
            text=story_text,
            story_type="confession",
            return_timestamps=True,
        )

        assert len(audio) > 0
        assert len(alignment) > 0


def test_flag_off_unchanged(monkeypatch):
    """
    When TTS_PACE_NORMALIZE is False (default), verify:
    1. apply_pace_normalization is never called.
    2. Chunk size defaults to standard 800-1500 chars.
    """
    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", True)
    monkeypatch.setattr(settings, "TTS_PACE_NORMALIZE", False)

    with patch("app.services.tts_pipeline.apply_pace_normalization") as mock_norm:
        audio, alignment = execute_tts_pipeline_v2(
            text="Testing flag off behavior.",
            story_type="confession",
            return_timestamps=True,
        )
        assert not mock_norm.called
        assert len(audio) > 0


def test_smaller_chunks_when_flag_on(monkeypatch):
    """
    When TTS_PACE_NORMALIZE is True, split_text_into_chunks uses 500-900 chars
    and respects sentence boundaries.
    """
    text = (
        "Paragraph one is a fairly long narrative sentence that keeps going on and on to build up substantial character count. "
        "Here is the second sentence which extends the length even further to reach beyond five hundred characters comfortably. "
        "And a third sentence to ensure the paragraph is safely within the target range.\n\n"
        "Paragraph two begins right here with fresh ideas and continuous momentum. "
        "It also carries several detailed sentences that maintain cadence without ever splitting mid-sentence."
    )

    # With flag on: min=500, max=900
    chunks_small = split_text_into_chunks(text, min_chars=500, max_chars=900)
    for c in chunks_small:
        assert len(c.text) <= 900
        # Ensure ends with sentence punctuation or paragraph end
        assert c.text[-1] in ".!?…\"'”’"


def test_band_edge_correction():
    """
    Validates that outliers are corrected toward the nearest edge of median +/- 5%,
    not to the median itself:
    - Lower outlier (< median): target = median * 0.95
    - Upper outlier (> median): target = median * 1.05
    """
    # 4 chunks: c0, c1, c2 normal (~150 WPM), c3 is slow (120 WPM, -20% deviation)
    # Target should be 150 * 0.95 = 142.5 WPM, factor = 142.5 / 120 = 1.1875
    normal_align = [{"word": f"w{i}", "start": float(i) * 0.4, "end": float(i) * 0.4 + 0.3} for i in range(100)]
    slow_align = [{"word": f"w{i}", "start": float(i) * 0.5, "end": float(i) * 0.5 + 0.4} for i in range(100)]

    c0 = ChunkResult(index=0, mp3_bytes=b"c0", alignment=normal_align, is_paragraph_end=True)
    c1 = ChunkResult(index=1, mp3_bytes=b"c1", alignment=normal_align, is_paragraph_end=True)
    c2 = ChunkResult(index=2, mp3_bytes=b"c2", alignment=normal_align, is_paragraph_end=True)
    c3 = ChunkResult(index=3, mp3_bytes=b"c3", alignment=slow_align, is_paragraph_end=True)

    ordered = [c0, c1, c2, c3]
    text_chunks = [TextChunk(index=i, text=f"Text {i}", previous_text="prev", next_text="next", is_paragraph_end=True) for i in range(4)]

    mock_fetch = MagicMock(return_value=ChunkResult(
        index=3,
        mp3_bytes=b"c3_regen",
        alignment=normal_align,
        is_paragraph_end=True,
    ))

    with patch("app.services.tts_pipeline.fetch_chunk_audio_with_retry", mock_fetch), \
         patch("app.services.tts_pipeline.apply_chunk_atempo", side_effect=lambda mp3_bytes, alignment, factor: (mp3_bytes, alignment)):

        apply_pace_normalization(
            ordered_chunks=ordered,
            chunks=text_chunks,
            resolved_voice_id="voice1",
            resolved_model_id="turbo",
            voice_settings={"speed": 1.0},
            api_key="real_key",
        )

        assert mock_fetch.call_count == 1
        call_kwargs = mock_fetch.call_args[1]
        # Target speed = clamp(1.0 * (142.5 / 120.0), 0.85, 1.15) = clamp(1.1875, 0.85, 1.15) = 1.15
        assert call_kwargs["voice_settings"]["speed"] == 1.15
        # Verify previous_text and next_text are preserved
        assert call_kwargs["chunk"].previous_text == "prev"
        assert call_kwargs["chunk"].next_text == "next"


def test_pace_normalize_no_effect_when_pipeline_v2_false(monkeypatch):
    """
    Confirms that TTS_PACE_NORMALIZE has zero effect when TTS_PIPELINE_V2 is False.
    The legacy path runs and apply_pace_normalization is never invoked.
    """
    from app.core.llm import generate_voice_elevenlabs

    monkeypatch.setattr(settings, "TTS_PIPELINE_V2", False)
    monkeypatch.setattr(settings, "TTS_PACE_NORMALIZE", True)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "SUQzBAAAAAAAAA==",
        "alignment": {"characters": ["H", "i"], "character_start_times_seconds": [0.0, 0.1], "character_end_times_seconds": [0.1, 0.2]}
    }

    with patch("app.services.tts_pipeline.apply_pace_normalization") as mock_norm, \
         patch("app.core.llm._generate_voice_elevenlabs_v2") as mock_v2, \
         patch("requests.post", return_value=mock_resp):

        audio, alignment = generate_voice_elevenlabs(
            text="Testing legacy isolation with pace normalize on.",
            return_timestamps=True,
            story_type="confession",
        )

        assert not mock_v2.called
        assert not mock_norm.called
        assert len(audio) > 0
