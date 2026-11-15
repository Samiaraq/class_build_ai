
import unittest
import numpy as np

from classbuild.rag.embeddings import (
    MODEL_NAME,
    EMBEDDING_DIM,
    BATCH_SIZE,
    EmbeddingService,
    EmbeddingInputError,
    EmbeddingModelUnavailableError,
    EmbeddingResourceError,
    InvalidEmbeddingError,
    validate_embedding_matrix,
)

from classbuild.rag.retriever import (
    DEFAULT_TOP_K,
    RetrievalError,
    EmptyQueryError,
    NoDocumentError,
    IndexMismatchError,
    DocumentIndex,
    SearchResult,
    cosine_similarity,
    build_index,
    check_index,
    search,
)

from classbuild.rag.search_state import (
    SearchOutcome,
    has_current_index,
    get_or_build_index,
    run_search,
    current_results,
)

from classbuild.rag.document_state import (
    DOC_KEY,
    INDEX_KEY,
    SEARCH_KEY,
)

from classbuild.rag.models import (
    DocumentChunk,
    ProcessedDocument,
)

from tests.embedding_fakes import FakeEncoder, BrokenEncoder


def make_document(
    texts=None,
    fingerprint="document-fingerprint",
):
    if texts is None:
        texts = [
            "Python programming language",
            "Machine learning model",
            "Artificial intelligence data",
        ]

    chunks = [
        DocumentChunk(
            chunk_id=f"p1-c{index}",
            source_filename="guide.pdf",
            page_number=1,
            chunk_index=index,
            text=text,
        )
        for index, text in enumerate(texts, start=1)
    ]

    return ProcessedDocument(
        filename="guide.pdf",
        fingerprint=fingerprint,
        page_count=1,
        word_count=sum(len(text.split()) for text in texts),
        char_count=sum(len(text) for text in texts),
        empty_pages=[],
        chunk_size=800,
        chunk_overlap=150,
        chunks=chunks,
    )


class TestEmbeddingValidation(unittest.TestCase):

    def test_valid_embedding_matrix(self):
        matrix = np.ones((2, EMBEDDING_DIM))

        result = validate_embedding_matrix(
            matrix,
            expected_rows=2,
        )

        self.assertEqual(result.shape, (2, EMBEDDING_DIM))
        self.assertEqual(result.dtype, np.float32)

    def test_rejects_one_dimensional_matrix(self):
        with self.assertRaises(InvalidEmbeddingError):
            validate_embedding_matrix(np.ones(384))

    def test_rejects_wrong_row_count(self):
        with self.assertRaises(InvalidEmbeddingError):
            validate_embedding_matrix(
                np.ones((2, 384)),
                expected_rows=3,
            )

    def test_rejects_wrong_dimension(self):
        with self.assertRaises(InvalidEmbeddingError):
            validate_embedding_matrix(np.ones((2, 100)))

    def test_rejects_nan_values(self):
        matrix = np.ones((2, 384))
        matrix[0, 0] = np.nan

        with self.assertRaises(InvalidEmbeddingError):
            validate_embedding_matrix(matrix)

    def test_rejects_infinite_values(self):
        matrix = np.ones((2, 384))
        matrix[0, 0] = np.inf

        with self.assertRaises(InvalidEmbeddingError):
            validate_embedding_matrix(matrix)

    def test_rejects_zero_vectors(self):
        matrix = np.zeros((2, 384))

        with self.assertRaises(InvalidEmbeddingError):
            validate_embedding_matrix(matrix)


class TestEmbeddingService(unittest.TestCase):

    def setUp(self):
        self.encoder = FakeEncoder()
        self.service = EmbeddingService(model=self.encoder)

    def test_embeds_multiple_texts(self):
        texts = [
            "Python programming",
            "Machine learning",
        ]

        result = self.service.embed_texts(texts)

        self.assertEqual(result.shape, (2, EMBEDDING_DIM))
        self.assertEqual(result.dtype, np.float32)

    def test_embeds_single_query(self):
        result = self.service.embed_query("Python programming")

        self.assertEqual(result.shape, (EMBEDDING_DIM,))
        self.assertGreater(np.linalg.norm(result), 0)

    def test_rejects_empty_list(self):
        with self.assertRaises(EmbeddingInputError):
            self.service.embed_texts([])

    def test_rejects_empty_string(self):
        with self.assertRaises(EmbeddingInputError):
            self.service.embed_texts([""])

    def test_rejects_whitespace_text(self):
        with self.assertRaises(EmbeddingInputError):
            self.service.embed_texts(["   "])

    def test_rejects_non_string_input(self):
        with self.assertRaises(EmbeddingInputError):
            self.service.embed_texts(["Python", 123])

    def test_batches_large_input(self):
        texts = [
            f"Python programming {index}"
            for index in range(BATCH_SIZE + 1)
        ]

        result = self.service.embed_texts(texts)

        self.assertEqual(
            result.shape,
            (BATCH_SIZE + 1, EMBEDDING_DIM),
        )
        self.assertEqual(len(self.encoder.calls), 2)
        self.assertEqual(len(self.encoder.calls[0]), BATCH_SIZE)
        self.assertEqual(len(self.encoder.calls[1]), 1)

    def test_model_error_is_wrapped(self):
        encoder = BrokenEncoder(
            error=RuntimeError("Model failure")
        )
        service = EmbeddingService(model=encoder)

        with self.assertRaises(EmbeddingModelUnavailableError):
            service.embed_texts(["Python"])

    def test_memory_error_is_wrapped(self):
        encoder = BrokenEncoder(error=MemoryError())
        service = EmbeddingService(model=encoder)

        with self.assertRaises(EmbeddingResourceError):
            service.embed_texts(["Python"])

    def test_invalid_model_output_is_rejected(self):
        encoder = BrokenEncoder(
            output=np.zeros((1, EMBEDDING_DIM))
        )
        service = EmbeddingService(model=encoder)

        with self.assertRaises(InvalidEmbeddingError):
            service.embed_texts(["Python"])


class TestDocumentIndex(unittest.TestCase):

    def test_index_is_created(self):
        embeddings = np.ones((2, EMBEDDING_DIM))

        index = DocumentIndex(
            document_fingerprint="abc",
            model_name=MODEL_NAME,
            chunk_ids=("p1-c1", "p1-c2"),
            embeddings=embeddings,
        )

        self.assertEqual(index.size, 2)
        self.assertEqual(index.embeddings.shape, (2, EMBEDDING_DIM))

    def test_index_embeddings_are_read_only(self):
        index = DocumentIndex(
            document_fingerprint="abc",
            model_name=MODEL_NAME,
            chunk_ids=("p1-c1",),
            embeddings=np.ones((1, EMBEDDING_DIM)),
        )

        self.assertFalse(index.embeddings.flags.writeable)

        with self.assertRaises(ValueError):
            index.embeddings[0, 0] = 10

    def test_index_uses_copy_of_embeddings(self):
        original = np.ones((1, EMBEDDING_DIM))

        index = DocumentIndex(
            document_fingerprint="abc",
            model_name=MODEL_NAME,
            chunk_ids=("p1-c1",),
            embeddings=original,
        )

        original[0, 0] = 99

        self.assertNotEqual(index.embeddings[0, 0], 99)


class TestCosineSimilarity(unittest.TestCase):

    def test_identical_vectors(self):
        query = np.array([1.0, 0.0])
        matrix = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
        ])

        result = cosine_similarity(query, matrix)

        np.testing.assert_allclose(
            result,
            np.array([1.0, 0.0]),
        )

    def test_opposite_vectors(self):
        query = np.array([1.0, 0.0])
        matrix = np.array([
            [-1.0, 0.0],
        ])

        result = cosine_similarity(query, matrix)

        np.testing.assert_allclose(result, [-1.0])

    def test_rejects_zero_query_vector(self):
        with self.assertRaises(RetrievalError):
            cosine_similarity(
                np.zeros(2),
                np.ones((2, 2)),
            )

    def test_rejects_zero_matrix_vector(self):
        with self.assertRaises(RetrievalError):
            cosine_similarity(
                np.ones(2),
                np.array([
                    [1.0, 0.0],
                    [0.0, 0.0],
                ]),
            )


class TestBuildIndex(unittest.TestCase):

    def setUp(self):
        self.document = make_document()
        self.service = EmbeddingService(model=FakeEncoder())

    def test_builds_index_from_document_chunks(self):
        index = build_index(self.document, self.service)

        self.assertEqual(
            index.document_fingerprint,
            self.document.fingerprint,
        )
        self.assertEqual(
            index.model_name,
            MODEL_NAME,
        )
        self.assertEqual(
            index.chunk_ids,
            tuple(chunk.chunk_id for chunk in self.document.chunks),
        )
        self.assertEqual(index.size, len(self.document.chunks))

    def test_rejects_document_without_chunks(self):
        document = make_document(texts=[])

        with self.assertRaises(NoDocumentError):
            build_index(document, self.service)


class TestCheckIndex(unittest.TestCase):

    def setUp(self):
        self.document = make_document()
        self.service = EmbeddingService(model=FakeEncoder())
        self.index = build_index(self.document, self.service)

    def test_accepts_matching_index(self):
        result = check_index(self.index, self.document)

        self.assertIsNone(result)

    def test_rejects_different_fingerprint(self):
        different_document = make_document(
            fingerprint="different-fingerprint"
        )

        with self.assertRaises(IndexMismatchError):
            check_index(self.index, different_document)

    def test_rejects_different_chunk_ids(self):
        different_document = make_document(
            texts=[
                "Python programming language",
                "Machine learning model",
                "Artificial intelligence data",
                "Extra document chunk",
            ],
        )

        with self.assertRaises(IndexMismatchError):
            check_index(self.index, different_document)
class TestSearch(unittest.TestCase):

    def setUp(self):
        self.document = make_document()
        self.service = EmbeddingService(model=FakeEncoder())
        self.index = build_index(self.document, self.service)

    def test_returns_ranked_results(self):
        results = search(
            self.index,
            self.document,
            "Python programming",
            self.service,
        )

        self.assertTrue(results)
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(
            results[0].chunk_id,
            "p1-c1",
        )
        self.assertGreaterEqual(
            results[0].score,
            results[-1].score,
        )

    def test_respects_top_k(self):
        results = search(
            self.index,
            self.document,
            "Python programming",
            self.service,
            top_k=2,
        )

        self.assertEqual(len(results), 2)

    def test_returns_all_results_when_top_k_is_large(self):
        results = search(
            self.index,
            self.document,
            "Python programming",
            self.service,
            top_k=100,
        )

        self.assertEqual(
            len(results),
            len(self.document.chunks),
        )

    def test_result_contains_chunk_metadata(self):
        results = search(
            self.index,
            self.document,
            "Python programming",
            self.service,
            top_k=1,
        )

        result = results[0]
        chunk = self.document.chunks[0]

        self.assertIsInstance(result, SearchResult)
        self.assertEqual(result.source_filename, chunk.source_filename)
        self.assertEqual(result.page_number, chunk.page_number)
        self.assertEqual(result.chunk_index, chunk.chunk_index)
        self.assertEqual(result.text, chunk.text)

    def test_rejects_empty_query(self):
        with self.assertRaises(EmptyQueryError):
            search(self.index, self.document, "", self.service)

    def test_rejects_whitespace_query(self):
        with self.assertRaises(EmptyQueryError):
            search(self.index, self.document, "   ", self.service)

    def test_rejects_document_without_chunks(self):
        document = make_document(texts=[])
        index = DocumentIndex(
            document_fingerprint=document.fingerprint,
            model_name=MODEL_NAME,
            chunk_ids=(),
            embeddings=np.empty((0, EMBEDDING_DIM)),
        )

        with self.assertRaises(NoDocumentError):
            search(index, document, "Python", self.service)

    def test_rejects_non_positive_top_k(self):
        with self.assertRaises(ValueError):
            search(
                self.index,
                self.document,
                "Python",
                self.service,
                top_k=0,
            )

    def test_equal_scores_keep_document_order(self):
        document = make_document(
            texts=[
                "Python programming",
                "Python programming",
                "Machine learning",
            ]
        )
        service = EmbeddingService(model=FakeEncoder())
        index = build_index(document, service)

        results = search(
            index,
            document,
            "Python programming",
            service,
            top_k=3,
        )

        self.assertEqual(
            [result.chunk_id for result in results[:2]],
            ["p1-c1", "p1-c2"],
        )


class TestSearchState(unittest.TestCase):

    def setUp(self):
        self.document = make_document()
        self.service = EmbeddingService(model=FakeEncoder())
        self.state = {
            DOC_KEY: self.document,
        }

    def test_has_current_index_without_index(self):
        self.assertFalse(
            has_current_index(
                self.state,
                self.document,
                self.service,
            )
        )

    def test_builds_index_once(self):
        first_index, first_built = get_or_build_index(
            self.state,
            self.document,
            self.service,
        )

        second_index, second_built = get_or_build_index(
            self.state,
            self.document,
            self.service,
        )

        self.assertTrue(first_built)
        self.assertFalse(second_built)
        self.assertIs(first_index, second_index)

    def test_detects_index_for_different_document(self):
        get_or_build_index(
            self.state,
            self.document,
            self.service,
        )

        different_document = make_document(
            fingerprint="another-document",
        )

        self.assertFalse(
            has_current_index(
                self.state,
                different_document,
                self.service,
            )
        )

    def test_rebuilds_index_for_different_document(self):
        first_index, _ = get_or_build_index(
            self.state,
            self.document,
            self.service,
        )

        different_document = make_document(
            fingerprint="another-document",
        )

        second_index, built_now = get_or_build_index(
            self.state,
            different_document,
            self.service,
        )

        self.assertTrue(built_now)
        self.assertIsNot(first_index, second_index)
        self.assertEqual(
            second_index.document_fingerprint,
            different_document.fingerprint,
        )

    def test_run_search_builds_and_stores_results(self):
        outcome = run_search(
            self.state,
            "Python programming",
            service=self.service,
        )

        self.assertIsInstance(outcome, SearchOutcome)
        self.assertTrue(outcome.index_built_now)
        self.assertEqual(outcome.query, "Python programming")
        self.assertTrue(outcome.results)
        self.assertIn(SEARCH_KEY, self.state)

    def test_run_search_reuses_existing_index(self):
        first = run_search(
            self.state,
            "Python programming",
            service=self.service,
        )

        second = run_search(
            self.state,
            "Machine learning",
            service=self.service,
        )

        self.assertTrue(first.index_built_now)
        self.assertFalse(second.index_built_now)

    def test_run_search_strips_query(self):
        outcome = run_search(
            self.state,
            "  Python programming  ",
            service=self.service,
        )

        self.assertEqual(outcome.query, "Python programming")
        self.assertEqual(
            self.state[SEARCH_KEY]["query"],
            "Python programming",
        )

    def test_run_search_clears_old_results_without_document(self):
        self.state.pop(DOC_KEY)
        self.state[SEARCH_KEY] = {"results": ["old"]}

        with self.assertRaises(NoDocumentError):
            run_search(
                self.state,
                "Python",
                service=self.service,
            )

        self.assertNotIn(SEARCH_KEY, self.state)

    def test_run_search_clears_old_results_for_empty_query(self):
        self.state[SEARCH_KEY] = {"results": ["old"]}

        with self.assertRaises(EmptyQueryError):
            run_search(
                self.state,
                "   ",
                service=self.service,
            )

        self.assertNotIn(SEARCH_KEY, self.state)

    def test_current_results_returns_stored_results(self):
        outcome = run_search(
            self.state,
            "Python programming",
            service=self.service,
        )

        self.assertEqual(
            current_results(self.state),
            outcome.results,
        )

    def test_current_results_rejects_different_document(self):
        run_search(
            self.state,
            "Python programming",
            service=self.service,
        )

        self.state[DOC_KEY] = make_document(
            fingerprint="different-document",
        )

        self.assertEqual(current_results(self.state), [])

    def test_current_results_without_document(self):
        self.state[SEARCH_KEY] = {
            "fingerprint": self.document.fingerprint,
            "results": ["old"],
        }
        self.state.pop(DOC_KEY)

        self.assertEqual(current_results(self.state), [])

    def test_current_results_without_search(self):
        self.assertEqual(current_results(self.state), [])


if __name__ == "__main__":
    unittest.main()
