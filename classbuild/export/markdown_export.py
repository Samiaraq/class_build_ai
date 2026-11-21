
import re
from pathlib import Path


OPTION_LETTERS = "ABCD"


def _one_line(text):
    """Collapse text into a single clean line."""
    return " ".join(str(text or "").split())


def _sources_line(lesson, source_ids):
    """Build a readable citation line for the requested source IDs."""
    grounding = getattr(lesson, "grounding", None)

    if grounding is None or not source_ids:
        return ""

    sources = getattr(grounding, "sources", [])
    source_map = {
        getattr(source, "chunk_id", None): source
        for source in sources
    }

    citations = []

    for source_id in source_ids:
        source = source_map.get(source_id)

        if source is None:
            continue

        filename = getattr(source, "source_filename", "Unknown PDF")
        page = getattr(source, "page_number", None)

        if page is not None:
            citations.append(f"{filename}, page {page}")
        else:
            citations.append(filename)

    if not citations:
        return ""

    unique_citations = list(dict.fromkeys(citations))
    return "Sources: " + "; ".join(unique_citations)


def course_to_markdown(outline, topic, lessons, quizzes):
    """Convert a generated course into a Markdown document."""
    lines = []

    lines.append(f"# {getattr(outline, 'title', topic)}")
    lines.append("")

    description = getattr(outline, "description", "")
    if description:
        lines.append(_one_line(description))
        lines.append("")

    lines.append(f"**Topic:** {_one_line(topic)}")
    lines.append(
        f"**Difficulty:** {getattr(outline, 'difficulty', 'Not specified')}"
    )
    lines.append("")

    objectives = getattr(outline, "learning_objectives", [])
    if objectives:
        lines.append("## Learning Objectives")
        lines.append("")

        for objective in objectives:
            lines.append(f"- {_one_line(objective)}")

        lines.append("")

    outline_lessons = getattr(outline, "lessons", [])

    lines.append("## Course Outline")
    lines.append("")

    for lesson_outline in outline_lessons:
        number = getattr(lesson_outline, "lesson_number", "")
        title = getattr(lesson_outline, "title", "")
        description = getattr(lesson_outline, "description", "")

        lines.append(f"### Lesson {number}: {_one_line(title)}")

        if description:
            lines.append(_one_line(description))

        lines.append("")

    lessons_by_number = {
        getattr(lesson, "lesson_number", None): lesson
        for lesson in lessons
    }

    lines.append("# Lesson Content")
    lines.append("")

    for lesson_outline in outline_lessons:
        number = getattr(lesson_outline, "lesson_number", None)
        lesson = lessons_by_number.get(number)

        if lesson is None:
            lines.append(f"## Lesson {number}: Not generated yet")
            lines.append("")
            lines.append("This lesson has not been generated yet.")
            lines.append("")
            continue

        title = getattr(lesson, "title", getattr(lesson_outline, "title", ""))

        lines.append(f"## Lesson {number}: {_one_line(title)}")
        lines.append("")

        intro = getattr(lesson, "introduction", "")
        if intro:
            lines.append(_one_line(intro))
            lines.append("")

        for section in getattr(lesson, "sections", []):
            heading = getattr(section, "heading", "")
            explanation = getattr(section, "explanation", "")
            example = getattr(section, "example", "")
            source_ids = getattr(section, "source_ids", [])

            lines.append(f"### {_one_line(heading)}")
            lines.append("")

            if explanation:
                lines.append(_one_line(explanation))
                lines.append("")

            if example:
                lines.append("**Example:**")
                lines.append("")
                lines.append(_one_line(example))
                lines.append("")

            source_line = _sources_line(lesson, source_ids)

            if source_line:
                lines.append(f"*{source_line}*")
                lines.append("")

        summary = getattr(lesson, "summary", "")
        if summary:
            lines.append("### Summary")
            lines.append("")
            lines.append(_one_line(summary))
            lines.append("")

        exercises = getattr(lesson, "exercises", [])

        if exercises:
            lines.append("### Exercises")
            lines.append("")

            for index, exercise in enumerate(exercises, start=1):
                question = getattr(exercise, "question", "")
                hint = getattr(exercise, "hint", "")

                lines.append(f"{index}. {_one_line(question)}")

                if hint:
                    lines.append(f"   - Hint: {_one_line(hint)}")

            lines.append("")

    quizzes_by_number = {
        getattr(quiz, "lesson_number", None): quiz
        for quiz in quizzes
    }

    lines.append("# Quizzes")
    lines.append("")

    for lesson_outline in outline_lessons:
        number = getattr(lesson_outline, "lesson_number", None)
        quiz = quizzes_by_number.get(number)

        if quiz is None:
            continue

        lines.append(f"## Quiz: Lesson {number}")
        lines.append("")

        for question_index, question in enumerate(
            getattr(quiz, "questions", []),
            start=1,
        ):
            question_text = getattr(question, "question", "")
            options = getattr(question, "options", [])

            lines.append(f"**{question_index}. {_one_line(question_text)}**")
            lines.append("")

            for option_index, option in enumerate(options):
                if option_index >= len(OPTION_LETTERS):
                    break

                lines.append(
                    f"- {OPTION_LETTERS[option_index]}. {_one_line(option)}"
                )

            lines.append("")

    if quizzes:
        lines.append("# Answer Key")
        lines.append("")

        for lesson_outline in outline_lessons:
            number = getattr(lesson_outline, "lesson_number", None)
            quiz = quizzes_by_number.get(number)

            if quiz is None:
                continue

            lines.append(f"## Lesson {number}")
            lines.append("")

            for question_index, question in enumerate(
                getattr(quiz, "questions", []),
                start=1,
            ):
                correct_answer = getattr(question, "correct_answer", None)
                explanation = getattr(question, "explanation", "")

                if (
                    isinstance(correct_answer, int)
                    and 0 <= correct_answer < len(OPTION_LETTERS)
                ):
                    answer = OPTION_LETTERS[correct_answer]
                else:
                    answer = "Not available"

                lines.append(f"{question_index}. **{answer}**")

                if explanation:
                    lines.append(f"   - {_one_line(explanation)}")

            lines.append("")

    return "\n".join(lines).strip() + "\n"


def course_filename(title):
    """Create a safe Markdown filename from a course title."""
    filename = str(title or "course").strip().lower()
    filename = re.sub(r"[^\w\s-]", "", filename)
    filename = re.sub(r"[\s_-]+", "-", filename)
    filename = filename.strip("-")

    if not filename:
        filename = "course"

    return f"{filename}.md"
