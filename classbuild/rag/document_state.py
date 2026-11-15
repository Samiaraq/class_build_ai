import logging


from dataclasses import dataclass
from typing import Callable

from classbuild.rag.models import ProcessedDocument
from classbuild.rag.pdf_processor import (
    PDFProcessingError,
    fingerprint,
    process_pdf,
)

DOC_KEY = "document"
DOC_STATUS_KEY = "document_status"
COURSE_MATERIAL_KEY = "course_material_fingerprint"
INDEX_KEY = "document_index"
SEARCH_KEY = "search_results"

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class MaterialStatus:
    document: ProcessedDocument | None
    error: str | None
    processed_now: bool

def clear_learning_material(state: dict) -> None:
    state.pop(DOC_KEY, None)
    state.pop(DOC_STATUS_KEY, None)
    state.pop(INDEX_KEY, None)
    state.pop(SEARCH_KEY, None)

def sync_learning_material(
    state: dict,
    upload: tuple[str, bytes] | None,
    processor: Callable | None = None,
) -> MaterialStatus:
    if upload is None:
        clear_learning_material(state)
        return MaterialStatus(
            document=None,
            error=None,
            processed_now=False,
        )
    filename, data = upload
    current_fingerprint = fingerprint(data)
    identity = (filename, current_fingerprint)

    cached_document = state.get(DOC_KEY)

    if (
        cached_document is not None
        and (cached_document.filename, cached_document.fingerprint) == identity
    ):
        return MaterialStatus(
            document=cached_document,
            error=None,
            processed_now=False,
        )

    cached_status = state.get(DOC_STATUS_KEY)

    if (
        isinstance(cached_status, dict)
        and cached_status.get("identity") == identity
        and cached_status.get("error")
    ):
        return MaterialStatus(
            document=None,
            error=cached_status["error"],
            processed_now=False,
        )

    clear_learning_material(state)
    processor = processor or process_pdf

    try:
        document = processor(filename, data)

    except PDFProcessingError as exc:
        error = str(exc)
        state[DOC_STATUS_KEY] = {
            "identity": identity,
            "error": error,
        }
        return MaterialStatus(
            document=None,
            error=error,
            processed_now=True,
        )
    except Exception:
        logger.exception("Unexpected error while processing PDF.")

        error = "An unexpected error occurred while processing the PDF."
        state[DOC_STATUS_KEY] = {
            "identity": identity,
            "error": error,
        }
        return MaterialStatus(
            document=None,
            error=error,
            processed_now=True,
        )
    state[DOC_KEY] = document
    state[DOC_STATUS_KEY] = None

    return MaterialStatus(
        document=document,
        error=None,
        processed_now=True,
    )
def attach_material_to_course(state: dict) -> None:
    document = state.get(DOC_KEY)

    state[COURSE_MATERIAL_KEY] = (
        document.fingerprint if document else None
    )
def material_for_course(state: dict) -> ProcessedDocument | None:
    document = state.get(DOC_KEY)
    course_fingerprint = state.get(COURSE_MATERIAL_KEY)

    if document is None or course_fingerprint is None:
        return None

    if document.fingerprint != course_fingerprint:
        return None

    return document