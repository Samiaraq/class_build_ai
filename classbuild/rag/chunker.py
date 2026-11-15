
from classbuild.rag.models import DocumentChunk


DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150


def _validate(chunk_size: int, chunk_overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")


def _find_cut(text: str, start: int, end: int) -> int:
    search_start = start + (end - start) // 2

    boundaries = [
        "\n\n",
        "\n",
        ". ",
        "! ",
        "? ",
        "؛ ",
        "، ",
        " ",
    ]

    for boundary in boundaries:
        position = text.rfind(boundary, search_start, end)

        if position != -1:
            return position + len(boundary)

    return end


def _next_start(
    text: str,
    start: int,
    cut: int,
    chunk_overlap: int,
) -> int:
    # A long word must not be split by overlapping chunks.
    if (
        cut < len(text)
        and text[cut - 1].isalnum()
        and text[cut].isalnum()
    ):
        return cut

    target = max(0, cut - chunk_overlap)

    # Move backward to the beginning of a word.
    while (
        target > start
        and target < len(text)
        and text[target - 1].isalnum()
        and text[target].isalnum()
    ):
        target -= 1

    # Always guarantee forward progress.
    if target <= start:
        return cut

    return target



def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:

    _validate(chunk_size, chunk_overlap)

    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    seen = set()
    start = 0

    # Avoid duplicate text chunks, but preserve repeated
    # segments when splitting a single long word.
    deduplicate = any(char.isspace() for char in text)

    while start < len(text):
        end = min(start + chunk_size, len(text))
        cut = _find_cut(text, start, end)

        if cut <= start:
            cut = end

        chunk = text[start:cut].strip()

        if chunk and (not deduplicate or chunk not in seen):
            chunks.append(chunk)
            seen.add(chunk)

        if cut >= len(text):
            break

        next_start = _next_start(
            text,
            start,
            cut,
            chunk_overlap,
        )

        if next_start <= start:
            next_start = cut

        start = next_start

    # Merge a very short final tail into the preceding chunk
    # so the final chunk retains the expected overlap.
    if (
        len(chunks) >= 2
        and deduplicate
        and len(chunks[-1]) < chunk_overlap
        and len(chunks[-2]) + 1 + len(chunks[-1]) <= chunk_size
    ):
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()

    return chunks


def chunk_pages(
    pages: list[str],
    source_filename: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:

    chunks = []

    for page_number, page_text in enumerate(pages, start=1):

        page_chunks = chunk_text(
            page_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for chunk_index, text in enumerate(page_chunks, start=1):

            chunks.append(
                DocumentChunk(
                    chunk_id=f"p{page_number}-c{chunk_index}",
                    source_filename=source_filename,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    text=text,
                )
            )

    return chunks
