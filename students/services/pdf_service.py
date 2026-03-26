from pathlib import Path

import fitz  # PyMuPDF
from docx import Document


def extract_text_from_pdf(path: str) -> str:
    doc = fitz.open(path)
    parts = []

    for page in doc:
        parts.append(page.get_text("text"))

    doc.close()
    return "\n".join(parts).strip()


def extract_text_from_docx(path: str) -> str:
    doc = Document(path)
    parts = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    return "\n".join(parts).strip()


def extract_text_from_file(path: str) -> str:
    ext = Path(path).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(path)

    if ext == ".docx":
        return extract_text_from_docx(path)

    raise ValueError(f"Қолдау жоқ файл форматы: {ext}")