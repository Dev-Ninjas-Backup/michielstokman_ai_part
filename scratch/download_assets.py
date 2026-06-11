import os
import requests
import zipfile
import io

def download_spotify_logo():
    url = "https://storage.googleapis.com/pr-newsroom-wp/1/2023/05/Spotify_Primary_Logo_RGB_White.png"
    dest = "public/fonts/Spotify_Primary_Logo_RGB_White.png"
    print(f"Downloading {url} -> {dest}...")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        f.write(resp.content)
    print("Downloaded Spotify logo.")

def download_and_extract_fonts():
    url = "https://gwfh.mranftl.com/api/fonts/playfair-display?download=zip&subsets=latin&variants=regular,700,italic,700italic&formats=ttf"
    print(f"Downloading fonts from {url}...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    
    os.makedirs("public/fonts", exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        for file_info in z.infolist():
            filename = file_info.filename
            print(f"Found file in zip: {filename}")
            if filename.endswith("-700.ttf"):
                with open("public/fonts/PlayfairDisplay-Bold.ttf", "wb") as f:
                    f.write(z.read(file_info))
                print("Extracted PlayfairDisplay-Bold.ttf")
            elif filename.endswith("-italic.ttf"):
                with open("public/fonts/PlayfairDisplay-Italic.ttf", "wb") as f:
                    f.write(z.read(file_info))
                print("Extracted PlayfairDisplay-Italic.ttf")
            elif filename.endswith("-regular.ttf"):
                with open("public/fonts/PlayfairDisplay-Regular.ttf", "wb") as f:
                    f.write(z.read(file_info))
                print("Extracted PlayfairDisplay-Regular.ttf")

def main():
    try:
        download_spotify_logo()
    except Exception as e:
        print(f"Failed to download Spotify logo: {e}")
        
    try:
        download_and_extract_fonts()
    except Exception as e:
        print(f"Failed to download/extract fonts: {e}")

if __name__ == "__main__":
    main()
