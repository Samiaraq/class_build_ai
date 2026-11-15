
import numpy as np


KEYWORDS = [
    "python", "programming", "code", "software",
    "machine", "learning", "artificial", "intelligence",
    "model", "training", "prediction", "data",
    "neural", "network", "deep", "algorithm",
    "student", "teacher", "course", "lesson",
    "education", "study", "quiz", "knowledge",
    "science", "computer", "language", "text",
    "document", "search", "embedding", "retrieval",
    "database", "information", "analysis", "research",
]


class FakeEncoder:
    """A lightweight test encoder that counts fixed keywords."""

    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]

        self.calls.append(list(texts))

        vectors = np.zeros((len(texts), 384), dtype=np.float32)

        for row, text in enumerate(texts):
            words = text.lower().split()

            for index, keyword in enumerate(KEYWORDS):
                vectors[row, index] = words.count(keyword)

            # Keep unknown but non-empty text representable.
            if not np.any(vectors[row]) and text.strip():
                vectors[row, 383] = 1.0

        return vectors


class BrokenEncoder:
    """A test encoder that returns invalid output or raises an error."""

    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append(texts)

        if self.error is not None:
            raise self.error

        return self.output
