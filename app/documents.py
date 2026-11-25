import hashlib
from io import BytesIO
from pypdf import PdfReader
from .errors import AppError

MAX_BYTES = 2 * 1024 * 1024


def read_document(name, content):
    """Preserve page provenance; fail explicitly when OCR is required."""
    if not content or len(content) > MAX_BYTES:
        raise AppError("file_size", "Upload a non-empty file no larger than 2 MB.")
    if name.lower().endswith(".pdf"):
        if not content.startswith(b"%PDF-"):
            raise AppError("file_type", "This file is not a valid PDF.")
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise AppError("encrypted_pdf", "Encrypted PDFs are unsupported.")
            if len(reader.pages) > 10:
                raise AppError("page_limit", "Upload a PDF with at most 10 pages.")
            pages = [{"page": i + 1, "text": page.extract_text() or ""} for i, page in enumerate(reader.pages)]
        except AppError:
            raise
        except Exception:
            raise AppError("pdf_invalid", "PDF parsing failed. Try a clean text PDF.")
    elif name.lower().endswith((".txt", ".md")):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AppError("file_encoding", "Text files must use UTF-8.")
        if "\x00" in text or text.lstrip().startswith(("%PDF-", "PK\x03\x04")):
            raise AppError("file_type", "Content is not plain text.")
        pages = [{"page": i + 1, "text": page} for i, page in enumerate(text.split("\f"))]
        if len(pages) > 10:
            raise AppError("page_limit", "Upload at most 10 pages.")
    else:
        raise AppError("file_type", "Use a text PDF, .txt, or .md file. Image OCR is planned.")
    if not pages or any(len(page["text"].strip()) < 10 for page in pages):
        raise AppError("ocr_required", "A page has too little text. Scanned documents need OCR, which is not included yet.")
    if sum(len(page["text"]) for page in pages) > 50000:
        raise AppError("text_limit", "Document exceeds 50,000 extracted characters.")
    return {"hash": hashlib.sha256(content).hexdigest(), "pages": pages}
