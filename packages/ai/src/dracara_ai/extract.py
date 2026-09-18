"""Plain text out of an uploaded knowledge-base file.

Supports what an agency actually uploads: PDF, Word, plain text and Markdown. Anything else is
rejected by name rather than guessed at -- ``content_type`` arrives from the uploading client and
is not trustworthy (``app/services/storage.py`` makes the same point about why signed links force
a download).
"""

from __future__ import annotations

import io
import logging

from .errors import AiError

logger = logging.getLogger(__name__)

#: Extensions we can read. Checked against the filename, not the declared content type.
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".markdown", ".csv")


class UnsupportedDocumentError(AiError):
    """The file is stored, but its text cannot be extracted for indexing."""


def is_supported(filename: str) -> bool:
    return filename.lower().endswith(SUPPORTED_EXTENSIONS)


def extract_text(data: bytes, filename: str) -> str:
    """Return the document's text. Raises :class:`UnsupportedDocumentError` for anything else."""
    lowered = (filename or "").lower()

    if lowered.endswith(".pdf"):
        return _extract_pdf(data)
    if lowered.endswith(".docx"):
        return _extract_docx(data)
    if lowered.endswith((".txt", ".md", ".markdown", ".csv")):
        return data.decode("utf-8", errors="replace")

    raise UnsupportedDocumentError(
        f"Cannot extract text from {filename!r}; supported types are "
        + ", ".join(SUPPORTED_EXTENSIONS)
    )


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises a wide variety on malformed input
        raise UnsupportedDocumentError(f"Could not read this PDF: {exc}") from exc
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _extract_docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedDocumentError(f"Could not read this Word document: {exc}") from exc

    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    # Pricing sheets live in tables far more often than in paragraphs; skipping them would index
    # a document that looks empty.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)
