"""
app/services/tts_pipeline.py

Phase 2 TTS Pipeline for Transform to Liberation:
- Intelligent paragraph and sentence chunking with neighbor context (~500 chars).
- Concurrency bounded to 3 in-flight requests via ThreadPoolExecutor.
- Exponential backoff retry on HTTP 429 and 5xx.
- Alignment-based edge trimming:
    trim_start = max(0, first_word_start - 0.030)
    trim_end = min(duration, last_word_end + 0.130)
- Natural seam pauses (profile paragraph break at paragraph ends, profile pause_ms at sentence splits).
- Single-pass Loudnorm normalization (I=-16, TP=-1.5, LRA=11) to prevent volume pumping.
- Monotonic, non-negative, sample-accurate alignment timestamp shifting.
- Zero external Python audio dependencies (uses standard library + system ffmpeg via subprocess).
"""

import array
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Optional, Union

import requests

from app.core.config import settings
from app.core.llm import ELEVENLABS_VOICES
from app.schemas.schema_ai import StoryType
from app.services.tts_profiles import TTSProfile, get_tts_profile, prepare_text_for_tts

logger = logging.getLogger(__name__)

# Sample rate and format for raw PCM handling
PCM_SAMPLE_RATE = 44100
PCM_CHANNELS = 2
PCM_BYTES_PER_SAMPLE = 2  # 16-bit
PCM_BYTES_PER_FRAME = PCM_CHANNELS * PCM_BYTES_PER_SAMPLE  # 4 bytes


@dataclass
class TextChunk:
    index: int
    text: str
    previous_text: str
    next_text: str
    is_paragraph_end: bool


@dataclass
class ChunkResult:
    index: int
    mp3_bytes: bytes
    alignment: list[dict]
    is_paragraph_end: bool


def get_ffmpeg_bin() -> str:
    """Locates the ffmpeg executable from PATH or scratch/bin."""
    bin_path = shutil.which("ffmpeg")
    if bin_path:
        return bin_path
    scratch_bin = os.path.abspath(os.path.join("scratch", "bin", "ffmpeg.exe"))
    if os.path.isfile(scratch_bin):
        return scratch_bin
    raise RuntimeError("ffmpeg executable not found in PATH or scratch/bin")


def apply_pcm_fade(pcm_bytes: bytes, fade_ms: float = 10.0, sample_rate: int = PCM_SAMPLE_RATE) -> bytes:
    """
    Applies a 5-10 ms linear fade-in and fade-out to 16-bit stereo PCM frames.
    Ramps amplitudes to 0 at slice boundaries so that seam transitions are click-free.
    """
    fade_frames = int((fade_ms / 1000.0) * sample_rate)
    if fade_frames <= 0 or len(pcm_bytes) < fade_frames * PCM_BYTES_PER_FRAME:
        return pcm_bytes

    samples = array.array("h", pcm_bytes)
    total_frames = len(samples) // PCM_CHANNELS

    # Linear fade-in
    for i in range(min(fade_frames, total_frames)):
        factor = i / float(fade_frames)
        samples[2 * i] = int(samples[2 * i] * factor)
        samples[2 * i + 1] = int(samples[2 * i + 1] * factor)

    # Linear fade-out
    for i in range(min(fade_frames, total_frames)):
        factor = (fade_frames - 1 - i) / float(fade_frames)
        idx = total_frames - fade_frames + i
        if idx >= 0:
            samples[2 * idx] = int(samples[2 * idx] * factor)
            samples[2 * idx + 1] = int(samples[2 * idx + 1] * factor)

    return samples.tobytes()


def parse_alignment_to_whitespace_words(alignment: dict) -> list[dict]:
    """
    Parses character-level alignments into exactly one word per whitespace-delimited
    token of the display text, matching the frontend's display text tokenization 1-to-1.
    XML <break> tags are stripped from character stream before assembly.
    Punctuation at outer boundaries of tokens (quotes, commas, ellipsis, brackets)
    is stripped from the display label while preserving the exact token start/end times.
    """
    if not alignment:
        return []
    characters = alignment.get("characters", [])
    start_times = alignment.get("character_start_times_seconds", [])
    end_times = alignment.get("character_end_times_seconds", [])

    if not characters or not start_times or not end_times:
        return []

    # 1. Filter out XML tags (such as <break time="...s" />)
    filt_chars, filt_starts, filt_ends = [], [], []
    i = 0
    n = len(characters)
    while i < n:
        if characters[i] == "<" and "".join(characters[i:i+6]).lower() == "<break":
            while i < n and characters[i] != ">":
                i += 1
            if i < n:
                i += 1
            continue
        filt_chars.append(characters[i])
        filt_starts.append(start_times[i])
        filt_ends.append(end_times[i])
        i += 1

    # 2. Group characters into whitespace-delimited tokens
    words: list[dict] = []
    curr_chars: list[str] = []
    curr_start: Optional[float] = None
    last_end: Optional[float] = None

    for c, s, e in zip(filt_chars, filt_starts, filt_ends):
        if c in (" ", "\t", "\n", "\r"):
            if curr_chars:
                raw_w = "".join(curr_chars)
                clean_w = raw_w.strip('.,!?;:"“”‘’()[]{}*`_~')
                words.append({
                    "word": clean_w if clean_w else raw_w,
                    "start": curr_start,
                    "end": last_end,
                })
                curr_chars = []
                curr_start = None
        else:
            if curr_start is None:
                curr_start = s
            curr_chars.append(c)
            last_end = e

    if curr_chars:
        raw_w = "".join(curr_chars)
        clean_w = raw_w.strip('.,!?;:"“”‘’()[]{}*`_~')
        words.append({
            "word": clean_w if clean_w else raw_w,
            "start": curr_start,
            "end": last_end,
        })

    return words


def split_text_into_chunks(
    text: str,
    min_chars: int = 800,
    max_chars: int = 1500,
) -> list[TextChunk]:
    """
    Splits text into chunks of 800-1500 characters respecting paragraph and sentence boundaries.
    Never cuts mid-sentence. If text is <= max_chars, returns a single chunk.
    Strips trailing <break> tags from chunk text because seam silence replaces them.
    """
    if not text or not text.strip():
        return []

    stripped = text.strip()
    if len(stripped) <= max_chars:
        clean_one = re.sub(r'\s*<break\s+time="[^"]*"\s*/>\s*$', '', stripped).strip()
        return [TextChunk(
            index=0,
            text=clean_one,
            previous_text="",
            next_text="",
            is_paragraph_end=True,
        )]

    # 1. Split text into paragraphs (double newline)
    paragraphs = re.split(r'\n\s*\n+', stripped)

    # 2. Break any oversize paragraphs into sentences
    units: list[tuple[str, bool]] = []  # (text, is_paragraph_end)
    for p in paragraphs:
        # Strip standalone break tags between paragraphs
        p_strip_breaks = re.sub(r'^\s*<break\s+time="[^"]*"\s*/>\s*$', '', p).strip()
        if not p_strip_breaks:
            continue
        p_clean = p_strip_breaks
        if len(p_clean) <= max_chars:
            units.append((p_clean, True))
        else:
            # Split sentences ending in [.!?…] followed by space or newline
            sentence_splits = re.split(r'((?<=[.!?…])\s+)', p_clean)
            sentences = []
            curr_s = ""
            for part in sentence_splits:
                curr_s += part
                if re.search(r'[.!?…]\s*$', curr_s.strip()):
                    sentences.append(curr_s.strip())
                    curr_s = ""
            if curr_s.strip():
                sentences.append(curr_s.strip())

            # If any individual sentence exceeds max_chars, split on whitespace
            sub_sentences = []
            for s in sentences:
                if len(s) <= max_chars:
                    sub_sentences.append(s)
                else:
                    words = s.split()
                    chunk_words = []
                    chunk_len = 0
                    for w in words:
                        if chunk_words and (chunk_len + len(w) + 1 > max_chars):
                            sub_sentences.append(" ".join(chunk_words))
                            chunk_words = [w]
                            chunk_len = len(w)
                        else:
                            chunk_words.append(w)
                            chunk_len += len(w) + 1
                    if chunk_words:
                        sub_sentences.append(" ".join(chunk_words))

            for s_idx, s in enumerate(sub_sentences):
                is_p_end = (s_idx == len(sub_sentences) - 1)
                units.append((s, is_p_end))

    # 3. Assemble units into chunks of target size
    raw_chunks: list[tuple[str, bool]] = []
    current_units: list[str] = []
    current_len = 0
    current_is_p_end = False

    for unit_text, is_p_end in units:
        unit_len = len(unit_text)
        # Flush if adding unit exceeds max_chars and we have accumulated content
        if current_units and (current_len + unit_len + 2 > max_chars):
            sep = "\n\n" if current_is_p_end else " "
            chunk_str = sep.join(current_units)
            raw_chunks.append((chunk_str, current_is_p_end))
            current_units = [unit_text]
            current_len = unit_len
            current_is_p_end = is_p_end
        else:
            current_units.append(unit_text)
            current_len += unit_len + 2
            current_is_p_end = is_p_end

    if current_units:
        sep = "\n\n" if current_is_p_end else " "
        chunk_str = sep.join(current_units)
        raw_chunks.append((chunk_str, True))

    # 4. Attach previous_text and next_text (up to 500 chars)
    result: list[TextChunk] = []
    for idx, (c_text, is_p_end) in enumerate(raw_chunks):
        # Strip leading and trailing break tags to prevent double pauses at seams
        clean_text = re.sub(r'^\s*<break\s+time="[^"]*"\s*/>\s*', '', c_text.strip()).strip()
        clean_text = re.sub(r'\s*<break\s+time="[^"]*"\s*/>\s*$', '', clean_text).strip()

        # Previous 500 chars
        prev_parts = []
        for p_idx in range(idx - 1, -1, -1):
            prev_parts.insert(0, raw_chunks[p_idx][0])
            if sum(len(x) for x in prev_parts) >= 500:
                break
        prev_text = " ".join(prev_parts)[-500:] if prev_parts else ""

        # Next 500 chars
        next_parts = []
        for n_idx in range(idx + 1, len(raw_chunks)):
            next_parts.append(raw_chunks[n_idx][0])
            if sum(len(x) for x in next_parts) >= 500:
                break
        next_text = " ".join(next_parts)[:500] if next_parts else ""

        result.append(TextChunk(
            index=idx,
            text=clean_text,
            previous_text=prev_text,
            next_text=next_text,
            is_paragraph_end=is_p_end,
        ))

    return result


def fetch_chunk_audio_with_retry(
    chunk: TextChunk,
    resolved_voice_id: str,
    resolved_model_id: str,
    voice_settings: dict,
    api_key: str,
    max_retries: int = 3,
) -> ChunkResult:
    """
    Calls ElevenLabs /with-timestamps for one chunk with exponential backoff on 429/5xx.
    Passes previous_text and next_text for prosody continuity.
    Raises RuntimeError on repeated failure.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}/with-timestamps"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    data = {
        "text": chunk.text,
        "model_id": resolved_model_id,
        "voice_settings": voice_settings,
    }
    if chunk.previous_text:
        data["previous_text"] = chunk.previous_text
    if chunk.next_text:
        data["next_text"] = chunk.next_text

    backoff = 0.5
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=60)
            if resp.status_code == 200:
                res_json = resp.json()
                audio_bytes = base64.b64decode(res_json["audio_base64"])
                raw_alignment = res_json.get("alignment", {})

                # Filter XML break tags from character stream
                chars = raw_alignment.get("characters", [])
                starts = raw_alignment.get("character_start_times_seconds", [])
                ends = raw_alignment.get("character_end_times_seconds", [])

                filt_chars, filt_starts, filt_ends = [], [], []
                i = 0
                n = len(chars)
                while i < n:
                    if chars[i] == "<" and "".join(chars[i:i+6]).lower() == "<break":
                        while i < n and chars[i] != ">":
                            i += 1
                        if i < n:
                            i += 1
                        continue
                    filt_chars.append(chars[i])
                    filt_starts.append(starts[i])
                    filt_ends.append(ends[i])
                    i += 1

                clean_alignment = {
                    "characters": filt_chars,
                    "character_start_times_seconds": filt_starts,
                    "character_end_times_seconds": filt_ends,
                }
                words = parse_alignment_to_whitespace_words(clean_alignment)
                if not words:
                    raise ValueError(f"Chunk {chunk.index} returned empty word alignment")

                return ChunkResult(
                    index=chunk.index,
                    mp3_bytes=audio_bytes,
                    alignment=words,
                    is_paragraph_end=chunk.is_paragraph_end,
                )

            elif resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff)
                backoff *= 2.0
                last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")
            else:
                resp.raise_for_status()

        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2.0

    raise RuntimeError(f"Chunk {chunk.index} failed after {max_retries} attempts: {last_err}")


def mp3_to_raw_pcm(mp3_bytes: bytes) -> tuple[bytes, float]:
    """Decodes MP3 bytes to raw 16-bit 44.1kHz stereo PCM frames via ffmpeg."""
    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin, "-y", "-i", "pipe:0",
        "-f", "s16le", "-acodec", "pcm_s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS),
        "pipe:1"
    ]
    proc = subprocess.run(cmd, input=mp3_bytes, capture_output=True, check=True)
    pcm = proc.stdout
    dur = len(pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    return pcm, dur


def raw_pcm_to_mp3(pcm_bytes: bytes, loudnorm: bool = True) -> bytes:
    """
    Normalizes loudness and exports high-quality MP3 (44100 Hz, stereo, 192k).
    Uses two-pass loudnorm with linear=true so quiet meditation audio is never pumped.
    """
    ffmpeg_bin = get_ffmpeg_bin()
    if not loudnorm:
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS), "-i", "pipe:0",
            "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS),
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-f", "mp3", "pipe:1"
        ]
        proc = subprocess.run(cmd, input=pcm_bytes, capture_output=True, check=True)
        return proc.stdout

    # Pass 1: Measure loudness statistics
    pass1_cmd = [
        ffmpeg_bin, "-y",
        "-f", "s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS), "-i", "pipe:0",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    p1 = subprocess.run(pass1_cmd, input=pcm_bytes, capture_output=True)
    stderr1 = p1.stderr.decode("utf-8", errors="ignore")

    json_match = re.search(r"\{[\s\S]*\"input_i\"[\s\S]*\}", stderr1)
    if json_match:
        try:
            stats = json.loads(json_match.group(0))
            measured_i = stats.get("input_i", "-16")
            measured_tp = stats.get("input_tp", "-1.5")
            measured_lra = stats.get("input_lra", "11")
            measured_thresh = stats.get("input_thresh", "-26")
            target_offset = stats.get("target_offset", "0")

            filter_str = (
                f"loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"
                f":measured_I={measured_i}:measured_TP={measured_tp}"
                f":measured_LRA={measured_lra}:measured_thresh={measured_thresh}"
                f":offset={target_offset}"
            )
        except Exception:
            filter_str = "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"
    else:
        filter_str = "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"

    # Pass 2: Apply linear normalization and encode to MP3 with explicit 44100 Hz, stereo, 192k
    pass2_cmd = [
        ffmpeg_bin, "-y",
        "-f", "s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS), "-i", "pipe:0",
        "-af", filter_str,
        "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS),
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-f", "mp3", "pipe:1"
    ]
    p2 = subprocess.run(pass2_cmd, input=pcm_bytes, capture_output=True, check=True)
    return p2.stdout


def execute_tts_pipeline_v2(
    text: str,
    story_type: Optional[Union[str, StoryType]] = None,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
    style: Optional[float] = None,
    return_timestamps: bool = True,
) -> tuple[bytes, list[dict]]:
    """
    Executes the complete Phase 2 TTS pipeline:
    1. Prepares text with profile paragraph breaks.
    2. Chunks text (800-1500 chars) with context neighbors.
    3. Concurrently synthesizes chunks (max 3 workers) with retry backoff.
    4. Trims edge silence per chunk using word alignment:
         trim_start = max(0, first_word_start - 0.030)
         trim_end = min(duration, last_word_end + 0.130)
    5. Injects profile seam pauses (paragraph break at paragraph ends, pause_ms at sentence splits).
    6. Stitches PCM frames and shifts alignment words monotonically.
    7. Applies single-pass loudness normalization (I=-16, TP=-1.5, LRA=11) and exports one MP3.
    """
    profile: TTSProfile = get_tts_profile(story_type)
    prepared_text = prepare_text_for_tts(text, story_type)

    # Resolve voice and settings
    resolved_voice_id = ELEVENLABS_VOICES.get(voice_id, voice_id) or settings.ELEVENLABS_VOICE_ID
    resolved_model_id = model_id or settings.ELEVENLABS_MODEL_ID

    resolved_stability = stability if stability is not None else profile.stability
    resolved_similarity_boost = similarity_boost if similarity_boost is not None else profile.similarity_boost
    resolved_style = style if style is not None else profile.style
    resolved_speed = profile.speed

    # Member cloned (IVC) voice detection & guardrails
    is_stock = False
    if voice_id:
        v_str = str(voice_id).strip().lower()
        is_stock = (
            any(k.lower() == v_str for k in ELEVENLABS_VOICES.keys())
            or any(v.lower() == v_str for v in ELEVENLABS_VOICES.values())
            or (settings.ELEVENLABS_VOICE_ID and settings.ELEVENLABS_VOICE_ID.strip().lower() == v_str)
        )
    else:
        is_stock = True

    if voice_id and not is_stock:
        resolved_stability = max(0.50, resolved_stability)
        resolved_style = min(0.25, resolved_style)

    voice_settings = {
        "stability": resolved_stability,
        "similarity_boost": resolved_similarity_boost,
        "style": resolved_style,
        "use_speaker_boost": True,
        "speed": resolved_speed,
    }

    # Split text into chunks
    chunks = split_text_into_chunks(prepared_text, min_chars=800, max_chars=1500)
    if not chunks:
        raise ValueError("Prepared text resulted in 0 chunks")

    # Mock TTS path when API key is missing
    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        mock_audio = b"ID3\x04\x00\x00\x00\x00\x00\x00"
        words_list = prepared_text.split()
        mock_alignment = []
        for i, w in enumerate(words_list):
            if "<break" in w or "time=" in w:
                continue
            mock_alignment.append({
                "word": w.strip(".,!?\"()"),
                "start": round(i * 0.4, 2),
                "end": round(i * 0.4 + 0.3, 2),
            })
        return mock_audio, mock_alignment

    # Concurrently fetch chunks (max 3 workers)
    chunk_results: dict[int, ChunkResult] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(
                fetch_chunk_audio_with_retry,
                chunk=chunk,
                resolved_voice_id=resolved_voice_id,
                resolved_model_id=resolved_model_id,
                voice_settings=voice_settings,
                api_key=settings.ELEVENLABS_API_KEY,
            ): chunk.index
            for chunk in chunks
        }
        for future in as_completed(future_map):
            chunk_res = future.result()  # Raises if any chunk failed
            chunk_results[chunk_res.index] = chunk_res

    # Order chunks sequentially
    ordered_chunks = [chunk_results[i] for i in range(len(chunks))]

    # Decode, trim, stitch PCM and shift alignment
    final_pcm_parts: list[bytes] = []
    final_alignment: list[dict] = []
    running_offset = 0.0

    for idx, c_res in enumerate(ordered_chunks):
        pcm_bytes, dur = mp3_to_raw_pcm(c_res.mp3_bytes)
        words = c_res.alignment
        if not words:
            raise ValueError(f"Missing word alignment in chunk {idx}")

        # Alignment-based trimming
        first_word_start = words[0]["start"]
        last_word_end = words[-1]["end"]

        trim_start = max(0.0, first_word_start - 0.030)
        trim_end = min(dur, last_word_end + 0.130)

        # Slice PCM frames
        start_frame = int(trim_start * PCM_SAMPLE_RATE)
        end_frame = int(trim_end * PCM_SAMPLE_RATE)
        sliced_pcm = pcm_bytes[start_frame * PCM_BYTES_PER_FRAME : end_frame * PCM_BYTES_PER_FRAME]
        trimmed_dur = len(sliced_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)

        # Shift word alignment
        for w in words:
            shifted_start = running_offset + (w["start"] - trim_start)
            shifted_end = running_offset + (w["end"] - trim_start)
            final_alignment.append({
                "word": w["word"],
                "start": max(0.0, round(shifted_start, 3)),
                "end": max(0.0, round(shifted_end, 3)),
            })

        # Apply 10 ms linear micro-fade to prevent edge clicks and pops at slice boundaries
        faded_pcm = apply_pcm_fade(sliced_pcm, fade_ms=10.0, sample_rate=PCM_SAMPLE_RATE)
        final_pcm_parts.append(faded_pcm)

        # Seam silence (skip after the last chunk)
        if idx < len(ordered_chunks) - 1:
            if c_res.is_paragraph_end:
                seam_pause_s = profile.paragraph_break_s
            else:
                seam_pause_s = profile.pause_ms / 1000.0

            silence_frames = int(seam_pause_s * PCM_SAMPLE_RATE)
            silence_pcm = b'\x00' * (silence_frames * PCM_BYTES_PER_FRAME)
            final_pcm_parts.append(silence_pcm)
            actual_pause_dur = len(silence_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
            running_offset += (trimmed_dur + actual_pause_dur)
        else:
            running_offset += trimmed_dur

    # Assemble complete raw PCM
    assembled_pcm = b"".join(final_pcm_parts)

    # Edge trim on final audio: ensure start has <= 30ms lead padding
    if final_alignment:
        final_head_start = max(0.0, final_alignment[0]["start"] - 0.030)
        if final_head_start > 0.01:
            head_frame = int(final_head_start * PCM_SAMPLE_RATE)
            assembled_pcm = assembled_pcm[head_frame * PCM_BYTES_PER_FRAME :]
            for w in final_alignment:
                w["start"] = max(0.0, round(w["start"] - final_head_start, 3))
                w["end"] = max(0.0, round(w["end"] - final_head_start, 3))

    # Apply final 10ms micro-fade to file boundaries
    assembled_pcm = apply_pcm_fade(assembled_pcm, fade_ms=10.0, sample_rate=PCM_SAMPLE_RATE)

    # Two-pass Loudnorm normalization and MP3 encoding
    final_mp3 = raw_pcm_to_mp3(assembled_pcm, loudnorm=True)

    return final_mp3, final_alignment
