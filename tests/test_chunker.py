
import unittest

from classbuild.rag.chunker import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    chunk_text,
    chunk_pages,
)


class TestChunkText(unittest.TestCase):

    def test_empty_text(self):
        self.assertEqual(chunk_text(""), [])

    def test_whitespace_text(self):
        self.assertEqual(chunk_text("   \n  "), [])

    def test_short_text(self):
        text = "Python is a programming language."
        self.assertEqual(chunk_text(text), [text])

    def test_chunk_size_limit(self):
        text = "Python programming. " * 100
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)

        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)

    def test_overlap_between_chunks(self):
        text = " ".join(f"word{i}" for i in range(100))
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)

        self.assertGreater(len(chunks), 1)

        for first, second in zip(chunks, chunks[1:]):
            self.assertTrue(
                first[-20:].strip() in second
                or second in first
                or first[-20:].strip() == ""
            )

    def test_ordered_coverage(self):
        text = " ".join(f"word{i}" for i in range(100))
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)

        for word_index in range(100):
            word = f"word{word_index}"
            self.assertTrue(
                any(word in chunk for chunk in chunks),
                f"{word} is missing from chunks",
            )

    def test_paragraph_boundaries(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, chunk_size=35, chunk_overlap=5)

        self.assertGreater(len(chunks), 1)

    def test_sentence_boundaries(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = chunk_text(text, chunk_size=35, chunk_overlap=5)

        self.assertGreater(len(chunks), 1)

    def test_very_long_word(self):
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)

        self.assertTrue(chunks)
        self.assertEqual("".join(chunks), text)

    def test_zero_overlap(self):
        text = " ".join(f"word{i}" for i in range(50))
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=0)

        self.assertGreater(len(chunks), 1)

    def test_no_duplicate_tail_chunk(self):
        text = "Python programming. " * 20
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)

        self.assertEqual(len(chunks), len(set(chunks)))

    def test_invalid_chunk_size(self):
        with self.assertRaises(ValueError):
            chunk_text("Some text", chunk_size=0)

    def test_negative_overlap(self):
        with self.assertRaises(ValueError):
            chunk_text("Some text", chunk_size=100, chunk_overlap=-1)

    def test_overlap_equal_to_chunk_size(self):
        with self.assertRaises(ValueError):
            chunk_text("Some text", chunk_size=100, chunk_overlap=100)


class TestChunkPages(unittest.TestCase):

    def test_chunk_ids_and_metadata(self):
        pages = [
            "Python programming. " * 20,
            "Machine learning. " * 20,
        ]

        chunks = chunk_pages(
            pages,
            source_filename="guide.pdf",
            chunk_size=100,
            chunk_overlap=20,
        )

        self.assertTrue(chunks)

        for chunk in chunks:
            self.assertEqual(chunk.source_filename, "guide.pdf")
            self.assertGreaterEqual(chunk.page_number, 1)
            self.assertGreaterEqual(chunk.chunk_index, 1)
            self.assertTrue(chunk.chunk_id.startswith("p"))

    def test_chunks_never_span_pages(self):
        pages = [
            "Python programming. " * 20,
            "Machine learning. " * 20,
        ]

        chunks = chunk_pages(
            pages,
            source_filename="guide.pdf",
            chunk_size=100,
            chunk_overlap=20,
        )

        for chunk in chunks:
            expected = pages[chunk.page_number - 1]
            self.assertTrue(
                all(word in expected for word in chunk.text.split())
            )

    def test_empty_pages(self):
        chunks = chunk_pages(
            ["", "Python programming.", "   "],
            source_filename="guide.pdf",
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].page_number, 2)

    def test_default_settings(self):
        self.assertEqual(DEFAULT_CHUNK_SIZE, 800)
        self.assertEqual(DEFAULT_CHUNK_OVERLAP, 150)


if __name__ == "__main__":
    unittest.main()
