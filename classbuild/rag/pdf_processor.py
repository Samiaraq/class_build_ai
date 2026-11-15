import hashlib
import re 
import unicodedata
from io import BytesIO 

from pypdf import PdfReader

from classbuild.rag.chunker import (
    chunk_pages,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)
from classbuild.rag.models import ProcessedDocument

MAX_FILE_SIZE_MB=10
MAX_FILE_SIZE_BYTES=MAX_FILE_SIZE_MB*1024*1024

class PDFProcessingError(Exception):
    """base error for PDF processing"""
    def __init__(self, message):
        super().__init__(message)


class InvalidFileError(PDFProcessingError):
    """Raised when the uploaded file is not a valid PDF."""
class FileTooLargeError(PDFProcessingError):
    """Raised when the PDF exceeds the maximum allowed size."""
class EmptyFileError(PDFProcessingError):
    """Raised when the PDF exceeds the maximum allowed size."""
class CorruptedPDFError(PDFProcessingError):
    """Raised when the PDF file is corrupted."""
class EncryptedPDFError(PDFProcessingError):
    """Raised when the PDF file is encrypted."""
class NoExtractableTextError(PDFProcessingError):
    """Raised when no extractable text is found in the PDF."""


def fingerprint(data: bytes)-> str:
    """Return a SHA-256 fingerprint of the PDF bytes."""
    return hashlib.sha256(data).hexdigest()


def validate_pdf_upload(filename: str,data:bytes)-> None:
    """Validate the uploaded PDF file"""
    if not filename.lower().endswith(".pdf"):
        raise InvalidFileError("please upload a PDF file ")
    if not data:
        raise EmptyFileError("the uploaded file is empty")
    if len(data)> MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"the pdf file exceeds the {MAX_FILE_SIZE_MB}MB limit."

        )
    if b"%PDF-" not in data[:1024]:
        raise InvalidFileError("the uploaded file is not a valid PDF.")

def clean_text(text: str) -> str:
    """Clean extracted PDF text."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"(?m)(?<=\S)[ \t]{2,}", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)

    return text

def extract_pages(data: bytes) -> list[str]:
    """Extract and clean text from each PDF page."""

    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise CorruptedPDFError("The PDF file is corrupted.") from exc

    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise EncryptedPDFError("The PDF file is encrypted.")
        except EncryptedPDFError:
            raise
        except Exception as exc:
            raise EncryptedPDFError("The PDF file is encrypted.") from exc

    pages = []

    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
            pages.append(clean_text(page_text))
        except Exception:
            pages.append("")

    return pages
def process_pdf(
    filename: str,
    data: bytes,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> ProcessedDocument:
    validate_pdf_upload(filename, data)

    pages = extract_pages(data)

    if not any(page.strip() for page in pages):
        raise NoExtractableTextError(
            "No extractable text was found in the PDF."
        )

    chunks = chunk_pages(
        pages,
        source_filename=filename,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    empty_pages = [
        page_number
        for page_number, page in enumerate(pages, start=1)
        if not page.strip()
    ]

    full_text = "\n".join(pages)

    document = ProcessedDocument(
        filename=filename,
        fingerprint=fingerprint(data),
        page_count=len(pages),
        word_count=len(full_text.split()),
        char_count=len(full_text),
        empty_pages=empty_pages,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunks=chunks,
    )

    document.check_consistency()

    return document