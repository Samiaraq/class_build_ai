
import logging
import re
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

import streamlit as st
from classbuild.rag.document_state import (
    COURSE_MATERIAL_KEY,
    attach_material_to_course,
    material_for_course,
    sync_learning_material,
)

from classbuild.rag.document_state import DOC_KEY
from classbuild.rag.embeddings import EmbeddingService
from classbuild.rag.search_state import get_or_build_index
from classbuild.services.grounded_lesson_generator import (
    GroundedLessonGenerator,
    InsufficientEvidenceError,
)
from classbuild.services.lesson_state import (
    remove_stale_grounded_lessons,
)

from classbuild.rag.search_state import (
    current_results,
    run_search,
)
from classbuild.rag.retriever import (
    RetrievalError,
    EmptyQueryError,
    NoDocumentError,
)

from classbuild.rag.embeddings import EmbeddingError

from classbuild.persistence import (
    CourseStore,
    CourseStorageError,
    InvalidCourseIdError,
    CourseNotFoundError,
    CourseFileTooLargeError,
    CorruptedCourseFileError,
    UnsupportedSchemaVersionError,
    build_saved_course,
    new_course_id,
)
from classbuild.export import course_to_markdown, course_filename
from classbuild.course_config import (
    DIFFICULTY_LEVELS,
    DEFAULT_DIFFICULTY,
    validate_course_config,
    CourseConfigError,
)

from classbuild.llm.exceptions import GroqClientError
from classbuild.services.course_generator import CourseGenerator
from classbuild.services.lesson_generator import LessonGenerator
from classbuild.services.quiz_generator import QuizGenerator
from classbuild.services.quiz_grader import (
    grade_quiz,
    QuizSubmissionError,
)

from classbuild.services.structured_output import (
    CourseGenerationError,
    ContentValidationError,
    StructuredGenerationError,)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


CONFIG_KEY = "course_config"
OUTLINE_KEY = "course_outline"
LESSONS_KEY = "lesson_contents"
COURSE_ID_KEY = "course_id"
QUIZZES_KEY = "quizzes"
RESULTS_KEY = "quiz_results"
ATTEMPTS_KEY = "quiz_attempts"
EVIDENCE_NOTICES_KEY = "evidence_notices"
UPLOADER_KEY = "pdf_uploader"

SAVED_ID_KEY = "saved_course_id"
SAVED_CREATED_KEY = "saved_created_at"
SAVED_AT_KEY = "saved_updated_at"
SAVED_HASH_KEY = "saved_content_hash"
SOURCE_DOC_KEY = "source_document"
SELECTED_LESSON_KEY = "selected_lesson"
SAVE_FLASH_KEY = "save_flash"

COURSE_STATE_KEYS = (
    CONFIG_KEY,
    OUTLINE_KEY,
    LESSONS_KEY,
    COURSE_ID_KEY,
    QUIZZES_KEY,
    RESULTS_KEY,
    ATTEMPTS_KEY,
    EVIDENCE_NOTICES_KEY,
    COURSE_MATERIAL_KEY,
    SAVED_ID_KEY,
    SAVED_CREATED_KEY,
    SAVED_AT_KEY,
    SAVED_HASH_KEY,
    SOURCE_DOC_KEY,
    SELECTED_LESSON_KEY,
)


def render_header():
    st.title("Mini ClassBuild")

    st.subheader("Build your own AI-powered learning experience")

    st.write(
        "Create a structured course on any topic, "
        "generate detailed lessons, and test your knowledge "
        "with interactive quizzes."
    )


def render_sidebar():
    with st.sidebar:
        st.title("Mini ClassBuild")

        st.write(
            "An AI-powered tool that helps you create "
            "personalized learning courses."
        )

        st.divider()

        st.subheader("Available Now")

        st.write(
            "- Course outline generation\n"
            "- Detailed lesson content\n"
            "- Five-question quizzes\n"
            "- Automatic quiz grading"
            "- PDF upload and summary\n"
            "- Semantic search in uploaded PDFs\n"
            "- PDF-grounded lessons\n"
        )

        st.subheader("Coming Soon")

        st.write(
            "- More learning resources\n"
            "- Additional assessment types"
        )

        st.divider()

        if st.session_state.get(OUTLINE_KEY):
            st.success("Current step: Learning")
        else:
            st.info("Current step: Create a course")


# PDF Learning Materials

def render_learning_materials():
    st.divider()
    st.header("Learning Materials")

    upload = st.file_uploader(
        "Upload a PDF file",
        type=["pdf"],
        key=UPLOADER_KEY,
    )

    upload_data = (
        (upload.name, upload.getvalue())
        if upload is not None
        else None
    )
    status = sync_learning_material(st.session_state, upload_data)

    if status.error:
        st.error(status.error)
        return

    document = status.document

    if document is None:
        return

    required_document = required_source_document()
    if (
        required_document is not None
        and document.fingerprint == required_document.fingerprint
    ):
        attach_material_to_course(st.session_state)

    render_document_summary(document)
    render_pdf_search(document)


def render_document_summary(document):
    st.subheader("PDF Summary")

    col1, col2, col3 = st.columns(3)

    col1.metric("Pages", document.page_count)
    col2.metric("Words", document.word_count)
    col3.metric("Chunks", document.chunk_count)

    st.write(f"**File:** {document.filename}")
    st.write(f"**Characters:** {document.char_count}")

    if document.empty_pages:
        st.warning(
            "Pages without extractable text: "
            + ", ".join(map(str, document.empty_pages))
        )

    with st.expander("Preview document chunks"):
        for chunk in document.chunks[:3]:
            st.caption(
                f"Page {chunk.page_number} · "
                f"Chunk {chunk.chunk_index}"
            )
            st.text(chunk.text)


def render_course_material_note():
    required_document = required_source_document()

    if required_document is not None and not pdf_features_allowed():
        st.info(
            "This saved course uses the following PDF. "
            "Upload the same original file to re-enable PDF-based features:"
        )
        st.text(required_document.filename)
        return

    document = material_for_course(st.session_state)

    if document is None:
        st.info(
            "This course is not linked to the currently uploaded PDF."
        )
    else:
        st.caption(
            f"Course reference material: {document.filename}"
        )


def render_pdf_search(document):
    st.subheader("Search in PDF")

    query = st.text_input(
        "Ask something about the uploaded PDF",
        key=(
            f"pdf_search_"
            f"{st.session_state.get(COURSE_ID_KEY, 'no_course')}_"
            f"{document.fingerprint[:12]}"
        ),
    )

    if st.button(
        "Search PDF",
        key=f"search_button_{document.fingerprint[:12]}",
    ):
        try:
            with st.spinner("Searching the document..."):
                outcome = run_search(
                    st.session_state,
                    query,
                )

            st.session_state["active_pdf_search_query"] = outcome.query

        except EmptyQueryError as error:
            st.warning(str(error))

        except NoDocumentError as error:
            st.warning(str(error))

        except EmbeddingError as error:
            st.error(f"Could not create embeddings: {error}")

        except RetrievalError as error:
            st.error(f"Search failed: {error}")

    results = current_results(st.session_state)

    if results:
        render_search_results(
            st.session_state.get("active_pdf_search_query", ""),
            results,
        )


def render_search_results(query, results):
    st.markdown("### Search Results")

    if query:
        st.caption(f"Query: {query}")

    for result in results:
        with st.expander(
            f"Page {result.page_number} · "
            f"Similarity: {result.score:.3f}"
        ):
            st.caption(
                f"Source: {result.source_filename} · "
                f"Chunk: {result.chunk_index}"
            )
            st.text(result.text)


def required_source_document():
    """Return the saved PDF metadata required by the current loaded course."""
    return st.session_state.get(SOURCE_DOC_KEY)


def pdf_features_allowed():
    """Allow PDF-grounded features only when the required PDF fingerprint matches."""
    required_document = required_source_document()
    if required_document is None:
        return True

    return current_pdf_fingerprint() == required_document.fingerprint


def plain(text):
    """Escape Markdown punctuation so filenames are displayed as plain text."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", str(text))


def current_pdf_fingerprint():
    document = st.session_state.get(DOC_KEY)
    return document.fingerprint if document else None


def drop_stale_grounded_lessons():
    if st.session_state.get(SAVED_ID_KEY):
        return

    lessons = get_lesson_cache()

    stale_numbers = [
        number
        for number, lesson in lessons.items()
        if (
            lesson.grounding is not None
            and lesson.grounding.document_fingerprint
            != current_pdf_fingerprint()
        )
    ]

    if stale_numbers:
        remove_stale_grounded_lessons(
            lessons,
            current_pdf_fingerprint(),
            _state_dict(QUIZZES_KEY),
            _state_dict(RESULTS_KEY),
            _state_dict(ATTEMPTS_KEY),
        )

        st.warning(
            "Some lessons were removed because their source PDF "
            "is no longer the currently uploaded document."
        )


def current_evidence_notice(lesson_number):
    notice = st.session_state.get(
        EVIDENCE_NOTICES_KEY, {}
    ).get(lesson_number)

    if not notice:
        return None

    if notice.get("fingerprint") != current_pdf_fingerprint():
        return None

    return notice.get("message")


def render_pdf_reference_option():
    if not pdf_features_allowed():
        required_document = required_source_document()
        if required_document is not None:
            st.warning(
                "PDF-based lesson generation is disabled until you upload "
                "the original PDF used by this saved course:"
            )
            st.text(required_document.filename)
        return None

    document = material_for_course(st.session_state)

    if document is None:
        return None

    course_id = st.session_state.get(COURSE_ID_KEY, "no_course")

    use_pdf = st.checkbox(
        "Use Uploaded PDF as Reference",
        value=False,
        key=f"use_pdf_{course_id}_{document.fingerprint[:12]}",
    )

    return document if use_pdf else None


def generate_grounded_lesson(outline, lesson_number, document):
    service = EmbeddingService()

    index, _ = get_or_build_index(
        st.session_state,
        document,
        service,
    )

    return GroundedLessonGenerator().generate_lesson(
        outline,
        lesson_number,
        document,
        index,
    )


def keep_previous_course_notice():
    if st.session_state.get(OUTLINE_KEY) is not None:
        st.warning(
            "The new course could not be generated. Your previous course "
            "is still available below and has not been changed."
        )

def render_form():

    with st.form("course_form"):

        st.subheader("Create a New Course")

        topic = st.text_input(
            "Course Topic",
            placeholder="e.g. Introduction to Python",
        )

        difficulty = st.radio(
            "Difficulty Level",
            options=DIFFICULTY_LEVELS,
            index=DIFFICULTY_LEVELS.index(DEFAULT_DIFFICULTY),
            horizontal=True,
        )

        lesson_count = st.slider(
            "Number of Lessons",
            min_value=2,
            max_value=5,
            value=3,
        )

        submitted = st.form_submit_button(
            "Generate Course",
            type="primary",
        )

    if not submitted:
        return
    
    try:
        config = validate_course_config(
            topic=topic,
            difficulty=difficulty,
            lesson_count=lesson_count,
    
        )
    except CourseConfigError as error:
        st.error(str(error))
        keep_previous_course_notice()
        return

    try:
        with st.spinner("Generating your course outline..."):
            outline = CourseGenerator().generate_outline(config)

        # Clear old course data only after the new outline passed validation.
        for key in COURSE_STATE_KEYS:
            st.session_state.pop(key, None)

        st.session_state[CONFIG_KEY] = config
        st.session_state[OUTLINE_KEY] = outline
        st.session_state[COURSE_ID_KEY] = uuid.uuid4().hex[:8]
        attach_material_to_course(st.session_state)
       
        st.success("Your course was generated successfully!")
        st.rerun()

    except ContentValidationError:
        logger.exception("Course content validation failed.")
        st.error(
            "The generated course did not pass validation. "
            "Please try again."
        )
        keep_previous_course_notice()

    except CourseGenerationError as error:
        logger.exception("Course generation failed.")
        st.error(f"Could not generate the course: {error}")
        keep_previous_course_notice()

    except StructuredGenerationError:
        logger.exception("Structured course generation failed.")
        st.error(
            "The AI could not generate a valid course. "
            "Please try again."
        )
        keep_previous_course_notice()

    except GroqClientError as error:
        logger.exception("Groq request failed.")
        st.error(f"AI service error: {error}")
        keep_previous_course_notice()

    except Exception:
        logger.exception("Unexpected error while generating course.")
        st.error(
            "Something unexpected happened. "
            "Please try again later."
        )
        keep_previous_course_notice()

def get_lesson_cache():
    if LESSONS_KEY not in st.session_state:
        st.session_state[LESSONS_KEY] = {}

    return st.session_state[LESSONS_KEY]


# Lesson Generation

def generate_lesson_content(lesson_number, document=None):
    st.session_state[SELECTED_LESSON_KEY] = lesson_number
    
    lesson_cache = get_lesson_cache()
    if lesson_number in lesson_cache:
        return True

    outline = st.session_state.get(OUTLINE_KEY)

    if outline is None:
        st.error("Please generate a course first.")
        return False

    try:
        with st.spinner(
            f"Generating lesson {lesson_number}..."
        ):
            if document is not None:
                content = generate_grounded_lesson(
                    outline,
                    lesson_number,
                    document,
                )
            else:
                content = LessonGenerator().generate_lesson(
                    outline,
                    lesson_number,
                )

        lesson_cache[lesson_number] = content

        st.session_state.get(
            EVIDENCE_NOTICES_KEY, {}
        ).pop(lesson_number, None)

        st.success(
            f"Lesson {lesson_number} generated successfully!"
        )

        return True

    except InsufficientEvidenceError as error:
        notices = _state_dict(EVIDENCE_NOTICES_KEY)
        notices[lesson_number] = {
            "fingerprint": document.fingerprint,
            "message": str(error),
        }

        st.warning(
            "The uploaded PDF does not contain enough evidence "
            "to generate this lesson."
        )
        return False

    except (RetrievalError, EmbeddingError) as error:
        logger.exception(
            "PDF retrieval failed for lesson %s.",
            lesson_number,
        )
        st.error(f"Could not use the PDF: {error}")
        return False

    except Exception as error:
        logger.exception(
            "Failed to generate lesson %s.",
            lesson_number,
        )

        st.error(
            f"Could not generate lesson {lesson_number}: {error}"
        )

        return False


def render_lesson_sources(content):
    if content.grounding is None:
        return

    st.markdown("### Sources")

    for source in content.grounding.sources:
        with st.expander(
            f"{source.source_filename} · "
            f"Page {source.page_number} · "
            f"Similarity: {source.similarity:.3f}"
        ):
            st.caption(
                f"Chunk ID: {source.chunk_id}"
            )
            st.text(source.text)


# Display Lesson Content

def render_lesson_content(content):

    st.subheader(content.title)

    st.write(content.introduction)

    if content.is_grounded:
        citation_label = (
            "Based on the uploaded PDF"
            if pdf_features_allowed()
            else "Saved PDF citations (source file not currently loaded)"
        )
        st.caption(
            citation_label
            + " · Cited pages: "
            + ", ".join(map(str, content.cited_pages))
        )

    source_map = {}

    if content.grounding is not None:
        source_map = {
            source.chunk_id: source
            for source in content.grounding.sources
        }

    for index, section in enumerate(content.sections, start=1):

        st.markdown(f"### {index}. {section.heading}")

        st.write(section.explanation)

        st.markdown("**Example**")
        st.code(section.example, language="python")

        if section.source_ids:
            st.caption("Section sources:")
            for source_id in section.source_ids:
                source = source_map.get(source_id)
                if source:
                    st.caption(
                        f"{source.source_filename} · "
                        f"Page {source.page_number}"
                    )

    st.markdown("### Summary")

    st.write(content.summary)

    st.markdown("### Exercises")

    for index, exercise in enumerate(content.exercises, start=1):

        st.markdown(
            f"**Exercise {index}:** {exercise.question}"
        )

        st.caption(f"Hint: {exercise.hint}")

    if content.is_grounded:
        render_lesson_sources(content)
        
def _state_dict(key):

    if key not in st.session_state:
        st.session_state[key] = {}

    return st.session_state[key]


def quiz_widget_prefix(lesson_number):

    course_id = st.session_state.get(
        COURSE_ID_KEY,
        "no_course",
    )

    attempts = _state_dict(ATTEMPTS_KEY)

    attempt_number = attempts.get(lesson_number, 0)

    return (
        f"quiz_{course_id}"
        f"_l{lesson_number}"
        f"_a{attempt_number}"
    )


def retake_quiz(lesson_number):

    st.session_state[SELECTED_LESSON_KEY] = lesson_number
    results = _state_dict(RESULTS_KEY)
    attempts = _state_dict(ATTEMPTS_KEY)

    results.pop(lesson_number, None)

    attempts[lesson_number] = (
        attempts.get(lesson_number, 0) + 1
    )





def generate_quiz(lesson_number):

    st.session_state[SELECTED_LESSON_KEY] = lesson_number
    quizzes = _state_dict(QUIZZES_KEY)

    # Keep an existing quiz instead of generating another one.
    if lesson_number in quizzes:
        return True

    outline = st.session_state.get(OUTLINE_KEY)
    lessons = get_lesson_cache()

    content = lessons.get(lesson_number)

    if outline is None or content is None:
        st.error(
            "Generate the lesson content before generating its quiz."
        )
        return False

    try:
        with st.spinner("Generating your quiz..."):

            quiz = QuizGenerator().generate_quiz(
                outline,
                lesson_number,
                content,
            )

        quizzes[lesson_number] = quiz

        st.success("Quiz generated successfully!")

        return True

    except Exception as error:
        logger.exception(
            "Failed to generate quiz for lesson %s.",
            lesson_number,
        )

        st.error(f"Could not generate the quiz: {error}")

        return False


# Quiz Section

def render_quiz_section(lesson_number):

    quizzes = _state_dict(QUIZZES_KEY)
    results = _state_dict(RESULTS_KEY)

    st.divider()

    st.subheader("Knowledge Check")

    quiz = quizzes.get(lesson_number)

    if quiz is None:

        if st.button(
            "Generate Quiz",
            key=(
                f"generate_quiz_"
                f"{st.session_state.get(COURSE_ID_KEY, 'no_course')}_"
                f"{lesson_number}"
            ),
        ):
            generated = generate_quiz(lesson_number)

            if generated:
                st.rerun()
        return

    result = results.get(lesson_number)

    if result is not None:
        render_quiz_result(result)
    else:
        render_quiz_form(quiz, lesson_number)


# Quiz Form and Local Grading

def render_quiz_form(quiz, lesson_number):

    prefix = quiz_widget_prefix(lesson_number)

    with st.form(f"{prefix}_form"):

        st.subheader("Quiz")

        answers = []

        for index, question in enumerate(
            quiz.questions,
            start=1,
        ):

            st.markdown(
                f"**Question {index}: {question.question}**"
            )

            selected = st.radio(
                f"Choose your answer for question {index}",
                options=range(len(question.options)),
                format_func=lambda option, q=question: (
                    q.options[option]
                ),
                index=None,
                key=f"{prefix}_q{index}",
                label_visibility="collapsed",
            )

            answers.append(selected)

        submitted = st.form_submit_button(
            "Submit Answers",
            type="primary",
        )

    if not submitted:
        return

    try:
        result = grade_quiz(quiz, answers)

        st.session_state[SELECTED_LESSON_KEY] = lesson_number
        _state_dict(RESULTS_KEY)[lesson_number] = result

        st.rerun()

    except QuizSubmissionError as error:
        st.warning(str(error))


# Quiz Results

def render_quiz_result(result):

    percentage = result.percentage

    if percentage >= 80:
        st.success(f"Your Score: {percentage}%")

    elif percentage >= 50:
        st.info(f"Your Score: {percentage}%")

    else:
        st.warning(f"Your Score: {percentage}%")

    st.markdown("### Your Answers")

    for index, question_result in enumerate(
        result.question_results,
        start=1,
    ):

        if question_result.is_correct:
            st.markdown(
                f"### ✓ Question {index}"
            )
        else:
            st.markdown(
                f"### ✗ Question {index}"
            )

        st.write(
            f"Your answer: {question_result.selected_text}"
        )

        if not question_result.is_correct:
            st.write(
                f"Correct answer: {question_result.correct_text}"
            )

    if st.button(
        "Try Again",
        key=(
            f"try_again_"
            f"{st.session_state.get(COURSE_ID_KEY, 'no_course')}_"
            f"{result.lesson_number}"
        ),
    ):
        retake_quiz(result.lesson_number)
        st.rerun()


# Course Outline

def render_outline():

    outline = st.session_state.get(OUTLINE_KEY)

    if outline is None:
        return

    drop_stale_grounded_lessons()
    render_course_material_note()

    document = render_pdf_reference_option()
    course_id = st.session_state.get(COURSE_ID_KEY, "no_course")
    pdf_fingerprint = current_pdf_fingerprint() or "no_pdf"
    widget_scope = f"{course_id}_{pdf_fingerprint[:12]}"

    st.divider()

    st.header(outline.title)

    st.write(f"**Difficulty:** {outline.difficulty}")

    st.write(outline.description)

    st.subheader("Learning Objectives")

    for objective in outline.learning_objectives:
        st.markdown(f"- {objective}")

    st.download_button(
        "Download Course as Markdown",
        data=course_to_markdown(
            outline,
            st.session_state[CONFIG_KEY].topic,
            list(get_lesson_cache().values()),
            list(_state_dict(QUIZZES_KEY).values()),
        ),
        file_name=course_filename(outline.title),
        mime="text/markdown",
        key=(
            f"download_course_"
            f"{st.session_state.get(COURSE_ID_KEY, 'course')}"
        ),
    )

    st.divider()

    st.header("Course Lessons")

    lesson_cache = get_lesson_cache()
    selected_lesson = st.session_state.get(SELECTED_LESSON_KEY)
    valid_lesson_numbers = {
        lesson.lesson_number for lesson in outline.lessons
    }

    if selected_lesson not in valid_lesson_numbers:
        selected_lesson = (
            outline.lessons[0].lesson_number
            if outline.lessons
            else None
        )
        if selected_lesson is not None:
            st.session_state[SELECTED_LESSON_KEY] = selected_lesson

    for lesson in outline.lessons:

        lesson_number = lesson.lesson_number

        with st.expander(
            f"Lesson {lesson_number}: {lesson.title}",
            expanded=(lesson_number == selected_lesson),
        ):

            st.write("**Learning Objectives**")

            for objective in lesson.learning_objectives:
                st.markdown(f"- {objective}")

            content = lesson_cache.get(lesson_number)

            if content is not None:

                render_lesson_content(content)

                render_quiz_section(lesson_number)

            else:
                notice = current_evidence_notice(lesson_number)

                if notice:
                    st.warning(notice)

                    if st.button(
                        "Generate Without PDF",
                        key=f"without_pdf_{widget_scope}_{lesson_number}",
                    ):
                        _state_dict(EVIDENCE_NOTICES_KEY).pop(
                            lesson_number, None
                        )
                        generate_lesson_content(lesson_number)
                        st.rerun()

                if st.button(
                    "Generate Lesson Content",
                    key=f"generate_lesson_{widget_scope}_{lesson_number}",
                ):
                    generate_lesson_content(
                        lesson_number,
                        document=document,
                    )
                    st.rerun()

# Saved Courses (Stage 3)

def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def current_saved_course(course_id=None):
    outline = st.session_state.get(OUTLINE_KEY)
    config = st.session_state.get(CONFIG_KEY)

    if outline is None or config is None:
        raise ValueError("Generate or load a course before saving it.")

    selected_lesson = st.session_state.get(SELECTED_LESSON_KEY)
    created_at = st.session_state.get(SAVED_CREATED_KEY)

    return build_saved_course(
        course_id=(
            course_id
            or st.session_state.get(SAVED_ID_KEY)
            or new_course_id()
        ),
        topic=config.topic,
        outline=outline,
        lessons=list(get_lesson_cache().values()),
        quizzes=list(_state_dict(QUIZZES_KEY).values()),
        created_at=created_at,
        selected_lesson=selected_lesson,
    )


def save_current_course(store):
    """Save or update the current course; mutate session metadata only on success."""
    try:
        saved_course = current_saved_course()
        store.save(saved_course)

    except InvalidCourseIdError as error:
        st.error(
            f"The course could not be saved because its saved ID is invalid: {error}"
        )
        return False

    except CourseNotFoundError as error:
        st.error(
            f"The saved course could not be found for updating: {error}"
        )
        return False

    except CourseFileTooLargeError as error:
        st.error(f"The course is too large to save: {error}")
        return False

    except CorruptedCourseFileError as error:
        st.error(f"The saved course file is damaged: {error}")
        return False

    except UnsupportedSchemaVersionError as error:
        st.error(
            f"This saved course uses an unsupported format: {error}"
        )
        return False

    except CourseStorageError as error:
        st.error(f"Could not save the course: {error}")
        return False

    except (ValidationError, ValueError) as error:
        st.error(
            f"The current course is not valid for saving: {error}"
        )
        return False

    except Exception:
        logger.exception(
            "Unexpected error while saving the current course."
        )
        st.error(
            "Something unexpected happened while saving the course. "
            "Your current course is unchanged."
        )
        return False

    st.session_state[SAVED_ID_KEY] = saved_course.course_id
    st.session_state[SAVED_CREATED_KEY] = saved_course.created_at
    st.session_state[SAVED_AT_KEY] = saved_course.updated_at
    st.session_state[SAVED_HASH_KEY] = saved_course.content_hash()
    st.session_state[SOURCE_DOC_KEY] = saved_course.source_document
    st.session_state[SAVE_FLASH_KEY] = "Course saved successfully."

    return True


def restore_saved_course(course):
    """Restore a saved course without calling Groq or reusing old widget state."""
    config = validate_course_config(
        topic=course.topic,
        difficulty=course.difficulty,
        lesson_count=len(course.outline.lessons),
    )

    for key in COURSE_STATE_KEYS:
        st.session_state.pop(key, None)

    st.session_state[CONFIG_KEY] = config
    st.session_state[OUTLINE_KEY] = course.outline
    st.session_state[LESSONS_KEY] = course.lessons_by_number()
    st.session_state[QUIZZES_KEY] = course.quizzes_by_number()
    st.session_state[RESULTS_KEY] = {}
    st.session_state[ATTEMPTS_KEY] = {}
    st.session_state[EVIDENCE_NOTICES_KEY] = {}
    st.session_state[COURSE_ID_KEY] = uuid.uuid4().hex[:8]
    st.session_state[SAVED_ID_KEY] = course.course_id
    st.session_state[SAVED_CREATED_KEY] = course.created_at
    st.session_state[SAVED_AT_KEY] = course.updated_at
    st.session_state[SAVED_HASH_KEY] = course.content_hash()
    st.session_state[SOURCE_DOC_KEY] = course.source_document
    st.session_state[SELECTED_LESSON_KEY] = course.selected_lesson
    st.session_state[SAVE_FLASH_KEY] = "Saved course loaded successfully."


def _summary_label(summary):
    title = (
        getattr(summary, "title", None)
        or getattr(summary, "topic", "Saved course")
    )
    updated_at = getattr(summary, "updated_at", None)
    lesson_count = getattr(summary, "lesson_count", None)
    quiz_count = getattr(summary, "quiz_count", None)
    has_pdf = getattr(
        summary,
        "has_pdf",
        getattr(summary, "pdf_based", False),
    )

    details = []

    if lesson_count is not None:
        details.append(f"{lesson_count} lessons")

    if quiz_count is not None:
        details.append(f"{quiz_count} quizzes")

    if has_pdf:
        details.append("PDF-based")

    if updated_at:
        details.append(f"Updated: {updated_at}")

    suffix = " · ".join(details)

    return f"{title} · {suffix}" if suffix else str(title)


def render_saved_courses():
    st.divider()
    st.header("Saved Courses")

    flash = st.session_state.pop(SAVE_FLASH_KEY, None)

    if flash:
        st.success(flash)

    outline = st.session_state.get(OUTLINE_KEY)

    if outline is not None:
        try:
            current_course = current_saved_course()
            saved_id = st.session_state.get(SAVED_ID_KEY)
            saved_hash = st.session_state.get(SAVED_HASH_KEY)

            has_unsaved_changes = bool(
                saved_id
                and saved_hash
                and current_course.content_hash() != saved_hash
            )

            if has_unsaved_changes:
                st.info("This course has unsaved changes.")

            save_label = (
                "Update Saved Course"
                if saved_id
                else "Save Course"
            )

            if st.button(
                save_label,
                type="primary",
                key="save_or_update_course",
            ):
                if save_current_course(CourseStore()):
                    st.rerun()

        except (ValidationError, ValueError) as error:
            st.warning(
                f"This course cannot be saved yet: {error}"
            )

    try:
        store = CourseStore()
        listing = store.list_courses()

    except CourseStorageError as error:
        st.error(f"Could not read saved courses: {error}")
        return

    for issue in listing.issues:
        st.warning(str(issue))

    summaries = list(listing.courses)

    if not summaries:
        st.caption("No saved courses yet.")
        return

    labels = {
        summary.course_id: _summary_label(summary)
        for summary in summaries
    }

    selected_id = st.selectbox(
        "Choose a saved course",
        options=[
            summary.course_id
            for summary in summaries
        ],
        format_func=lambda course_id: labels.get(
            course_id,
            course_id,
        ),
        key="saved_course_picker",
    )

    if st.button(
        "Load Selected Course",
        key="load_selected_course",
    ):
        try:
            saved_course = store.load(selected_id)
            restore_saved_course(saved_course)
            st.rerun()

        except InvalidCourseIdError as error:
            st.error(
                f"The selected course ID is invalid: {error}"
            )

        except CourseNotFoundError as error:
            st.error(
                f"The selected saved course no longer exists: {error}"
            )

        except CourseFileTooLargeError as error:
            st.error(
                f"The saved course file is too large: {error}"
            )

        except CorruptedCourseFileError as error:
            st.error(
                f"The selected saved course is damaged: {error}"
            )

        except UnsupportedSchemaVersionError as error:
            st.error(
                f"The selected course uses an unsupported format: {error}"
            )

        except CourseStorageError as error:
            st.error(
                f"Could not load the selected course: {error}"
            )

        except (ValidationError, ValueError) as error:
            st.error(
                f"The saved course could not be restored: {error}"
            )


# Main Application

def main():

    st.set_page_config(
        page_title="Mini ClassBuild",
        page_icon="📚",
        layout="centered",
    )

    render_sidebar()

    render_header()
    render_learning_materials()
    render_form()

    saved_courses_container = st.container()
    render_outline()

    with saved_courses_container:
        render_saved_courses()

if __name__ == "__main__":

    main()