import io
import os
import re
import logging
import requests
from PIL import Image, ImageDraw, ImageFont
from app.core.config import settings
from app.utils.s3 import upload_image_to_s3

logger = logging.getLogger(__name__)

def draw_top_gradient(img: Image.Image, height: int, max_opacity: float = 0.75):
    """Draws a vertical dark gradient at the top of the image to ensure text legibility."""
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    for y in range(height):
        # Calculate opacity from max_opacity to 0
        ratio = 1.0 - (y / height)
        # Apply easing function ratio^1.5 for a smoother transition
        opacity = int(ratio**1.5 * max_opacity * 255)
        if opacity > 0:
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, opacity))

def wrap_text(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    """Wraps text into multiple lines so it fits within max_width."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            
    if current_line:
        lines.append(" ".join(current_line))
        
    return lines

def draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill_color: tuple[int, int, int] = (255, 255, 255),
    shadow_color: tuple[int, int, int, int] = (0, 0, 0, 180),
    shadow_offset: tuple[int, int] = (2, 2)
):
    """Draws text with a drop shadow behind it."""
    # Draw shadow
    shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
    draw.text(shadow_pos, text, font=font, fill=shadow_color)
    # Draw main text
    draw.text(position, text, font=font, fill=fill_color)

def compose_cover_image(
    raw_image_bytes: bytes,
    title: str,
    subtitle: str
) -> bytes:
    """
    Applies the podcast-style overlay to a raw background image using Pillow.
    - Draws a dark gradient at the top.
    - Draws the title in PlayfairDisplay-Bold.
    - Draws the subtitle (e.g. author name) in PlayfairDisplay-Italic.
    - Centered Spotify logo at the bottom.
    """
    img = Image.open(io.BytesIO(raw_image_bytes)).convert("RGBA")
    w, h = img.size
    
    # 1. Draw top gradient (disabled as requested)
    # draw_top_gradient(img, int(h * 0.35), max_opacity=0.75)
    
    draw = ImageDraw.Draw(img, "RGBA")
    
    # Load fonts (fallback to default if not present)
    font_bold_path = "public/fonts/PlayfairDisplay-Bold.ttf"
    font_italic_path = "public/fonts/PlayfairDisplay-Italic.ttf"
    
    if os.path.exists(font_bold_path):
        title_font = ImageFont.truetype(font_bold_path, size=72)
    else:
        title_font = ImageFont.load_default()
        
    if os.path.exists(font_italic_path):
        subtitle_font = ImageFont.truetype(font_italic_path, size=34)
    else:
        subtitle_font = ImageFont.load_default()
        
    # 2. Draw Title (wrapped and centered)
    max_text_width = int(w * 0.85) # 85% of image width
    wrapped_title = wrap_text(title, title_font, draw, max_text_width)
    
    title_y = 120 # Start 120px from top
    for line in wrapped_title:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        
        line_x = (w - line_w) // 2
        draw_text_with_shadow(draw, (line_x, title_y), line, font=title_font)
        title_y += line_h + 20
        
    # 3. Draw Subtitle (e.g., author name)
    subtitle_y = title_y + 10
    bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    sub_w = bbox[2] - bbox[0]
    sub_x = (w - sub_w) // 2
    draw_text_with_shadow(draw, (sub_x, subtitle_y), subtitle, font=subtitle_font, shadow_offset=(1, 1))
    
    # 4. Draw Spotify logo centered at the bottom
    logo_path = "public/fonts/Spotify_Primary_Logo_RGB_White.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_aspect = logo.height / logo.width
            logo_w = 180
            logo_h = int(logo_w * logo_aspect)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            
            logo_x = (w - logo_w) // 2
            logo_y = h - logo_h - 60
            img.paste(logo, (logo_x, logo_y), logo)
        except Exception as e:
            logger.error(f"Failed to paste Spotify logo overlay: {e}", exc_info=True)
            
    # Convert back to RGB bytes (JPEG)
    final_img = img.convert("RGB")
    out_io = io.BytesIO()
    final_img.save(out_io, format="JPEG", quality=90)
    return out_io.getvalue()

def prepend_cover_identity_lock(
    prompt: str,
    *,
    author_name: str,
    gender: str | None,
) -> str:
    """Prefix the DALL-E prompt with a short identity lock Grok cannot overwrite."""
    name = (author_name or "").strip() or "the author"
    gender_label = (gender or "").strip() or "person"
    lock = f"The person depicted MUST be {name}, a {gender_label}."
    stripped = (prompt or "").strip()
    if stripped.startswith("The person depicted MUST be "):
        return stripped
    return f"{lock} {stripped}".strip()


def _image_prompt_char_limit(model: str) -> int | None:
    """Max prompt characters the OpenAI Images model accepts, None if unbounded.

    gpt-image models accept very long prompts; dall-e-3 rejects >4,000 chars.
    """
    if model.lower().startswith("dall-e"):
        return 4000
    return None


def generate_ai_cover_image(
    title: str,
    story_type: str,
    author_name: str,
    image_prompt: str,
    gender: str | None = None,
    *,
    lock_identity: bool = True,
    size: str | None = None,
) -> tuple[str, str] | tuple[None, None]:
    """
    Calls DALL-E 3 (or configured image model) to generate the background image,
    and uploads the resulting image to S3 (or local fallback).
    Returns (image_url, s3_key) or (None, None) on failure.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not configured. Skipping DALL-E 3 cover generation.")
        return None, None
        
    # Clean/format parameters
    cleaned_title = title.strip() or "Untitled"
    cleaned_author = author_name.strip() or "Anonymous"
    
    # Build the display subtitle
    story_type_clean = story_type.lower()
    if "confession" in story_type_clean:
        subtitle = f"A confession by {cleaned_author}"
    elif "meditation" in story_type_clean:
        subtitle = f"A meditation by {cleaned_author}"
    else:
        subtitle = f"A journey by {cleaned_author}"

    if lock_identity:
        dalle_prompt = prepend_cover_identity_lock(
            image_prompt,
            author_name=cleaned_author,
            gender=gender,
        )
    else:
        dalle_prompt = image_prompt.strip()

    model = settings.OPENAI_IMAGE_MODEL or "dall-e-3"
    prompt_limit = _image_prompt_char_limit(model)
    if prompt_limit is not None and len(dalle_prompt) > prompt_limit:
        trimmed = dalle_prompt[: prompt_limit - 3].rsplit(" ", 1)[0].rstrip() + "..."
        logger.warning(
            "Image prompt %s chars exceeds %s limit %s — trimmed to %s chars "
            "(story-specific blocks sit at the front, boilerplate drops last)",
            len(dalle_prompt),
            model,
            prompt_limit,
            len(trimmed),
        )
        dalle_prompt = trimmed
        
    logger.info(f"Generating OpenAI background for '{cleaned_title}' using model {settings.OPENAI_IMAGE_MODEL}. Prompt: {dalle_prompt}")
    
    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        model = settings.OPENAI_IMAGE_MODEL or "dall-e-3"
        model_lower = model.lower().strip()
        if size is not None:
            target_size = size
        elif model_lower.startswith("dall-e-3"):
            target_size = "1024x1792"
        elif model_lower.startswith("dall-e-2"):
            target_size = "1024x1024"
        else:
            target_size = "1024x1536"

        payload = {
            "model": model,
            "prompt": dalle_prompt,
            "n": 1,
            "size": target_size
        }
        # Prefer natural (less glossy) for DALL·E 3 — matches TTL anti-AI look.
        if model_lower.startswith("dall-e"):
            payload["style"] = "natural"
        
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        if not resp.ok and resp.status_code == 400 and any(k in resp.text.lower() for k in ("moderation", "safety", "sexual")):
            logger.warning(
                "OpenAI image generation rejected by safety system (%s). Applying safety sanitization and retrying with safe editorial prompt...",
                resp.text[:200],
            )
            safe_prompt = re.sub(r"\b(?:kiss(?:ing|ed|es)?|almost-kiss|mouth-to-mouth)\b", "tender embrace", dalle_prompt, flags=re.I)
            safe_prompt = re.sub(r"\b(?:massag\w*|shoulders?\s+massage)\b", "gentle care", safe_prompt, flags=re.I)
            safe_prompt = re.sub(r"\b(?:sensual\w*|seduct\w*|erotic\w*|lust\w*|arous\w*|sexual\w*|provocative)\b", "magnetic", safe_prompt, flags=re.I)
            safe_prompt = re.sub(r"\b(?:bare\s+skin|bare\s+shoulders?|collarbones?|cleavage|undress\w*|naked|nude|lingerie|underwear|bikini|swimsuit|topless)\b", "tasteful attire", safe_prompt, flags=re.I)
            safe_prompt = re.sub(r"\b(?:bed(?:room)?|sheets|mattress)\b", "cozy terrace", safe_prompt, flags=re.I)
            safe_prompt = re.sub(r"\b(?:jawline\s+and\s+neck|neck\s+and\s+jawline|touching\s+(?:the\s+)?(?:neck|jawline))\b", "tender embrace", safe_prompt, flags=re.I)
            safe_prompt = re.sub(r"\b(?:ghb|cocaine|ecstasy|narcotics?)\b", "evening drink", safe_prompt, flags=re.I)
            safe_prompt = (
                "STRICT EDITORIAL SAFETY DIRECTIVE: Strictly safe, modest, fully clothed editorial lifestyle photograph. "
                "Natural eye contact, genuine warm smiles, stylish casual fashion, beautiful lighting, and serene outdoor atmosphere.\n\n"
                + safe_prompt
            )
            payload["prompt"] = safe_prompt
            resp = requests.post(url, json=payload, headers=headers, timeout=180)
            if resp.ok:
                logger.info("OpenAI image generation succeeded on sanitized safety retry.")

        if not resp.ok:
            error_detail = resp.text
            try:
                err_json = resp.json()
                if "error" in err_json:
                    err_obj = err_json["error"]
                    error_detail = (
                        f"[{err_obj.get('code', 'error')} / {err_obj.get('type', 'api_error')}]: "
                        f"{err_obj.get('message', resp.text)}"
                    )
            except Exception:
                pass
            logger.error(
                "OpenAI image generation rejected (HTTP %s): %s | Model: %s, Size: %s, Prompt chars: %s",
                resp.status_code,
                error_detail,
                model,
                size,
                len(payload.get("prompt", dalle_prompt)),
            )
        resp.raise_for_status()
        data = resp.json()
        
        image_data = data["data"][0]
        if "b64_json" in image_data:
            import base64
            logger.info("De-serializing base64 image data from OpenAI response.")
            raw_bytes = base64.b64decode(image_data["b64_json"])
        else:
            generated_url = image_data["url"]
            logger.info(f"Downloading generated image from: {generated_url}")
            img_resp = requests.get(generated_url, timeout=30)
            img_resp.raise_for_status()
            raw_bytes = img_resp.content
        
        # Apply Pillow overlay (disabled - using full AI image generation)
        # composed_bytes = compose_cover_image(raw_bytes, cleaned_title, subtitle)
        
        # Upload/save (S3 or local fallback handled inside upload_image_to_s3)
        final_url, s3_key = upload_image_to_s3(raw_bytes, file_extension="jpg")
        return final_url, s3_key
        
    except Exception as e:
        error_body = getattr(getattr(e, "response", None), "text", None)
        if error_body:
            logger.error(
                "Failed to generate and compose AI cover image: %s — Response body: %s",
                e,
                error_body,
                exc_info=True,
            )
        else:
            logger.error(f"Failed to generate and compose AI cover image: {e}", exc_info=True)
        return None, None
