
import hashlib
import unittest
from unittest.mock import patch

from classbuild.rag.pdf_processor import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    PDFProcessingError,
    InvalidFileError,
    FileTooLargeError,
    EmptyFileError,
    CorruptedPDFError,
    EncryptedPDFError,
    NoExtractableTextError,
    fingerprint,
    validate_pdf_upload,
    clean_text,
    extract_pages,
    process_pdf,
)

from tests.pdf_fixtures import make_pdf, make_encrypted_pdf


class TestFingerprint(unittest.TestCase):

    def test_returns_sha256_hash(self):
        data = b"sample PDF content"
        expected = hashlib.sha256(data).hexdigest()

        self.assertEqual(fingerprint(data), expected)

    def test_different_content_has_different_fingerprint(self):
        self.assertNotEqual(
            fingerprint(b"first"),
            fingerprint(b"second"),
        )


class TestValidatePDFUpload(unittest.TestCase):

    def test_accepts_valid_pdf(self):
        data = make_pdf(["Python programming"])

        validate_pdf_upload("guide.pdf", data)

    def test_accepts_uppercase_extension(self):
        data = make_pdf(["Python programming"])

        validate_pdf_upload("GUIDE.PDF", data)

    def test_rejects_wrong_extension(self):
        with self.assertRaises(InvalidFileError):
            validate_pdf_upload("guide.docx", make_pdf(["Text"]))

    def test_rejects_empty_file(self):
        with self.assertRaises(EmptyFileError):
            validate_pdf_upload("guide.pdf", b"")

    def test_rejects_oversized_file(self):
        data = b"%PDF-" + b"x" * MAX_FILE_SIZE_BYTES

        with self.assertRaises(FileTooLargeError):
            validate_pdf_upload("guide.pdf", data)

    def test_rejects_non_pdf_content(self):
        with self.assertRaises(InvalidFileError):
            validate_pdf_upload("guide.pdf", b"This is not a PDF")


class TestCleanText(unittest.TestCase):

    def test_normalizes_unicode(self):
        text = "e\u0301"
        result = clean_text(text)

        self.assertEqual(result, "\u00e9")

    def test_normalizes_line_breaks(self):
        text = "First line\r\nSecond line\rThird line"
        result = clean_text(text)

        self.assertEqual(
            result,
            "First line\nSecond line\nThird line",
        )

    def test_removes_control_characters(self):
        text = "Hello\x00World\x07!"
        result = clean_text(text)

        self.assertEqual(result, "HelloWorld!")

    def test_collapses_repeated_inline_spaces(self):
        text = "Python    is\t\tgreat"
        result = clean_text(text)

        self.assertEqual(result, "Python is great")

    def test_preserves_leading_indentation(self):
        text = "    def example():\n        return True"
        result = clean_text(text)

        self.assertTrue(result.startswith("    def"))
        self.assertIn("\n        return", result)

    def test_preserves_paragraphs(self):
        text = "First paragraph.\n\n\nSecond paragraph."
        result = clean_text(text)

        self.assertEqual(
            result,
            "First paragraph.\n\nSecond paragraph.",
        )

    def test_preserves_symbols(self):
        text = "Python: x = 10; y != 5; result >= 2"
        result = clean_text(text)

        self.assertEqual(result, text)


class TestExtractPages(unittest.TestCase):

    def test_extracts_single_page(self):
        data = make_pdf(["Python programming"])

        pages = extract_pages(data)

        self.assertEqual(len(pages), 1)
        self.assertIn("Python programming", pages[0])

    def test_extracts_multiple_pages(self):
        data = make_pdf([
            "First page content",
            "Second page content",
        ])

        pages = extract_pages(data)

        self.assertEqual(len(pages), 2)
        self.assertIn("First page content", pages[0])
        self.assertIn("Second page content", pages[1])

    def test_keeps_empty_page(self):
        data = make_pdf([
            "Page with text",
            None,
            "Another page with text",
        ])

        pages = extract_pages(data)

        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[1], "")

    def test_rejects_corrupted_pdf(self):
        with self.assertRaises(CorruptedPDFError):
            extract_pages(b"not a valid PDF")

    def test_rejects_encrypted_pdf_without_empty_password(self):
        data = make_encrypted_pdf(
            ["Encrypted content"],
            user_password="secret",
        )

        with self.assertRaises(EncryptedPDFError):
            extract_pages(data)

    def test_accepts_encrypted_pdf_with_empty_password(self):
        data = make_encrypted_pdf(
            ["Public encrypted content"],
            user_password="",
        )

        pages = extract_pages(data)

        self.assertEqual(len(pages), 1)
        self.assertIn("Public encrypted content", pages[0])


class TestProcessPDF(unittest.TestCase):

    def test_processes_valid_pdf(self):
        data = make_pdf([
            "Python is a programming language.",
            "Machine learning uses data.",
        ])

        document = process_pdf("guide.pdf", data)

        self.assertEqual(document.filename, "guide.pdf")
        self.assertEqual(document.fingerprint, fingerprint(data))
        self.assertEqual(document.page_count, 2)
        self.assertEqual(document.word_count, 11)
        self.assertEqual(document.empty_pages, [])
        self.assertGreaterEqual(document.char_count, 1)
        self.assertGreaterEqual(len(document.chunks), 1)

    def test_records_empty_pages(self):
        data = make_pdf([
            "First page has text.",
            None,
            "Third page has text.",
        ])

        document = process_pdf("guide.pdf", data)

        self.assertEqual(document.page_count, 3)
        self.assertEqual(document.empty_pages, [2])

    def test_rejects_scanned_pdf_without_text(self):
        data = make_pdf([None, None])

        with self.assertRaises(NoExtractableTextError):
            process_pdf("scanned.pdf", data)

    def test_rejects_page_less_pdf(self):
        data = make_pdf([])

        with self.assertRaises(NoExtractableTextError):
            process_pdf("empty_pages.pdf", data)

    def test_uses_custom_chunk_settings(self):
        data = make_pdf(["Python programming. " * 30])

        document = process_pdf(
            "guide.pdf",
            data,
            chunk_size=100,
            chunk_overlap=20,
        )

        self.assertEqual(document.chunk_size, 100)
        self.assertEqual(document.chunk_overlap, 20)

    def test_document_consistency(self):
        data = make_pdf([
            "First page content.",
            None,
            "Third page content.",
        ])

        document = process_pdf("guide.pdf", data)

        self.assertTrue(document.check_consistency())

    def test_does_not_write_pdf_to_disk(self):
        data = make_pdf(["Python programming."])

        with patch("builtins.open") as mocked_open:
            process_pdf("guide.pdf", data)

        mocked_open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
