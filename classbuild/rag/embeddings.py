
from typing import Protocol
from functools import lru_cache
import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
DEVICE = "cpu"
BATCH_SIZE = 32

class EmbeddingError(Exception):
    """Base error for embedding operations."""


class EmbeddingInputError(EmbeddingError):
    """Raised when the embedding input is invalid."""


class EmbeddingModelUnavailableError(EmbeddingError):
    """Raised when the embedding model is unavailable."""


class EmbeddingResourceError(EmbeddingError):
    """Raised when embedding resources are insufficient."""


class InvalidEmbeddingError(EmbeddingError):
    """Raised when the generated embeddings are invalid."""

class TextEncoder(Protocol):
    def encode(self, sentences, **kwargs):
        ...
@lru_cache(maxsize=None)
def load_model(
    model_name: str = MODEL_NAME,
    device: str = DEVICE,
):
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=device)

    if model.get_embedding_dimension() != EMBEDDING_DIM:
        raise InvalidEmbeddingError(
            f"Expected embedding dimension {EMBEDDING_DIM}."
        )

    return model


def validate_embedding_matrix(
    matrix,
    expected_rows: int | None = None,
    dimension: int = EMBEDDING_DIM,
) -> np.ndarray:

    array = np.asarray(matrix, dtype=np.float32)

    if array.ndim != 2:
        raise InvalidEmbeddingError(
            "Embedding matrix must be 2-dimensional."
        )
    if expected_rows is not None and array.shape[0] != expected_rows:
        raise InvalidEmbeddingError(
            f"Expected {expected_rows} rows, got {array.shape[0]}."
        )
    if array.shape[1] != dimension:
        raise InvalidEmbeddingError(
            f"Expected embedding dimension {dimension}, got {array.shape[1]}."
        )
    if not np.isfinite(array).all():
        raise InvalidEmbeddingError(
            "Embedding matrix contains invalid values."
        )
    if np.any(np.linalg.norm(array, axis=1) == 0):
        raise InvalidEmbeddingError(
            "Embedding matrix contains zero vectors."
        )
    return array

class EmbeddingService:

    def __init__(self, model: TextEncoder | None = None):
        self.model = model or load_model()

    def embed_texts(
        self,
        texts: list[str],
    ) -> np.ndarray:
        if not texts or any(
            not isinstance(text, str) or not text.strip()
            for text in texts
        ):
            raise EmbeddingInputError(
                "Texts must be a non-empty list of non-empty strings."
            )
        batches = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start:start + BATCH_SIZE]
            try:
                vectors = self.model.encode(
                    batch,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
            except MemoryError as exc:
                raise EmbeddingResourceError(
                    "Not enough memory to generate embeddings."
                ) from exc
            except Exception as exc:
                raise EmbeddingModelUnavailableError(
                    "The embedding model could not generate embeddings."
                ) from exc
            batch_vectors = validate_embedding_matrix(
                vectors,
                expected_rows=len(batch),
            )
            batches.append(batch_vectors)
        result = np.vstack(batches)
        return validate_embedding_matrix(
            result,
            expected_rows=len(texts),
        )
    def embed_query(self, query: str) -> np.ndarray:
        embedding = self.embed_texts([query])
        return embedding[0]