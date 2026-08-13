"""PDF text extraction + chunking for the RAG pipeline.

Step 1 (extract text) and step 2 (split into chunks) of the pipeline. pypdf
imports lazily so the rest of the package can be exercised without it.
"""

from __future__ import annotations

import io
import re


class PdfError(ValueError):
    """A PDF could not be read (corrupt, encrypted, or not a PDF). A valid PDF
    with no text layer (a scan) returns '' — the caller reports it, never
    silently indexes an empty document."""


def extract_text_from_pdf(raw: bytes, *, max_pages: int = 100) -> str:
    """Extract text from PDF bytes via pypdf (step 1)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise PdfError("pypdf is not installed (pip install pypdf).") from exc
    if not raw:
        raise PdfError("empty upload — no PDF bytes.")
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise PdfError("the PDF is password-protected.")
            except PdfError:
                raise
            except Exception:  # noqa: BLE001
                raise PdfError("the PDF is password-protected.")
        text = "\n".join(
            (page.extract_text() or "") for page in reader.pages[:max_pages])
    except PdfError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"unreadable PDF: {exc}") from exc
    return text


def chunk_text(
    text: str, *, target_chars: int = 900, overlap_chars: int = 150
) -> list[str]:
    """Split text into overlapping, word-aligned chunks (step 2).

    A sliding window with overlap keeps a fact that straddles a boundary
    retrievable from at least one chunk. Blank input -> [] (no empty chunks are
    ever embedded).
    """
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= target_chars:
        return [cleaned]

    overlap = max(0, min(overlap_chars, target_chars // 2))
    step = target_chars - overlap
    n = len(cleaned)
    chunks: list[str] = []
    start = 0
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            space = cleaned.rfind(" ", start, end)
            if space > start + step // 2:
                end = space
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
