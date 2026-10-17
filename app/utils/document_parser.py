import io
import os
import re
from typing import Optional


def extract_text_from_file(raw_bytes: bytes, filename: str) -> str:
    """
    Extracts readable plain text from uploaded file bytes.
    Supported extensions: .txt, .md, .docx, .pdf
    """
    ext = os.path.splitext(filename.lower())[1]

    if ext in [".txt", ".md"]:
        return _extract_from_text(raw_bytes)
    elif ext == ".docx":
        return _extract_from_docx(raw_bytes)
    elif ext == ".pdf":
        return _extract_from_pdf(raw_bytes)
    else:
        raise ValueError(
            f"Unsupported file format '{ext}'. Supported formats: .docx, .pdf, .txt, .md"
        )


def _extract_from_text(raw_bytes: bytes) -> str:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1", errors="replace")
    return _normalize_extracted_text(text)


def _extract_from_docx(raw_bytes: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(raw_bytes))
    paragraphs = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            paragraphs.append(t)
    return _normalize_extracted_text("\n\n".join(paragraphs))


def _extract_from_pdf(raw_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_bytes))
    pages_text = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted and extracted.strip():
            pages_text.append(extracted.strip())
    return _normalize_extracted_text("\n\n".join(pages_text))


def _normalize_extracted_text(text: str) -> str:
    if not text:
        return ""
    # Replace non-breaking spaces and carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    # Replace 3 or more consecutive newlines with 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
