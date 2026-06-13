import os
import uuid
import requests
from pathlib import Path
from langchain_openai import ChatOpenAI
from app.core.config import settings


# ElevenLabs TTS & LLM Configuration for House of Juliette
# ---------------------------------------------------------------------------
# LLM — SuperGrok (xAI)
# ---------------------------------------------------------------------------

def get_story_llm(
    temperature: float | None = None,
    model_name: str | None = None,
):
    """
    Returns a SuperGrok LangChain-compatible LLM instance.
    Model name and temperature are loaded from settings (config.py / .env).

    Override via .env:
        LLM_MODEL=grok-3-mini          # cheaper/faster
        LLM_TEMPERATURE_STORY=0.9      # more creative
    """
    if not settings.XAI_API_KEY:
        raise ValueError("XAI_API_KEY is missing. Add it to your .env file.")

    return ChatOpenAI(
        api_key=settings.XAI_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=model_name or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE_STORY,
    )


# Curated list of high-quality premium pre-made ElevenLabs voices
ELEVENLABS_VOICES = {
    "Charlotte": "aRlmTYIQo6Tlg5SlulGC",   # Client Preferred soft/gentle (Female)
    "Sophia": "u8ADrbquiJqufR9XMtb8",      # Client Preferred Meditative Voice (Female)
    "Calen": "S44KQ3oLFckbxgyKfold",       # Resonant, Magnetic (Male)
    "Victoria": "WeAAwKYcS06VmXw086yZ",    # Warm and Calm French (Female)
    "Anja": "ytIo1w3M21piPjpR44FO",        # Cloned Female (Anja / Louise Porter)
    "Chapter1": "DGU073R3uvEaw6TvrL1r",    # Cloned Female (Chapter 1)
}
def parse_alignment_to_words(alignment: dict) -> list[dict]:
    """
    Parses character-level alignments from ElevenLabs response into word-level alignments.
    Returns list of dicts: [{'word': str, 'start': float, 'end': float}]
    """
    if not alignment:
        return []
    characters = alignment.get("characters", [])
    start_times = alignment.get("character_start_times_seconds", [])
    end_times = alignment.get("character_end_times_seconds", [])
    
    if not characters or not start_times or not end_times:
        return []
        
    words = []
    current_word = []
    word_start = None
    
    # Standard separators (excluding apostrophe to keep words like don't, let's intact)
    separators = {
        ' ', '\t', '\n', '\r', '.', ',', '!', '?', ';', ':', '-', '—', 
        '"', '“', '”', '‘', '’', '(', ')', '[', ']', '{', '}', '*', 
        '<', '>', '/', '\\', '_', '@', '#', '$', '%', '^', '&', '+'
    }
    
    for idx, char in enumerate(characters):
        if idx >= len(start_times) or idx >= len(end_times):
            break
            
        start = start_times[idx]
        end = end_times[idx]
        
        if char in separators:
            if current_word:
                words.append({
                    "word": "".join(current_word),
                    "start": word_start,
                    "end": end_times[idx - 1]
                })
                current_word = []
                word_start = None
        else:
            if not current_word:
                word_start = start
            current_word.append(char)
            
    if current_word:
        words.append({
            "word": "".join(current_word),
            "start": word_start,
            "end": end_times[min(len(end_times) - 1, len(characters) - 1)]
        })
        
    return words


def generate_voice_elevenlabs(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
    stability: float | None = None,
    similarity_boost: float | None = None,
    style: float | None = None,
    return_timestamps: bool = False,
) -> bytes | tuple[bytes, list[dict]]:
    """
    Generates audio from text using ElevenLabs API.
    Returns the generated audio as raw MP3 bytes (or a tuple of bytes and word alignment JSON if return_timestamps is True).

    All voice parameters are loaded from settings (config.py / .env) by default.
    If parameters are not provided, they are randomized slightly to provide unique variations.

    Requires ELEVENLABS_API_KEY in .env.
    """
    # Preprocess text to add breaks/pauses for a sensual, slow delivery
    import re
    # Strip markdown bold/italic tags so the TTS engine doesn't read them or glitch
    clean_text = text.replace("**", "").replace("*", "")
    
    # 1. Paragraph breaks (double newlines) -> 2.0s pause
    processed_text = re.sub(r'\n\s*\n', '\n\n<break time="2.0s" />\n\n', clean_text)
    # 2. Line breaks (single newline) -> 1.2s pause
    processed_text = re.sub(r'(?<!\n)\n(?!\n)', '\n<break time="1.2s" />\n', processed_text)
    # 3. Ellipses (...) -> 1.5s pause
    processed_text = re.sub(r'\.\.\.+', '... <break time="1.5s" />', processed_text)
    # 4. Sentence endings (period, question mark, exclamation mark followed by space and Capital Letter) -> 1.0s pause
    processed_text = re.sub(r'([.!?])\s+([A-Z])', r'\1 <break time="1.0s" /> \2', processed_text)

    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        # MOCK TTS: Return a tiny empty mp3 byte string so the job completes successfully during testing
        mock_audio = b"ID3\x04\x00\x00\x00\x00\x00\x00"
        if return_timestamps:
            words_list = processed_text.split()
            mock_alignment = []
            for i, w in enumerate(words_list):
                if "<break" in w or "time=" in w:
                    continue
                mock_alignment.append({
                    "word": w.strip(".,!?\"()"),
                    "start": round(i * 0.4, 2),
                    "end": round(i * 0.4 + 0.3, 2)
                })
            return mock_audio, mock_alignment
        return mock_audio

    # Resolve voice ID from name (e.g. "Sophia" -> "u8ADrbquiJqufR9XMtb8")
    resolved_voice_id = ELEVENLABS_VOICES.get(voice_id, voice_id) or settings.ELEVENLABS_VOICE_ID
    resolved_model_id = model_id or settings.ELEVENLABS_MODEL_ID

    # Generate or resolve random variations for voice settings if not explicitly specified
    import random
    resolved_stability = stability
    if resolved_stability is None:
        resolved_stability = round(random.uniform(0.40, 0.50), 2)

    resolved_similarity_boost = similarity_boost
    if resolved_similarity_boost is None:
        resolved_similarity_boost = round(random.uniform(0.75, 0.85), 2)

    resolved_style = style
    if resolved_style is None:
        resolved_style = round(random.uniform(0.60, 0.75), 2)

    if return_timestamps:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}/with-timestamps"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "xi-api-key": settings.ELEVENLABS_API_KEY,
        }
    else:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": settings.ELEVENLABS_API_KEY,
        }

    data = {
        "text": processed_text,
        "model_id": resolved_model_id,
        "voice_settings": {
            "stability": resolved_stability,
            "similarity_boost": resolved_similarity_boost,
            "style": resolved_style,
            "use_speaker_boost": True,
            "speed": 0.9,  # Slow down speech natively to allow emotional resonance
        },
    }

    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()

    if return_timestamps:
        import base64
        res_json = response.json()
        audio_bytes = base64.b64decode(res_json["audio_base64"])
        alignment = res_json.get("alignment", {})
        word_alignments = parse_alignment_to_words(alignment)
        return audio_bytes, word_alignments
    else:
        return response.content


# ---------------------------------------------------------------------------
# Audio Storage — S3 / Local Fallback
# ---------------------------------------------------------------------------

AUDIO_STORAGE_DIR = Path("media/audio")


def save_audio(audio_bytes: bytes, filename: str | None = None) -> str:
    """
    Attempts to save raw audio bytes to AWS S3. 
    If S3 is not configured or fails, it falls back to local media/audio/ directory.
    Returns the URL or relative path, e.g. "https://mybucket.s3..." or "media/audio/abc123.mp3".
    """
    from app.utils.s3 import upload_audio_bytes_to_s3
    
    s3_url = upload_audio_bytes_to_s3(audio_bytes)
    if s3_url:
        return s3_url

    # Fallback to local storage
    AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f"{uuid.uuid4()}.mp3"

    file_path = AUDIO_STORAGE_DIR / filename
    file_path.write_bytes(audio_bytes)

    return str(file_path)
