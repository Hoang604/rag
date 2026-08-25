"""Sliding-window text chunking with title context injection for documents."""

from dataclasses import dataclass

from rag_eval.schemas import Document


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """A sliced text chunk linked to its parent document."""

    chunk_id: str
    doc_id: str
    text: str
    start_char: int
    end_char: int


def chunk_text(
    text: str,
    doc_id: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    title: str | None = None,
) -> list[DocumentChunk]:
    """Split a single text into overlapping character chunks, injecting title prefix."""
    if chunk_size <= 0:
        msg = f"chunk_size must be positive, got {chunk_size}"
        raise ValueError(msg)
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        msg = f"chunk_overlap must be in range [0, chunk_size), got {chunk_overlap} for size {chunk_size}"
        raise ValueError(msg)

    text_len = len(text)
    if text_len == 0:
        return []

    title_prefix = f"{title}\n\n" if title else ""

    if text_len <= chunk_size:
        return [
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_0",
                doc_id=doc_id,
                text=f"{title_prefix}{text}",
                start_char=0,
                end_char=text_len,
            )
        ]

    chunks: list[DocumentChunk] = []
    step = chunk_size - chunk_overlap
    start = 0
    chunk_index = 0

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk_str = f"{title_prefix}{text[start:end]}"
        chunks.append(
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_{chunk_index}",
                doc_id=doc_id,
                text=chunk_str,
                start_char=start,
                end_char=end,
            )
        )
        chunk_index += 1
        if end == text_len:
            break
        start += step

    return chunks


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[DocumentChunk]:
    """Chunk all documents in a corpus into sliding-window text segments."""
    all_chunks: list[DocumentChunk] = []
    for doc in documents:
        doc_chunks = chunk_text(
            text=doc.text,
            doc_id=doc.id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            title=doc.title,
        )
        all_chunks.extend(doc_chunks)
    return all_chunks
