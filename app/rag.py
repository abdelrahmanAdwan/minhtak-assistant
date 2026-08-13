"""Retrieval-augmented generation over the session's uploaded PDFs.

    ingest:   PDF bytes -> text -> overlapping chunks -> embeddings -> store
    retrieve: question  -> query embedding -> top-k by cosine similarity

Note what this module does NOT do: it does not generate the answer. The
retrieved passages are handed back to the agent as a TOOL RESULT, and the same
model that is running the conversation writes the reply. That keeps one voice,
one history, and one place where grounding rules are enforced -- instead of a
second, bolted-on RAG chatbot living beside the first.

Everything is per-session and in memory. Nothing about an uploaded CV is
written to disk or to a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import config
from .errors import DocumentUnreadable, UploadRejected
from .gemini import embed_texts
from .pdf import PdfError, chunk_text, extract_text_from_pdf
from .store import Retrieved, VectorStore


@dataclass
class DocumentCorpus:
    """One session's uploaded documents and their vectors."""

    store: VectorStore = field(
        default_factory=lambda: VectorStore(config.EMBEDDING_DIM))
    documents: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.store.size == 0

    def ingest(self, raw: bytes, filename: str) -> dict[str, Any]:
        """Add one PDF. Returns a summary; raises a typed error on refusal."""
        if len(self.documents) >= config.MAX_DOCS_PER_SESSION:
            raise UploadRejected(
                "document limit reached",
                user_message=(
                    f"يمكن رفع {config.MAX_DOCS_PER_SESSION} ملفات كحد أقصى في "
                    "المحادثة الواحدة. ابدأ محادثة جديدة لرفع المزيد."),
            )
        if len(raw) > config.MAX_UPLOAD_BYTES:
            raise UploadRejected(
                f"{len(raw)} bytes exceeds the cap",
                user_message=(
                    f"حجم الملف يتجاوز الحد المسموح "
                    f"({config.MAX_UPLOAD_BYTES // (1024 * 1024)} ميغابايت)."),
            )

        try:
            text = extract_text_from_pdf(raw, max_pages=config.MAX_PDF_PAGES)
        except PdfError as exc:
            raise DocumentUnreadable(str(exc)) from exc

        chunks = chunk_text(text)
        if not chunks:
            # A valid PDF with no text layer (a scan). Say so -- never index an
            # empty document and let the user wonder why answers are useless.
            raise DocumentUnreadable("no extractable text layer")

        room = config.MAX_CHUNKS_PER_SESSION - self.store.size
        if room <= 0:
            raise UploadRejected(
                "chunk budget exhausted",
                user_message="بلغت المحادثة حدّها من المحتوى المفهرس. ابدأ محادثة جديدة.",
            )
        truncated = len(chunks) > room
        chunks = chunks[:room]

        vectors = embed_texts(chunks, task_type="RETRIEVAL_DOCUMENT")
        self.store.add(chunks, vectors, source=filename)
        summary = {
            "filename": filename,
            "chunks": len(chunks),
            "truncated": truncated,
        }
        self.documents.append(summary)
        return summary

    def retrieve(self, query: str, k: int | None = None) -> list[Retrieved]:
        if self.is_empty or not query.strip():
            return []
        vector = embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
        return self.store.search(vector, k=k or config.RAG_TOP_K)

    def reset(self) -> None:
        self.store = VectorStore(config.EMBEDDING_DIM)
        self.documents = []
