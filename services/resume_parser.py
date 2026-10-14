from PyPDF2 import PdfReader


def extract_text_from_pdf(source):
    """Extract selectable text from a PDF path or binary file-like object."""
    reader = PdfReader(source, strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
