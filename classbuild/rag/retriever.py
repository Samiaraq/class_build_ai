from dataclasses import dataclass, field
import numpy as np

from classbuild.rag.embeddings import (
    MODEL_NAME,
    EmbeddingService,
)
from classbuild.rag.models import ProcessedDocument

DEFAULT_TOP_K = 3

class RetrievalError(Exception):
    """Base error for document retrieval operations."""

class EmptyQueryError(RetrievalError):
    """Raised when the search query is empty."""


class NoDocumentError(RetrievalError):
    """Raised when no document is available for retrieval."""


class IndexMismatchError(RetrievalError):
    """Raised when the index does not match the document."""

@dataclass(frozen=True)
class DocumentIndex:
    document_fingerprint: str
    model_name: str
    chunk_ids: tuple[str, ...]
    embeddings: np.ndarray = field(repr=False)
    def __post_init__(self) -> None:
        embeddings = np.array(self.embeddings, dtype=np.float32, copy=True)
        embeddings.setflags(write=False)
        object.__setattr__(self, "embeddings", embeddings)
    @property
    def size(self) -> int:
        return len(self.chunk_ids)
    
@dataclass(frozen=True)
class SearchResult:
    rank: int
    chunk_id: str
    source_filename: str
    page_number: int
    chunk_index: int
    text: str
    score: float

def cosine_similarity(
    query: np.ndarray,
    matrix: np.ndarray,
) -> np.ndarray:
    query_norm = np.linalg.norm(query)
    matrix_norms = np.linalg.norm(matrix, axis=1)

    if query_norm == 0 or np.any(matrix_norms == 0):
        raise RetrievalError("Cannot calculate similarity for zero vectors.")

    similarities = np.dot(matrix, query) / (matrix_norms * query_norm)

    return similarities

def build_index(
    document: ProcessedDocument,
    service: EmbeddingService,
) -> DocumentIndex:
    if not document.chunks:
        raise NoDocumentError("Document has no chunks to index.")

    embeddings = service.embed_texts(
        [chunk.text for chunk in document.chunks]
    )

    return DocumentIndex(
        document_fingerprint=document.fingerprint,
        model_name=MODEL_NAME,
        chunk_ids=tuple(chunk.chunk_id for chunk in document.chunks),
        embeddings=embeddings,
    )

def check_index(
    index: DocumentIndex,
    document: ProcessedDocument,
) -> None:
    if index.document_fingerprint != document.fingerprint:
        raise IndexMismatchError(
            "The index belongs to a different document."
        )

    current_chunk_ids = tuple(
        chunk.chunk_id for chunk in document.chunks
    )

    if index.chunk_ids != current_chunk_ids:
        raise IndexMismatchError(
            "The document chunks do not match the index."
        )


def search(
    index: DocumentIndex,
    document: ProcessedDocument,
    query: str,
    service: EmbeddingService,
    top_k: int = DEFAULT_TOP_K,
) -> list[SearchResult]:

    if not query or not query.strip():
        raise EmptyQueryError("Search query cannot be empty.")

    if not document.chunks:
        raise NoDocumentError("Document has no chunks to search.")

    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    check_index(index, document)

    query_embedding = service.embed_query(query)
    scores = cosine_similarity(query_embedding, index.embeddings)

    best_indices = np.argsort(-scores, kind="stable")[:top_k]

    results = []

    for rank, chunk_position in enumerate(best_indices, start=1):
        chunk = document.chunks[chunk_position]

        results.append(
            SearchResult(
                rank=rank,
                chunk_id=chunk.chunk_id,
                source_filename=chunk.source_filename,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=float(scores[chunk_position]),
            )
        )

    return results