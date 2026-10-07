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
import math
import os
import re
import shutil
import statistics
import subprocess
import time
from typing import Optional, Union

import requests

from app.core.config import settings
from app.core.llm import ELEVENLABS_VOICES
from app.schemas.schema_ai import StoryType
from app.services.tts_profiles import TTSProfile, get_tts_profile, prepare_text_for_tts

logger = logging.getLogger(__name__)

# Sample rate and format for raw PCM handling (matches legacy format: 44.1 kHz, mono, 16-bit)
PCM_SAMPLE_RATE = 44100
PCM_CHANNELS = 1
PCM_BYTES_PER_SAMPLE = 2  # 16-bit
PCM_BYTES_PER_FRAME = PCM_CHANNELS * PCM_BYTES_PER_SAMPLE  # 2 bytes


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
    Applies a 5-10 ms linear fade-in and fade-out to 16-bit PCM frames.
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
        for ch in range(PCM_CHANNELS):
            samples[PCM_CHANNELS * i + ch] = int(samples[PCM_CHANNELS * i + ch] * factor)

    # Linear fade-out
    for i in range(min(fade_frames, total_frames)):
        factor = (fade_frames - 1 - i) / float(fade_frames)
        idx = total_frames - fade_frames + i
        if idx >= 0:
            for ch in range(PCM_CHANNELS):
                samples[PCM_CHANNELS * idx + ch] = int(samples[PCM_CHANNELS * idx + ch] * factor)

    return samples.tobytes()


def get_first_audible_time(
    pcm_bytes: bytes,
    channels: int = PCM_CHANNELS,
    sample_rate: int = PCM_SAMPLE_RATE,
    threshold_db: float = -50.0,
    window_ms: float = 10.0,
    search_s: float = 2.0,
) -> float:
    """
    Finds the timestamp (in seconds from start of pcm_bytes) where audio energy
    first exceeds threshold_db. Scans in window_ms (10 ms) windows from the start up to search_s.
    Returns the start time of the first window >= threshold_db, or 0.0 if not found.
    """
    bytes_per_sample = 2
    bytes_per_frame = channels * bytes_per_sample
    total_frames = len(pcm_bytes) // bytes_per_frame
    if total_frames == 0:
        return 0.0

    samples = array.array("h", pcm_bytes)
    if channels == 2:
        mono_samples = array.array("h", ((samples[2 * i] + samples[2 * i + 1]) // 2 for i in range(total_frames)))
    else:
        mono_samples = samples

    window_frames = int((window_ms / 1000.0) * sample_rate)
    head_frames = min(total_frames, int(search_s * sample_rate))

    for f_idx in range(0, head_frames, window_frames):
        chunk = mono_samples[f_idx : min(f_idx + window_frames, total_frames)]
        if not chunk:
            continue
        sum_sq = sum(s * s for s in chunk)
        rms = math.sqrt(sum_sq / float(len(chunk)))
        if rms > 0:
            db = 20.0 * math.log10(rms / 32767.0)
        else:
            db = -100.0
        if db >= threshold_db:
            return f_idx / float(sample_rate)

    return 0.0


def get_last_audible_time(
    pcm_bytes: bytes,
    channels: int = PCM_CHANNELS,
    sample_rate: int = PCM_SAMPLE_RATE,
    threshold_db: float = -50.0,
    window_ms: float = 10.0,
    search_s: float = 2.0,
) -> float:
    """
    Finds the timestamp (in seconds from start of pcm_bytes) where audio energy
    last drops below threshold_db. Scans in window_ms (10 ms) windows over the last search_s (2.0 s).
    """
    bytes_per_sample = 2
    bytes_per_frame = channels * bytes_per_sample
    total_frames = len(pcm_bytes) // bytes_per_frame
    if total_frames == 0:
        return 0.0

    samples = array.array("h", pcm_bytes)
    if channels == 2:
        mono_samples = array.array("h", ((samples[2 * i] + samples[2 * i + 1]) // 2 for i in range(total_frames)))
    else:
        mono_samples = samples

    window_frames = int((window_ms / 1000.0) * sample_rate)
    tail_frames = int(search_s * sample_rate)
    start_frame = max(0, total_frames - tail_frames)

    last_audible_frame = start_frame
    for f_idx in range(start_frame, total_frames, window_frames):
        chunk = mono_samples[f_idx : min(f_idx + window_frames, total_frames)]
        if not chunk:
            continue
        sum_sq = sum(s * s for s in chunk)
        rms = math.sqrt(sum_sq / float(len(chunk)))
        if rms > 0:
            db = 20.0 * math.log10(rms / 32767.0)
        else:
            db = -100.0
        if db >= threshold_db:
            last_audible_frame = f_idx + len(chunk)

    return last_audible_frame / float(sample_rate)


def parse_alignment_to_whitespace_words(alignment: dict, display_text: Optional[str] = None) -> list[dict]:
    """
    Parses character-level alignments into exactly one word per whitespace-delimited
    token of the DISPLAY text, matching the frontend's display text tokenization 1-to-1.
    XML <break> tags are stripped from character stream before assembly.
    For display tokens with no speakable characters (a lone dash, a lone ellipsis,
    an emoji, a bullet, markdown tokens like '**', standalone parentheses),
    emits a zero-length entry at the previous word's end time so index-based
    highlighting never drifts.
    Numbers with decimals/commas, contractions, and words with punctuation have
    outer boundary punctuation stripped for display while preserving exact timestamps.
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

    # If display_text is provided, strip XML tags (such as <break time="...s" />) before tokenizing
    if display_text:
        display_text = re.sub(r'<[^>]+>', ' ', display_text)
    else:
        display_text = "".join(filt_chars)

    display_tokens = display_text.split()
    if not display_tokens:
        return []

    # 2. Extract spoken word units from filt_chars (grouped by whitespace in character stream)
    raw_spoken_units = []
    curr_c, curr_s, curr_e = [], None, None
    for c, s, e in zip(filt_chars, filt_starts, filt_ends):
        if c in (" ", "\t", "\n", "\r"):
            if curr_c:
                raw_spoken_units.append({
                    "text": "".join(curr_c),
                    "start": curr_s,
                    "end": curr_e,
                })
                curr_c, curr_s, curr_e = [], None, None
        else:
            if curr_s is None:
                curr_s = s
            curr_c.append(c)
            curr_e = e
    if curr_c:
        raw_spoken_units.append({
            "text": "".join(curr_c),
            "start": curr_s,
            "end": curr_e,
        })

    # Filter to speakable units (containing at least one alphanumeric char)
    speakable_units = [u for u in raw_spoken_units if any(ch.isalnum() for ch in u["text"])]

    # 3. Match display_tokens to speakable_units 1-to-1
    words = []
    spk_idx = 0
    num_spk = len(speakable_units)
    prev_end = 0.0

    for token in display_tokens:
        has_speakable = any(ch.isalnum() for ch in token)
        if not has_speakable:
            # Standalone unspeakable token: emit zero-length entry at previous word's end time
            words.append({
                "word": token,
                "start": round(prev_end, 3),
                "end": round(prev_end, 3),
            })
            continue

        clean_w = token.strip('.,!?;:"“”‘’()[]{}*`_~')
        if not clean_w:
            clean_w = token

        if spk_idx < num_spk:
            spk = speakable_units[spk_idx]
            tok_start = spk["start"]
            tok_end = spk["end"]
            spk_idx += 1
            prev_end = tok_end
            words.append({
                "word": clean_w,
                "start": round(tok_start, 3),
                "end": round(tok_end, 3),
            })
        else:
            words.append({
                "word": clean_w,
                "start": round(prev_end, 3),
                "end": round(prev_end, 3),
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

    # Merge final chunk shorter than 450 chars into previous chunk when model limit allows (<= 1800 chars)
    if len(raw_chunks) > 1 and len(raw_chunks[-1][0]) < 450:
        prev_text, prev_is_p = raw_chunks[-2]
        last_text, last_is_p = raw_chunks[-1]
        if len(prev_text) + len(last_text) + 2 <= max(max_chars, 1800):
            sep = "\n\n" if prev_is_p else " "
            raw_chunks[-2] = (prev_text + sep + last_text, last_is_p)
            raw_chunks.pop()

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
                words = parse_alignment_to_whitespace_words(clean_alignment, display_text=chunk.text)
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
    """Decodes MP3 bytes to raw 16-bit 44.1kHz mono PCM frames via ffmpeg."""
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
    Normalizes loudness and exports MP3 matching legacy format (44100 Hz, mono, 128k).
    Uses two-pass loudnorm with linear=true so quiet meditation audio is never pumped.
    """
    ffmpeg_bin = get_ffmpeg_bin()
    if not loudnorm:
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS), "-i", "pipe:0",
            "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS),
            "-c:a", "libmp3lame", "-b:a", "128k",
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

    # Pass 2: Apply linear normalization and encode to MP3 matching legacy format (44100 Hz, mono, 128k)
    pass2_cmd = [
        ffmpeg_bin, "-y",
        "-f", "s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS), "-i", "pipe:0",
        "-af", filter_str,
        "-ar", str(PCM_SAMPLE_RATE), "-ac", str(PCM_CHANNELS),
        "-c:a", "libmp3lame", "-b:a", "128k",
        "-f", "mp3", "pipe:1"
    ]
    p2 = subprocess.run(pass2_cmd, input=pcm_bytes, capture_output=True, check=True)
    return p2.stdout


def compute_articulation_rate(alignment: list[dict], audio_duration_s: Optional[float] = None) -> float:
    """
    Computes articulation rate (words per minute) based on spoken words and
    phonation time (speech duration excluding internal silence gaps > 250 ms).
    """
    if not alignment:
        return 0.0

    words = [w for w in alignment if any(c.isalnum() for c in w.get("word", ""))]
    if not words:
        return 0.0

    first_start = words[0]["start"]
    last_end = words[-1]["end"]
    speech_time = max(0.001, last_end - first_start)

    # Calculate internal pauses > 250 ms (0.250 s)
    total_internal_gaps = 0.0
    for i in range(len(words) - 1):
        gap = words[i + 1]["start"] - words[i]["end"]
        if gap > 0.250:
            total_internal_gaps += gap

    phonation_time = max(0.001, speech_time - total_internal_gaps)
    return (len(words) / phonation_time) * 60.0


def compute_articulation_rate_from_pcm(
    pcm_bytes: bytes,
    word_count: int,
    channels: int = PCM_CHANNELS,
    sample_rate: int = PCM_SAMPLE_RATE,
    threshold_db: float = -40.0,
    min_pause_ms: float = 250.0,
    window_ms: float = 10.0,
) -> float:
    """
    Computes articulation rate (words per minute) directly from decoded PCM frames:
    words / (phonation time in minutes), where pauses > min_pause_ms (250 ms)
    below threshold_db (-40 dB) between first and last audible sounds are subtracted.
    """
    bytes_per_sample = 2
    bytes_per_frame = channels * bytes_per_sample
    total_frames = len(pcm_bytes) // bytes_per_frame
    if total_frames == 0 or word_count <= 0:
        return 0.0

    samples = array.array("h", pcm_bytes)
    if channels == 2:
        mono_samples = array.array("h", ((samples[2 * i] + samples[2 * i + 1]) // 2 for i in range(total_frames)))
    else:
        mono_samples = samples

    window_frames = int((window_ms / 1000.0) * sample_rate)
    num_windows = total_frames // window_frames
    if num_windows == 0:
        return 0.0

    dbs = []
    for w in range(num_windows):
        chunk = mono_samples[w * window_frames : (w + 1) * window_frames]
        sum_sq = sum(s * s for s in chunk)
        rms = math.sqrt(sum_sq / float(len(chunk))) if chunk else 0.0
        db = 20.0 * math.log10(rms / 32767.0) if rms > 0 else -100.0
        dbs.append(db)

    # Speech onset and audible end (-50 dB boundary to not clip soft phonation edges)
    start_win = 0
    while start_win < num_windows and dbs[start_win] < -50.0:
        start_win += 1

    end_win = num_windows - 1
    while end_win >= 0 and dbs[end_win] < -50.0:
        end_win -= 1

    if start_win > end_win:
        return 0.0

    total_span_s = (end_win - start_win + 1) * (window_ms / 1000.0)
    min_pause_wins = int(min_pause_ms / window_ms)
    pause_wins = 0
    curr_pause_wins = 0

    for w in range(start_win, end_win + 1):
        if dbs[w] < threshold_db:
            curr_pause_wins += 1
        else:
            if curr_pause_wins >= min_pause_wins:
                pause_wins += curr_pause_wins
            curr_pause_wins = 0
    if curr_pause_wins >= min_pause_wins:
        pause_wins += curr_pause_wins

    pause_s = pause_wins * (window_ms / 1000.0)
    phonation_s = max(0.1, total_span_s - pause_s)
    return (word_count / phonation_s) * 60.0


def select_outlier_chunks(
    chunk_metrics: list[dict],  # list of {"index": int, "rate": float, "word_count": int}
) -> tuple[float, list[dict]]:
    """
    Computes median articulation rate across chunks and selects outliers outside
    the acceptable tolerance band (6% default; 8% for short chunks < 60 words).
    """
    valid_rates = [c["rate"] for c in chunk_metrics if c.get("rate", 0) > 0]
    if not valid_rates:
        return 0.0, []

    median_rate = statistics.median(valid_rates)
    if median_rate <= 0:
        return 0.0, []

    outliers = []
    for c in chunk_metrics:
        rate = c.get("rate", 0.0)
        word_count = c.get("word_count", 0)
        if rate <= 0:
            continue
        threshold = 0.08 if word_count < 60 else 0.06
        deviation = abs(rate - median_rate) / median_rate
        if deviation > threshold:
            outliers.append({
                "chunk_index": c["index"],
                "rate": rate,
                "word_count": word_count,
                "deviation": deviation,
                "threshold": threshold,
            })
    return median_rate, outliers


def apply_chunk_atempo_pcm(
    pcm_bytes: bytes,
    alignment: list[dict],
    factor: float,
    sample_rate: int = PCM_SAMPLE_RATE,
    channels: int = PCM_CHANNELS,
) -> tuple[bytes, list[dict]]:
    """
    Applies ffmpeg atempo filter directly on raw PCM audio frames.
    Dead zone: factors between 0.97 and 1.03 skip atempo entirely.
    Clamps factor to [0.92, 1.08]. Scales alignment word timestamps monotonically.
    """
    if abs(factor - 1.0) < 1e-4:
        return pcm_bytes, alignment

    # Dead zone: 0.97 to 1.03 (no atempo)
    if 0.97 <= factor <= 1.03:
        return pcm_bytes, alignment

    clamped_factor = min(1.08, max(0.92, factor))
    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels),
        "-i", "pipe:0",
        "-filter:a", f"atempo={clamped_factor:.4f}",
        "-f", "s16le", "pipe:1",
    ]
    proc = subprocess.run(cmd, input=pcm_bytes, capture_output=True, check=True)
    scaled_pcm = proc.stdout

    bytes_per_sample = 2
    bytes_per_frame = channels * bytes_per_sample
    new_dur = len(scaled_pcm) / float(sample_rate * bytes_per_frame)

    scaled_alignment = []
    prev_end = 0.0
    for w in alignment:
        s = max(0.0, round(w["start"] / clamped_factor, 3))
        e = min(new_dur, max(s, round(w["end"] / clamped_factor, 3)))
        if s < prev_end:
            s = prev_end
        if e < s:
            e = s
        prev_end = e
        scaled_alignment.append({
            "word": w["word"],
            "start": s,
            "end": e,
        })

    if scaled_alignment and scaled_alignment[-1]["end"] > new_dur:
        scaled_alignment[-1]["end"] = new_dur

    return scaled_pcm, scaled_alignment


def apply_chunk_atempo(
    mp3_bytes: bytes,
    alignment: list[dict],
    factor: float,
) -> tuple[bytes, list[dict]]:
    """
    Applies ffmpeg atempo filter to chunk mp3 bytes and scales alignment timestamps.
    Factor (target / measured) is clamped to [0.92, 1.08] and respects dead zone [0.97, 1.03].
    """
    if abs(factor - 1.0) < 1e-4 or (0.97 <= factor <= 1.03):
        return mp3_bytes, alignment

    clamped_factor = min(1.08, max(0.92, factor))
    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "mp3", "-i", "pipe:0",
        "-filter:a", f"atempo={clamped_factor:.4f}",
        "-ar", str(PCM_SAMPLE_RATE),
        "-ac", str(PCM_CHANNELS),
        "-b:a", "128k",
        "-f", "mp3", "pipe:1",
    ]
    proc = subprocess.run(cmd, input=mp3_bytes, capture_output=True, check=True)
    scaled_mp3 = proc.stdout

    # Get new audio duration
    _, new_dur = mp3_to_raw_pcm(scaled_mp3)

    # Scale alignment timestamps: as tempo increases (clamped_factor > 1), duration shrinks
    scaled_alignment = []
    prev_end = 0.0
    for w in alignment:
        s = max(0.0, round(w["start"] / clamped_factor, 3))
        e = min(new_dur, max(s, round(w["end"] / clamped_factor, 3)))
        if s < prev_end:
            s = prev_end
        if e < s:
            e = s
        prev_end = e
        scaled_alignment.append({
            "word": w["word"],
            "start": s,
            "end": e,
        })

    # Final clamp check: ensure last end <= new_dur
    if scaled_alignment and scaled_alignment[-1]["end"] > new_dur:
        scaled_alignment[-1]["end"] = new_dur

    return scaled_mp3, scaled_alignment


def apply_pace_normalization(
    ordered_chunks: list[ChunkResult],
    chunks: list[TextChunk],
    resolved_voice_id: str,
    resolved_model_id: str,
    voice_settings: dict,
    api_key: str,
    max_retries: int = 3,
) -> list[ChunkResult]:
    """
    Two-pass relative pace normalization across chunks:
    1. Saves pass-1 chunk audio to untracked scratch/pass1_chunks/ for free auditing.
    2. Computes articulation rate per chunk directly from decoded audio PCM and finds story median.
    3. Identifies outliers (>6% deviation; >8% for chunks < 60 words).
    4. For outliers >8%: regenerates chunk once with damped speed = clamp(current_speed * (factor ** 0.5), 0.88, 1.12)
       toward nearest band edge (median +/- 5%), capped at 30% of chunks per story (worst outliers first).
    5. Applies ffmpeg atempo directly on decoded PCM (factor clamped to [0.92, 1.08], dead zone [0.97, 1.03]).
    6. Logs per-chunk numbers only (articulation rate, factor, regenerated yes/no). No story text.
    """
    if len(ordered_chunks) <= 1:
        return ordered_chunks

    # Save pass-1 chunk audio to untracked scratch/ for reproducible verification
    try:
        scratch_pass1_dir = os.path.abspath(os.path.join("scratch", "pass1_chunks"))
        os.makedirs(scratch_pass1_dir, exist_ok=True)
        for c_res in ordered_chunks:
            with open(os.path.join(scratch_pass1_dir, f"chunk_{c_res.index}.mp3"), "wb") as f:
                f.write(c_res.mp3_bytes)
    except Exception as cache_exc:
        logger.debug("Failed saving pass1 chunk to scratch: %s", cache_exc)

    # Measure initial articulation rates directly from decoded PCM (with alignment fallback for mock bytes)
    chunk_metrics = []
    for c_res in ordered_chunks:
        try:
            pcm_bytes, _ = mp3_to_raw_pcm(c_res.mp3_bytes)
            w_count = len([w for w in c_res.alignment if any(ch.isalnum() for ch in w.get("word", ""))])
            rate = compute_articulation_rate_from_pcm(pcm_bytes, word_count=w_count)
            if rate <= 0.0:
                rate = compute_articulation_rate(c_res.alignment)
        except Exception:
            rate = compute_articulation_rate(c_res.alignment)
            w_count = len([w for w in c_res.alignment if any(ch.isalnum() for ch in w.get("word", ""))])

        chunk_metrics.append({
            "index": c_res.index,
            "rate": rate,
            "word_count": w_count,
        })

    median_rate, outliers = select_outlier_chunks(chunk_metrics)
    if not outliers or median_rate <= 0:
        for m in chunk_metrics:
            logger.info("Pace chunk %d: rate=%.1f WPM, median=%.1f, factor=1.000, regenerated=False", m["index"], m["rate"], median_rate)
        return ordered_chunks

    # Cap regeneration at 30% of chunks per story
    max_regenerations = math.floor(len(ordered_chunks) * 0.30)

    # Sort candidates for regeneration: deviation > 0.08, descending deviation
    regen_candidates = [o for o in outliers if o["deviation"] > 0.08]
    regen_candidates.sort(key=lambda x: x["deviation"], reverse=True)
    allowed_regen_indices = {o["chunk_index"] for o in regen_candidates[:max_regenerations]}

    normalized_chunks = list(ordered_chunks)
    base_speed = voice_settings.get("speed", 1.0)

    for c_idx, c_res in enumerate(ordered_chunks):
        outlier_info = next((o for o in outliers if o["chunk_index"] == c_idx), None)
        if not outlier_info:
            logger.info("Pace chunk %d: rate=%.1f WPM, median=%.1f, factor=1.000, regenerated=False", c_idx, chunk_metrics[c_idx]["rate"], median_rate)
            continue

        measured_rate = outlier_info["rate"]
        regenerated = False

        # Band-edge correction: correct toward nearest edge of median +/- 5% (not median itself)
        if measured_rate < median_rate:
            target_rate = median_rate * 0.95
        else:
            target_rate = median_rate * 1.05

        factor = target_rate / measured_rate if measured_rate > 0 else 1.0
        current_res = c_res

        # Regeneration for severe outliers (>8%) within 30% budget
        if c_idx in allowed_regen_indices and api_key and api_key != "your_elevenlabs_api_key_here":
            damped_speed = base_speed * (factor ** 0.5)
            target_speed = min(1.12, max(0.88, damped_speed))
            adjusted_settings = dict(voice_settings)
            adjusted_settings["speed"] = round(target_speed, 3)

            try:
                new_chunk_res = fetch_chunk_audio_with_retry(
                    chunk=chunks[c_idx],
                    resolved_voice_id=resolved_voice_id,
                    resolved_model_id=resolved_model_id,
                    voice_settings=adjusted_settings,
                    api_key=api_key,
                    max_retries=max_retries,
                )
                current_res = new_chunk_res
                regenerated = True

                # Re-measure using decoded PCM
                try:
                    new_pcm, _ = mp3_to_raw_pcm(current_res.mp3_bytes)
                    new_wc = len([w for w in current_res.alignment if any(ch.isalnum() for ch in w.get("word", ""))])
                    new_rate = compute_articulation_rate_from_pcm(new_pcm, word_count=new_wc)
                    if new_rate <= 0.0:
                        new_rate = compute_articulation_rate(current_res.alignment)
                except Exception:
                    new_rate = compute_articulation_rate(current_res.alignment)

                if new_rate > 0:
                    measured_rate = new_rate
                    if measured_rate < median_rate:
                        target_rate = median_rate * 0.95
                    else:
                        target_rate = median_rate * 1.05
                    factor = target_rate / measured_rate
            except Exception as exc:
                logger.warning("Pace chunk %d regeneration failed (%s: %s). Falling back to atempo.", c_idx, type(exc).__name__, str(exc))

        # Atempo on decoded PCM: clamped to [0.92, 1.08], dead zone [0.97, 1.03]
        atempo_factor = min(1.08, max(0.92, factor))
        if atempo_factor < 0.97 or atempo_factor > 1.03:
            scaled = False
            try:
                pcm_bytes, _ = mp3_to_raw_pcm(current_res.mp3_bytes)
                scaled_pcm, scaled_alignment = apply_chunk_atempo_pcm(
                    pcm_bytes=pcm_bytes,
                    alignment=current_res.alignment,
                    factor=atempo_factor,
                )
                scaled_mp3 = raw_pcm_to_mp3(scaled_pcm, loudnorm=False)
                current_res = ChunkResult(
                    index=current_res.index,
                    mp3_bytes=scaled_mp3,
                    alignment=scaled_alignment,
                    is_paragraph_end=current_res.is_paragraph_end,
                )
                scaled = True
            except Exception:
                pass

            if not scaled:
                try:
                    scaled_mp3, scaled_alignment = apply_chunk_atempo(
                        mp3_bytes=current_res.mp3_bytes,
                        alignment=current_res.alignment,
                        factor=atempo_factor,
                    )
                    current_res = ChunkResult(
                        index=current_res.index,
                        mp3_bytes=scaled_mp3,
                        alignment=scaled_alignment,
                        is_paragraph_end=current_res.is_paragraph_end,
                    )
                except Exception as exc:
                    logger.warning("Pace chunk %d atempo scaling failed (%s: %s).", c_idx, type(exc).__name__, str(exc))

        normalized_chunks[c_idx] = current_res
        logger.info(
            "Pace chunk %d: rate=%.1f WPM, median=%.1f, factor=%.3f, regenerated=%s",
            c_idx,
            measured_rate,
            median_rate,
            round(atempo_factor, 3),
            regenerated,
        )

    return normalized_chunks


def execute_tts_pipeline_v2(
    text: str,
    story_type: Optional[Union[str, StoryType]] = None,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
    style: Optional[float] = None,
    return_timestamps: bool = True,
    max_retries: int = 3,
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
    resolved_model_id = model_id or getattr(settings, "TTS_V2_MODEL_ID", None) or settings.ELEVENLABS_MODEL_ID

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

    # Derive max chunk size from model limit (10k for multilingual v2, 40k for turbo v2.5; cap at 1500)
    # When TTS_PACE_NORMALIZE is enabled, use smaller 500-900 char chunks on sentence boundaries
    pace_norm_enabled = getattr(settings, "TTS_PACE_NORMALIZE", False)
    if pace_norm_enabled:
        chunk_min_chars = 500
        chunk_max_chars = 900
    else:
        model_char_limit = 10000 if "multilingual" in str(resolved_model_id).lower() else 40000
        chunk_min_chars = 800
        chunk_max_chars = min(1500, model_char_limit)

    # Split text into chunks
    chunks = split_text_into_chunks(prepared_text, min_chars=chunk_min_chars, max_chars=chunk_max_chars)
    if not chunks:
        raise ValueError("Prepared text resulted in 0 chunks")

    # Mock TTS path when API key is missing
    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        mock_audio = b"ID3\x04\x00\x00\x00\x00\x00\x00"
        words_list = text.split() if text else prepared_text.split()
        mock_alignment = []
        prev_end = 0.0
        for i, w in enumerate(words_list):
            if not any(c.isalnum() for c in w):
                mock_alignment.append({
                    "word": w,
                    "start": round(prev_end, 2),
                    "end": round(prev_end, 2),
                })
            else:
                clean = w.strip('.,!?;:"“”‘’()[]{}*`_~') or w
                start = round(prev_end + 0.1, 2)
                end = round(start + 0.3, 2)
                prev_end = end
                mock_alignment.append({
                    "word": clean,
                    "start": start,
                    "end": end,
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
                max_retries=max_retries,
            ): chunk.index
            for chunk in chunks
        }
        for future in as_completed(future_map):
            chunk_res = future.result()  # Raises if any chunk failed
            chunk_results[chunk_res.index] = chunk_res

    # Order chunks sequentially
    ordered_chunks = [chunk_results[i] for i in range(len(chunks))]

    # Phase 2 Pass 2: Pace normalization (only when TTS_PACE_NORMALIZE is enabled)
    if getattr(settings, "TTS_PACE_NORMALIZE", False):
        try:
            ordered_chunks = apply_pace_normalization(
                ordered_chunks=ordered_chunks,
                chunks=chunks,
                resolved_voice_id=resolved_voice_id,
                resolved_model_id=resolved_model_id,
                voice_settings=voice_settings,
                api_key=settings.ELEVENLABS_API_KEY,
                max_retries=max_retries,
            )
        except Exception as norm_exc:
            logger.warning(
                "TTS pace normalization failed (%s: %s). Continuing with un-normalized chunks.",
                type(norm_exc).__name__,
                str(norm_exc),
            )

    # Decode, trim, stitch PCM and shift alignment
    # Pass 1: Decode PCM, determine energy-based boundaries, and measure head/tail silence per chunk
    chunk_specs = []
    for idx, c_res in enumerate(ordered_chunks):
        pcm_bytes, dur = mp3_to_raw_pcm(c_res.mp3_bytes)
        words = c_res.alignment
        if not words:
            raise ValueError(f"Missing word alignment in chunk {idx}")

        first_word_start = words[0]["start"]
        last_word_end = words[-1]["end"]

        # Head trimming:
        # t_onset = first 10 ms window >= -50 dB
        # trim_start = max(first_word_start - 0.030, t_onset - 0.050); never later than first_word_start
        t_onset = get_first_audible_time(pcm_bytes, channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE, threshold_db=-50.0, window_ms=10.0)
        if t_onset <= 0.0:
            t_onset = first_word_start
        candidate_start = max(first_word_start - 0.030, t_onset - 0.050)
        trim_start = max(0.0, min(candidate_start, first_word_start))

        # Tail trimming:
        # t_audible = last 10 ms window >= -50 dB
        # trim_end = min(dur, t_audible + 0.150); never cut earlier than t_audible + 0.080
        t_audible = get_last_audible_time(pcm_bytes, channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE, threshold_db=-50.0, window_ms=10.0)
        if t_audible <= 0.0:
            t_audible = last_word_end
        trim_end = min(dur, max(t_audible + 0.080, t_audible + 0.150))

        # Slice PCM frames
        start_frame = int(trim_start * PCM_SAMPLE_RATE)
        end_frame = int(trim_end * PCM_SAMPLE_RATE)
        sliced_pcm = pcm_bytes[start_frame * PCM_BYTES_PER_FRAME : end_frame * PCM_BYTES_PER_FRAME]

        # Apply 10 ms linear micro-fade inside the cushion
        faded_pcm = apply_pcm_fade(sliced_pcm, fade_ms=10.0, sample_rate=PCM_SAMPLE_RATE)

        measured_head = max(0.0, t_onset - trim_start)
        measured_tail = max(0.0, trim_end - t_audible)

        chunk_specs.append({
            "faded_pcm": faded_pcm,
            "words": words,
            "trim_start": trim_start,
            "trim_end": trim_end,
            "trimmed_dur": len(faded_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME),
            "measured_head": measured_head,
            "measured_tail": measured_tail,
            "is_paragraph_end": c_res.is_paragraph_end,
        })

    # Pass 2: Assemble trimmed PCM, inject target-gap silence, and shift alignment monotonically
    final_pcm_parts: list[bytes] = []
    final_alignment: list[dict] = []
    running_offset = 0.0

    for idx, spec in enumerate(chunk_specs):
        final_pcm_parts.append(spec["faded_pcm"])
        trim_start = spec["trim_start"]
        trim_end = spec["trim_end"]
        trimmed_dur = spec["trimmed_dur"]

        # Shift word alignment
        for w in spec["words"]:
            shifted_start = running_offset + (w["start"] - trim_start)
            shifted_end = running_offset + (min(w["end"], trim_end) - trim_start)
            final_alignment.append({
                "word": w["word"],
                "start": max(0.0, round(shifted_start, 3)),
                "end": max(0.0, round(shifted_end, 3)),
            })

        # Seam silence (skip after the last chunk)
        if idx < len(chunk_specs) - 1:
            if spec["is_paragraph_end"]:
                target_gap = profile.paragraph_break_s
            else:
                target_gap = profile.seam_gap_ms / 1000.0

            cur_tail = spec["measured_tail"]
            next_head = chunk_specs[idx + 1]["measured_head"]

            inserted_s = max(0.0, target_gap - cur_tail - next_head)
            silence_frames = int(inserted_s * PCM_SAMPLE_RATE)
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

    # Cap final-file tail at about 150 ms after energy drops below -50 dB
    t_audible_final = get_last_audible_time(assembled_pcm, channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE, threshold_db=-50.0)
    total_assembled_dur = len(assembled_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
    if t_audible_final > 0 and (total_assembled_dur - t_audible_final) > 0.150:
        target_tail_dur = t_audible_final + 0.150
        cut_frame = int(target_tail_dur * PCM_SAMPLE_RATE)
        assembled_pcm = assembled_pcm[: cut_frame * PCM_BYTES_PER_FRAME]
        total_assembled_dur = len(assembled_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)
        if final_alignment:
            final_alignment[-1]["end"] = min(final_alignment[-1]["end"], round(target_tail_dur, 3))

    # Guarantee tail cushion after last audible energy is never shorter than 80-100 ms (cushion for 10ms boundary fade)
    MIN_TAIL_CUSHION_S = 0.080  # 80 ms minimum cushion
    if t_audible_final > 0 and (total_assembled_dur - t_audible_final) < MIN_TAIL_CUSHION_S:
        needed_pad_s = MIN_TAIL_CUSHION_S - (total_assembled_dur - t_audible_final)
        pad_frames = int(needed_pad_s * PCM_SAMPLE_RATE)
        assembled_pcm += b'\x00' * (pad_frames * PCM_BYTES_PER_FRAME)

    # Ensure final alignment matches display text whitespace tokens 1-to-1
    if text and text.strip():
        tokens = text.split()
        if len(final_alignment) != len(tokens):
            combined_chars, combined_starts, combined_ends = [], [], []
            for w in final_alignment:
                w_chars = list(w["word"])
                dur_per_char = (w["end"] - w["start"]) / max(1, len(w_chars))
                for ci, c in enumerate(w_chars):
                    combined_chars.append(c)
                    combined_starts.append(round(w["start"] + ci * dur_per_char, 3))
                    combined_ends.append(round(w["start"] + (ci + 1) * dur_per_char, 3))
                combined_chars.append(" ")
                combined_starts.append(round(w["end"], 3))
                combined_ends.append(round(w["end"], 3))
            remapped_alignment = parse_alignment_to_whitespace_words(
                {
                    "characters": combined_chars,
                    "character_start_times_seconds": combined_starts,
                    "character_end_times_seconds": combined_ends,
                },
                display_text=text,
            )
            if len(remapped_alignment) == len(tokens):
                final_alignment = remapped_alignment

    # Apply final 10ms micro-fade to file boundaries
    assembled_pcm = apply_pcm_fade(assembled_pcm, fade_ms=10.0, sample_rate=PCM_SAMPLE_RATE)

    # Two-pass Loudnorm normalization and MP3 encoding
    final_mp3 = raw_pcm_to_mp3(assembled_pcm, loudnorm=True)

    # Final audio duration in seconds
    final_audio_dur = round(len(assembled_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME), 3)

    # Clamp every alignment time to [0.0, final_audio_dur], guaranteeing monotonicity and non-negativity
    prev_s = 0.0
    for w in final_alignment:
        w["start"] = max(prev_s, max(0.0, min(round(w["start"], 3), final_audio_dur)))
        w["end"] = max(w["start"], min(round(w["end"], 3), final_audio_dur))
        prev_s = w["start"]

    return final_mp3, final_alignment
