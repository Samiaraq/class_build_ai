
import logging
import uuid

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
    StructuredGenerationError,
)



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
EVIDENCE_NOTICES_KEY="evidence_notices"

UPLOADER_KEY="pdf_uploader"

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
            "- Automatic quiz grading\n"
            "- PDF upload and summary\n"
            "- Semantic search in uploaded PDFs\n"
            "- PDF-grounded lessons"
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

    status = sync_learning_material(
        st.session_state,
        upload_data,
    )

    if status.error:
        st.error(status.error)
        return

    document = status.document

    if document is None:
        return

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
    course_id = st.session_state.get(COURSE_ID_KEY, "no_course")
    if st.button(
        "Search PDF",
        key=f"search_button_{course_id}_{document.fingerprint[:12]}",    ):
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

def current_pdf_fingerprint():
    document = st.session_state.get(DOC_KEY)
    return document.fingerprint if document else None


def drop_stale_grounded_lessons():
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

# Course Form

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

    # Clear the previous course before generating a new one.
    for key in COURSE_STATE_KEYS:
        st.session_state.pop(key, None)

    try:
        config = validate_course_config(
            topic=topic,
            difficulty=difficulty,
            lesson_count=lesson_count,
        )

    except CourseConfigError as error:
        st.error(str(error))
        return

    try:
        with st.spinner("Generating your course outline..."):
            outline = CourseGenerator().generate_outline(config)

        st.session_state[CONFIG_KEY] = config
        st.session_state[OUTLINE_KEY] = outline
        st.session_state[COURSE_ID_KEY] = uuid.uuid4().hex[:8]
        attach_material_to_course(st.session_state)
        st.success("Your course was generated successfully!")

        st.rerun()

    except ContentValidationError as error:
        logger.exception("Course content validation failed.")
        st.error(
            "The generated course did not pass validation. "
            "Please try again."
        )

    except CourseGenerationError as error:
        logger.exception("Course generation failed.")
        st.error(f"Could not generate the course: {error}")

    except StructuredGenerationError as error:
        logger.exception("Structured course generation failed.")
        st.error(
            "The AI could not generate a valid course. "
            "Please try again."
        )

    except GroqClientError as error:
        logger.exception("Groq request failed.")
        st.error(f"AI service error: {error}")

    except Exception:
        logger.exception("Unexpected error while generating course.")
        st.error(
            "Something unexpected happened. "
            "Please try again later."
        )


# Lesson Cache

def get_lesson_cache():
    if LESSONS_KEY not in st.session_state:
        st.session_state[LESSONS_KEY] = {}

    return st.session_state[LESSONS_KEY]


# Lesson Generation

def generate_lesson_content(lesson_number, document=None):
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
        st.caption(
            "Based on the uploaded PDF · "
            f"Cited pages: {', '.join(map(str, content.cited_pages))}"
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


# Quiz Session State Helpers


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

    results = _state_dict(RESULTS_KEY)
    attempts = _state_dict(ATTEMPTS_KEY)

    results.pop(lesson_number, None)

    attempts[lesson_number] = (
        attempts.get(lesson_number, 0) + 1
    )


# Quiz Generation


def generate_quiz(lesson_number):

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

    st.divider()

    st.header("Course Lessons")

    lesson_cache = get_lesson_cache()

    for lesson in outline.lessons:

        lesson_number = lesson.lesson_number

        with st.expander(
            f"Lesson {lesson_number}: {lesson.title}",
            expanded=False,
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

    render_outline()


if __name__ == "__main__":

    main()