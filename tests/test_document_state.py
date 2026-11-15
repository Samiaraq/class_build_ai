
import unittest
from unittest.mock import Mock

from classbuild.rag.document_state import (
    DOC_KEY,
    DOC_STATUS_KEY,
    COURSE_MATERIAL_KEY,
    INDEX_KEY,
    SEARCH_KEY,
    MaterialStatus,
    sync_learning_material,
    clear_learning_material,
    attach_material_to_course,
    material_for_course,
)
from classbuild.rag.pdf_processor import PDFProcessingError
from classbuild.rag.models import ProcessedDocument


class TestDocumentState(unittest.TestCase):

    def setUp(self):
        self.state = {}
        self.filename = "guide.pdf"
        self.data = b"%PDF-1.4 test content"

    def make_document(self, filename=None, data=None):
        filename = filename or self.filename
        data = data or self.data

        return ProcessedDocument(
            filename=filename,
            fingerprint=__import__(
                "hashlib"
            ).sha256(data).hexdigest(),
            page_count=1,
            word_count=3,
            char_count=20,
            empty_pages=[],
            chunk_size=800,
            chunk_overlap=150,
            chunks=[],
        )

    def test_processes_same_file_only_once(self):
        processor = Mock(return_value=self.make_document())

        first = sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=processor,
        )
        second = sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=processor,
        )

        self.assertTrue(first.processed_now)
        self.assertFalse(second.processed_now)
        self.assertIs(first.document, second.document)
        processor.assert_called_once_with(self.filename, self.data)

    def test_replaced_file_is_processed_again(self):
        first_document = self.make_document()
        second_data = b"%PDF-1.4 different content"
        second_document = self.make_document(data=second_data)

        processor = Mock(
            side_effect=[first_document, second_document]
        )

        sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=processor,
        )

        self.state[INDEX_KEY] = "old index"
        self.state[SEARCH_KEY] = "old results"

        result = sync_learning_material(
            self.state,
            (self.filename, second_data),
            processor=processor,
        )

        self.assertTrue(result.processed_now)
        self.assertIs(result.document, second_document)
        self.assertNotIn(INDEX_KEY, self.state)
        self.assertNotIn(SEARCH_KEY, self.state)
        self.assertEqual(processor.call_count, 2)

    def test_removed_file_clears_document_and_derived_state(self):
        document = self.make_document()

        sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=Mock(return_value=document),
        )

        self.state[INDEX_KEY] = "index"
        self.state[SEARCH_KEY] = "results"

        result = sync_learning_material(self.state, None)

        self.assertIsNone(result.document)
        self.assertIsNone(result.error)
        self.assertFalse(result.processed_now)

        self.assertNotIn(DOC_KEY, self.state)
        self.assertNotIn(DOC_STATUS_KEY, self.state)
        self.assertNotIn(INDEX_KEY, self.state)
        self.assertNotIn(SEARCH_KEY, self.state)

    def test_failed_file_error_is_reused(self):
        processor = Mock(
            side_effect=PDFProcessingError("Invalid PDF file.")
        )

        first = sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=processor,
        )
        second = sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=processor,
        )

        self.assertIsNone(first.document)
        self.assertEqual(first.error, "Invalid PDF file.")
        self.assertTrue(first.processed_now)

        self.assertIsNone(second.document)
        self.assertEqual(second.error, first.error)
        self.assertFalse(second.processed_now)

        processor.assert_called_once_with(self.filename, self.data)

    def test_unexpected_error_returns_generic_message(self):
        processor = Mock(
            side_effect=RuntimeError("Private internal details")
        )

        result = sync_learning_material(
            self.state,
            (self.filename, self.data),
            processor=processor,
        )

        self.assertIsNone(result.document)
        self.assertEqual(
            result.error,
            "An unexpected error occurred while processing the PDF.",
        )
        self.assertNotIn("Private internal details", result.error)
        self.assertTrue(result.processed_now)

    def test_clear_learning_material_removes_derived_state(self):
        self.state[DOC_KEY] = "document"
        self.state[DOC_STATUS_KEY] = "status"
        self.state[INDEX_KEY] = "index"
        self.state[SEARCH_KEY] = "results"
        self.state[COURSE_MATERIAL_KEY] = "course fingerprint"

        clear_learning_material(self.state)

        self.assertNotIn(DOC_KEY, self.state)
        self.assertNotIn(DOC_STATUS_KEY, self.state)
        self.assertNotIn(INDEX_KEY, self.state)
        self.assertNotIn(SEARCH_KEY, self.state)

        self.assertIn(COURSE_MATERIAL_KEY, self.state)

    def test_attach_material_to_course(self):
        document = self.make_document()
        self.state[DOC_KEY] = document

        attach_material_to_course(self.state)

        self.assertEqual(
            self.state[COURSE_MATERIAL_KEY],
            document.fingerprint,
        )

    def test_attach_course_without_document(self):
        attach_material_to_course(self.state)

        self.assertIsNone(
            self.state[COURSE_MATERIAL_KEY]
        )

    def test_material_for_course_returns_matching_document(self):
        document = self.make_document()
        self.state[DOC_KEY] = document
        self.state[COURSE_MATERIAL_KEY] = document.fingerprint

        result = material_for_course(self.state)

        self.assertIs(result, document)

    def test_material_for_course_rejects_different_pdf(self):
        document = self.make_document()
        self.state[DOC_KEY] = document
        self.state[COURSE_MATERIAL_KEY] = "different-fingerprint"

        self.assertIsNone(material_for_course(self.state))

    def test_material_for_course_without_document(self):
        self.state[COURSE_MATERIAL_KEY] = "some-fingerprint"

        self.assertIsNone(material_for_course(self.state))

    def test_material_for_course_without_course_link(self):
        self.state[DOC_KEY] = self.make_document()

        self.assertIsNone(material_for_course(self.state))


if __name__ == "__main__":
    unittest.main()
