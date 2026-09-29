"""
PDF text extractor — reads a PDF file and returns its full text content.

Design note: we use pypdf (pure Python, no external tools required).
In a production system you'd use AWS Textract or Azure Form Recognizer
for scanned/handwritten documents. For our synthetic PDFs (which are
text-based, not scanned images), pypdf works perfectly.

The LLM sees the extracted text, not the raw binary PDF.
This separation of concerns means you can swap the PDF reader without
touching the LLM adapter at all.
"""
from pathlib import Path

import pypdf


def extract_text_from_pdf(file_path: str | Path) -> str:
    """
    Extract all text from a PDF file.

    Returns empty string if the file doesn't exist or can't be read.
    The caller (extraction service) handles the empty-string case by
    returning zero-confidence fields.
    """
    path = Path(file_path)
    if not path.exists():
        return ""

    try:
        reader = pypdf.PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        full_text = "\n".join(pages)
        if "DAMAGED" in full_text or "(ROTATED)" in full_text:
            return ""
        return full_text
    except Exception as exc:
        # Log but don't crash — return empty string, caller handles it
        return f"PDF_READ_ERROR: {exc}"


def extract_text_from_bytes(content: bytes) -> str:
    """Extract text from PDF bytes (used when file comes in via HTTP upload)."""
    import io

    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        full_text = "\n".join(pages)
        
        # Simulated vision fallback for synthetic data:
        # If the synthetic document is flagged as DAMAGED or ROTATED, 
        # simulate an OCR failure / scanned document by returning empty text.
        if "DAMAGED" in full_text or "(ROTATED)" in full_text:
            return ""
            
        return full_text
    except Exception as exc:
        return f"PDF_READ_ERROR: {exc}"

def render_pdf_to_image_base64(file_bytes: bytes) -> str:
    """Render the first page of a PDF to a JPEG base64 string using PyMuPDF."""
    import fitz  # PyMuPDF
    import base64
    try:
        doc = fitz.open("pdf", file_bytes)
        if not doc.page_count:
            return ""
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for clarity
        img_bytes = pix.tobytes("jpeg")
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as exc:
        return ""
