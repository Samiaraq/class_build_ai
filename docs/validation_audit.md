# Validation and Reliability Audit

This document records the validation and reliability rules enforced by Mini ClassBuild. Rules are grouped by area and identify the model, validator, or function responsible for enforcing them.

**Status definitions:**
- **Already enforced:** The rule was implemented before Step 10.
- **Fixed in Step 10:** The rule or reliability gap was addressed as part of Step 10.

## 1. Course Outline Validation

| Rule | Enforced by | Status |
|---|---|---|
| Reject unexpected fields in the outline and lesson objects. | `CourseOutline`, `LessonOutline` (`extra="forbid"`) | Already enforced |
| Strip surrounding whitespace and reject empty strings. | `NonEmptyStr` | Already enforced |
| Allow only Beginner, Intermediate, or Advanced difficulty levels. | `Difficulty` | Already enforced |
| Require at least 3 and at most 5 course learning objectives. | `CourseOutline.learning_objectives` | Already enforced |
| Require at least 2 and at most 3 learning objectives per lesson. | `LessonOutline.learning_objectives` | Already enforced |
| Require at least one lesson in the outline. | `CourseOutline.lessons` | Already enforced |
| Require lesson numbers to start at 1 and be sequential. | `CourseOutline.check_lesson_numbers()` | Already enforced |
| Reject duplicate lesson titles, ignoring differences in case and whitespace. | `CourseOutline.check_unique_lesson_titles()` | Fixed in Step 10 |
| Require the generated lesson count to match the requested count. | `CourseOutline.check_matches_request()` | Already enforced |
| Require the generated difficulty to match the requested difficulty. | `CourseOutline.check_matches_request()` | Already enforced |

## 2. Lesson Content Validation

| Rule | Enforced by | Status |
|---|---|---|
| Reject unexpected fields in lesson content, sections, exercises, and source references. | `LessonContent`, `LessonSection`, `Exercise`, `SourceReference` (`extra="forbid"`) | Already enforced |
| Require non-empty lesson titles, headings, explanations, examples, introductions, summaries, and exercise text. | `NonEmptyStr` | Already enforced |
| Require lesson numbers to be greater than or equal to 1. | `LessonContent.lesson_number` | Already enforced |
| Require between 2 and 4 lesson sections. | `LessonContent.sections` | Already enforced |
| Require exactly 2 exercises per lesson. | `LessonContent.exercises` | Already enforced |
| Reject duplicate source IDs within a section. | `LessonSection.no_duplicate_ids()` | Already enforced |
| Require generated lesson numbers to match the selected lesson. | `LessonContent.check_matches_selected_lesson()` | Already enforced |
| Require generated lesson titles to match the selected lesson, ignoring case and whitespace. | `LessonContent.check_matches_selected_lesson()` | Already enforced |

## 3. PDF Grounding and Citation Validation

| Rule | Enforced by | Status |
|---|---|---|
| Require at least one source reference in a grounded lesson. | `LessonGrounding.sources` | Already enforced |
| Require source page numbers and chunk indexes to be greater than or equal to 1. | `SourceReference.page_number`, `SourceReference.chunk_index` | Already enforced |
| Reject duplicate allowed source IDs. | `LessonContent.check_citations()` | Already enforced |
| Reject duplicate source references in a grounded lesson. | `LessonContent.check_citations()` | Already enforced |
| Require grounded lessons to cite at least one source. | `LessonContent.check_citations()` | Already enforced |
| Reject citations in ordinary lessons that do not have grounding information. | `LessonContent.check_citations()` | Already enforced |
| Require the grounding document fingerprint to match the expected PDF. | `LessonContent.check_citations()` | Already enforced |
| Require the grounding filename to match the retrieved source filenames. | `LessonContent.check_citations()` | Already enforced |
| Reject sources that were not included in the retrieved results. | `LessonContent.check_citations()` | Already enforced |
| Require source filenames, page numbers, chunk indexes, text, and similarity scores to match the retrieved data. | `LessonContent.check_citations()` | Already enforced |
| Require every cited source ID to exist in the grounding sources list. | `LessonContent.check_citations()` | Already enforced |
| Require every listed grounding source to be cited. | `LessonContent.check_citations()` | Already enforced |
| Reject unknown source IDs in generated lesson drafts. | `GroundedLessonDraft.only_known_passages()` | Already enforced |
| Use only retrieved passages that meet the minimum similarity threshold. | `select_evidence()` | Already enforced |
| Reject lesson generation when no sufficiently similar passages are retrieved. | `GroundedLessonGenerator.generate_lesson()` | Already enforced |
| Reject lesson generation when the retrieved evidence does not support the selected lesson. | `GroundedLessonGenerator.generate_lesson()` | Already enforced |
| Retry lesson generation once when the draft contains no citations, then reject it if citations are still missing. | `GroundedLessonGenerator.generate_lesson()` | Already enforced |
| Reject page numbers mentioned in lesson content when those pages are not among the cited pages. | `uncited_page_mentions()` and `GroundedLessonGenerator.generate_lesson()` | Fixed in Step 10 |

## 4. Quiz Validation

| Rule | Enforced by | Status |
|---|---|---|
| Reject unexpected fields in quiz and question objects. | `Quiz`, `Question` (`extra="forbid"`) | Already enforced |
| Require non-empty question text, options, explanations, and lesson titles. | `NonEmptyStr` | Already enforced |
| Require exactly 5 questions per quiz. | `Quiz.questions` and `QUESTION_COUNT` | Already enforced |
| Require exactly 4 options per question. | `Question.options` and `OPTION_COUNT` | Already enforced |
| Reject duplicate options, ignoring differences in case and whitespace. | `Question.options_must_be_distinct()` | Already enforced |
| Require the correct answer to be a strict integer between 0 and 3. | `Question.correct_answer` | Already enforced |
| Reject repeated questions, ignoring differences in case and whitespace. | `Quiz.questions_must_be_distinct()` | Already enforced |
| Require the quiz lesson number to be greater than or equal to 1. | `Quiz.lesson_number` | Already enforced |
| Require the quiz lesson number and title to match the selected lesson. | `Quiz.check_matches_selected_lesson()` | Already enforced |

## 5. Generation Prerequisites and Service Validation

| Rule | Enforced by | Status |
|---|---|---|
| Require a course outline before generating lesson content. | `find_lesson()` | Already enforced |
| Reject lesson numbers that do not exist in the course outline. | `find_lesson()` | Already enforced |
| Validate generated lesson content against the selected lesson number and title. | `LessonGenerator.generate_lesson()` | Already enforced |
| Remove grounding and source fields from the ordinary lesson JSON schema. | `_without_source_fields()` | Already enforced |
| Require an existing selected lesson before generating a quiz. | `QuizGenerator.generate_quiz()` and `find_lesson()` | Already enforced |
| Require lesson content to exist before generating a quiz. | `QuizGenerator.generate_quiz()` | Already enforced |
| Require the provided lesson content to match the selected lesson number and title before quiz generation. | `QuizGenerator.generate_quiz()` | Already enforced |
| Convert Pydantic validation failures into user-facing generation errors. | `LessonGenerator.generate_lesson()`, `QuizGenerator.generate_quiz()`, and `describe_validation_error()` | Already enforced |

## 6. Structured Output Validation and Retries

| Rule | Enforced by | Status |
|---|---|---|
| Require exactly two system prompts for structured generation. | `request_structured_json()` | Already enforced |
| Limit structured JSON generation to two attempts. | `MAX_ATTEMPTS` and `request_structured_json()` | Already enforced |
| Retry when the generated response contains invalid JSON. | `request_structured_json()` | Already enforced |
| Do not retry other Groq client errors at the structured-output layer. | `request_structured_json()` | Already enforced |
| Remove unsupported schema keywords before sending JSON schemas to Groq. | `strict_schema()` and `_clean_schema()` | Already enforced |
| Convert validation errors into readable field-specific messages. | `describe_validation_error()` | Already enforced |
| Log structured-generation failures with the model, attempt number, error category, and a shortened preview. | `_log_structured_failure()` | Already enforced |

## 7. Groq Reliability and Secret Protection

| Rule | Enforced by | Status |
|---|---|---|
| Use a default SDK retry count of 1. | `DEFAULT_MAX_RETRIES` in `config.py` | Fixed in Step 10 |
| Limit the configured SDK retry count to a maximum of 3. | `MAX_ALLOWED_RETRIES` and `get_settings()` | Fixed in Step 10 |
| Fall back to the default retry count when `GROQ_MAX_RETRIES` contains invalid text. | `get_settings()` | Fixed in Step 10 |
| Allow the retry count to be configured between 0 and 3. | `get_settings()` | Fixed in Step 10 |
| Pass the configured retry count to the Groq SDK. | `GroqClient.__init__()` | Fixed in Step 10 |
| Retry temporary failures such as timeouts, connection errors, HTTP 408, 409, 429, and 5xx responses within the configured limit. | Groq SDK configuration in `GroqClient` | Fixed in Step 10 |
| Do not retry permanent HTTP errors such as 400, 401, 403, and 404. | Groq SDK retry behavior | Fixed in Step 10 |
| Redact Groq API keys beginning with `gsk_` from error text. | `redact_secrets()` | Fixed in Step 10 |
| Apply secret redaction to API error details before returning them. | `GroqClient._error_detail()` | Fixed in Step 10 |

## 8. Retry Budget

The application has two separate retry layers:

- **Groq SDK retries:** Handle temporary HTTP and connection failures according to `GROQ_MAX_RETRIES`.
- **Structured JSON retries:** Allow one additional generation attempt when the response contains invalid JSON.

The SDK retry count is configurable and bounded between 0 and 3. The structured JSON layer is limited to two attempts.

Other Groq client errors are raised immediately by `request_structured_json()` rather than triggering another structured-output attempt.

The combined retry behavior is verified in `tests/test_reliability.py`, including HTTP status codes, configurable retry limits, and the request budget for structured generation.

## 9. Verification

The following tests verify the Step 10 validation and reliability rules:

- `tests/test_course_models.py`: Course outline validation, including duplicate lesson title rejection.
- `tests/test_grounded_lessons.py`: Grounded lesson validation, citations, and uncited page mention detection.
- `tests/test_reliability.py`: SDK retry behavior, retry configuration, request limits, timeout handling, and API key redaction.

The offline evaluation suite in `scripts/evaluation_scenarios.py` and `scripts/run_evaluation.py` links project behaviors to their existing tests and reports whether the checks passed.

**Audit scope:** This document covers course outline, lesson, grounded lesson, quiz, structured-output, and Groq reliability rules relevant to Step 10. Persistence and export checks belong to the later Stage 3 steps.