from dataclasses import dataclass

from classbuild.rag.document_state import (
    DOC_KEY,
    INDEX_KEY,
    SEARCH_KEY,
)
from classbuild.rag.embeddings import EmbeddingService, MODEL_NAME
from classbuild.rag.models import ProcessedDocument
from classbuild.rag.retriever import (
    DEFAULT_TOP_K,
    DocumentIndex,
    SearchResult,
    EmptyQueryError,
    NoDocumentError,
    build_index,
    search,
)
@dataclass(frozen=True)
class SearchOutcome:
    query: str
    results: list[SearchResult]
    index_built_now: bool


def has_current_index(
    state: dict,
    document: ProcessedDocument,
    service: EmbeddingService,
) -> bool:
    index = state.get(INDEX_KEY)

    if index is None:
        return False

    expected_chunk_ids = tuple(
        chunk.chunk_id for chunk in document.chunks
    )

    return (
        index.document_fingerprint == document.fingerprint
        and index.chunk_ids == expected_chunk_ids
        and index.model_name == MODEL_NAME
    )

def get_or_build_index(
    state: dict,
    document: ProcessedDocument,
    service: EmbeddingService,
) -> tuple[DocumentIndex, bool]:
    if has_current_index(state, document, service):
        return state[INDEX_KEY], False

    index = build_index(document, service)
    state[INDEX_KEY] = index

    return index, True

def run_search(
    state: dict,
    query: str,
    service: EmbeddingService | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> SearchOutcome:
    state.pop(SEARCH_KEY, None)

    document = state.get(DOC_KEY)

    if document is None:
        raise NoDocumentError("No document is available for search.")

    if not query or not query.strip():
        raise EmptyQueryError("Search query cannot be empty.")

    service = service or EmbeddingService()

    index, index_built_now = get_or_build_index(
        state,
        document,
        service,
    )

    results = search(
        index=index,
        document=document,
        query=query.strip(),
        service=service,
        top_k=top_k,
    )

    state[SEARCH_KEY] = {
        "fingerprint": document.fingerprint,
        "query": query.strip(),
        "results": results,
    }

    return SearchOutcome(
        query=query.strip(),
        results=results,
        index_built_now=index_built_now,
    )
def current_results(state: dict) -> list[SearchResult]:
    stored = state.get(SEARCH_KEY)

    if not stored:
        return []

    document = state.get(DOC_KEY)

    if document is None:
        return []

    if stored.get("fingerprint") != document.fingerprint:
        return []

    return stored.get("results", [])