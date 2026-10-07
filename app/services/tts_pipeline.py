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


def get_last_audible_time(
    pcm_bytes: bytes,
    channels: int = PCM_CHANNELS,
    sample_rate: int = PCM_SAMPLE_RATE,
    threshold_db: float = -50.0,
    window_ms: float = 20.0,
    search_s: float = 1.5,
) -> float:
    """
    Finds the timestamp (in seconds from start of pcm_bytes) where audio energy
    last drops below threshold_db. Scans in 20 ms windows over the last search_s (1.5 s).
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
    model_char_limit = 10000 if "multilingual" in str(resolved_model_id).lower() else 40000
    chunk_max_chars = min(1500, model_char_limit)

    # Split text into chunks
    chunks = split_text_into_chunks(prepared_text, min_chars=800, max_chars=chunk_max_chars)
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

    # Decode, trim, stitch PCM and shift alignment
    final_pcm_parts: list[bytes] = []
    final_alignment: list[dict] = []
    running_offset = 0.0

    for idx, c_res in enumerate(ordered_chunks):
        pcm_bytes, dur = mp3_to_raw_pcm(c_res.mp3_bytes)
        words = c_res.alignment
        if not words:
            raise ValueError(f"Missing word alignment in chunk {idx}")

        # Alignment-based trimming with audible tail cap
        first_word_start = words[0]["start"]
        last_word_end = words[-1]["end"]

        trim_start = max(0.0, first_word_start - 0.030)
        default_trim_end = min(dur, last_word_end + 0.130)

        # Cap tail at ~150 ms after audio energy drops below -50 dB, ensuring at least 80ms cushion
        t_audible = get_last_audible_time(pcm_bytes, channels=PCM_CHANNELS, sample_rate=PCM_SAMPLE_RATE, threshold_db=-50.0)
        if t_audible > first_word_start and (t_audible + 0.150) < default_trim_end:
            trim_end = max(t_audible + 0.150, last_word_end)
        else:
            trim_end = default_trim_end

        # Guarantee chunk trim does not cut closer than 80 ms after last audible speech
        if t_audible > first_word_start and (trim_end - t_audible) < 0.080:
            trim_end = min(dur, t_audible + 0.080)

        # Slice PCM frames
        start_frame = int(trim_start * PCM_SAMPLE_RATE)
        end_frame = int(trim_end * PCM_SAMPLE_RATE)
        sliced_pcm = pcm_bytes[start_frame * PCM_BYTES_PER_FRAME : end_frame * PCM_BYTES_PER_FRAME]
        trimmed_dur = len(sliced_pcm) / (PCM_SAMPLE_RATE * PCM_BYTES_PER_FRAME)

        # Shift word alignment
        for w in words:
            shifted_start = running_offset + (w["start"] - trim_start)
            shifted_end = running_offset + (min(w["end"], trim_end) - trim_start)
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
