import io
import os
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

def generate_ai_cover_image(
    title: str,
    story_type: str,
    author_name: str,
    image_prompt: str
) -> tuple[str, str] | tuple[None, None]:
    """
    Calls DALL-E 3 to generate the background image, applies the Pillow overlay,
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
        
    logger.info(f"Generating OpenAI background for '{cleaned_title}' using model {settings.OPENAI_IMAGE_MODEL}. Prompt: {image_prompt}")
    
    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        model = settings.OPENAI_IMAGE_MODEL or "dall-e-3"
        size = "1024x1792" if model.startswith("dall-e") else "1024x1536"
        
        payload = {
            "model": model,
            "prompt": image_prompt,
            "n": 1,
            "size": size
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
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
        logger.error(f"Failed to generate and compose AI cover image: {e}", exc_info=True)
        return None, None
