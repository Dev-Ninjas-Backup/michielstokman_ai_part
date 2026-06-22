import re
from pypdf import PdfReader

def main():
    reader = PdfReader("FILES/lots of Meditations transform to liberation.pdf")
    print(f"Total pages: {len(reader.pages)}")
    
    text_content = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text(extraction_mode="layout")
        text_content.append((i + 1, text))
    
    # Write full text to a scratch file for easier reading
    with open("scratch/meditations_full_text.txt", "w", encoding="utf-8") as f:
        for pg_num, text in text_content:
            f.write(f"--- PAGE {pg_num} ---\n")
            f.write(text)
            f.write("\n\n")
            
    print("Full text written to scratch/meditations_full_text.txt")
    
    # Try finding titles
    print("\n--- Finding titles/headers ---")
    full_text = "\n".join([text for _, text in text_content])
    
    # Find occurrences of "Title:" or "Guided Meditation:"
    titles = re.findall(r"(?:Title:|Guided Meditation:)\s*(.*)", full_text, re.IGNORECASE)
    for idx, title in enumerate(titles):
        print(f"{idx+1}. {title.strip()}")

if __name__ == "__main__":
    main()
