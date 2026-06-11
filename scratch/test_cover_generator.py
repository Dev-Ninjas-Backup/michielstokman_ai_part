import os
from PIL import Image
from app.utils.image_generator import compose_cover_image

def main():
    print("Testing Pillow cover composition locally...")
    
    # Create a solid color background (1024x1792 portrait)
    # We will use a warm golden brown color as a mock DALL-E background
    w, h = 1024, 1792
    raw_img = Image.new("RGB", (w, h), color=(180, 140, 100))
    
    # Save raw image bytes
    import io
    raw_io = io.BytesIO()
    raw_img.save(raw_io, format="JPEG")
    raw_bytes = raw_io.getvalue()
    
    title = "The Night She Took The Lead"
    subtitle = "A confession by Lars"
    
    try:
        # Run composition
        composed_bytes = compose_cover_image(raw_bytes, title, subtitle)
        
        # Save output
        os.makedirs("scratch", exist_ok=True)
        dest_path = "scratch/test_composed_cover.jpg"
        with open(dest_path, "wb") as f:
            f.write(composed_bytes)
        print(f"Success! Composed image saved to: {dest_path}")
        
    except Exception as e:
        print(f"Error during composition: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
