

from dataclasses import dataclass


T = "tests."


@dataclass(frozen=True)
class Scenario:
    number: int
    name: str
    category: str
    checks: str
    tests: tuple[str, ...]


SCENARIOS = (
    Scenario(
        1,
        "Valid course outline",
        "Outlines",
        "A valid course outline is generated with the requested settings.",
        (
            T + "test_course_models.ValidOutlineTests.test_valid_outline_passes",
            T + "test_course_generator.SuccessfulGenerationTests.test_success_on_first_attempt",
            T + "test_course_generator.SuccessfulGenerationTests.test_prompt_contains_request",
        ),
    ),
    Scenario(
        2,
        "Invalid course outlines",
        "Outlines",
        "Invalid course outlines are rejected by validation.",
        (
            T + "test_course_models.RejectedOutlineTests.test_missing_course_field",
            T + "test_course_models.RejectedOutlineTests.test_no_lessons",
            T + "test_course_models.RejectedOutlineTests.test_wrong_lesson_count",
            T + "test_course_models.RejectedOutlineTests.test_invalid_difficulty",
        ),
    ),
    Scenario(
        3,
        "Lesson outline consistency",
        "Outlines",
        "Lesson numbers, titles, and requested difficulty remain consistent.",
        (
            T + "test_course_models.RejectedOutlineTests.test_nonsequential_lesson_numbers",
            T + "test_course_models.RejectedOutlineTests.test_duplicate_lesson_titles_rejected",
            T + "test_course_generator.ValidationTests.test_difficulty_mismatch_rejected",
        ),
    ),
    Scenario(
        4,
        "Strict structured output",
        "Structured output",
        "Structured responses follow the expected JSON schema.",
        (
            T + "test_course_generator.GenerateJsonTests.test_strict_schema_mode_for_gpt_oss",
            T + "test_course_generator.GenerateJsonTests.test_json_object_mode_for_other_models",
            T + "test_course_generator.SchemaTests.test_schema_is_strict_mode_friendly",
        ),
    ),
    Scenario(
        5,
        "Invalid JSON handling",
        "Structured output",
        "Empty, invalid, and truncated JSON responses are detected.",
        (
            T + "test_course_generator.GenerateJsonTests.test_empty_response_raises",
            T + "test_course_generator.GenerateJsonTests.test_invalid_json_raises",
            T + "test_course_generator.GenerateJsonTests.test_truncated_output",
        ),
    ),
    Scenario(
        6,
        "Structured output retries",
        "Errors and retries",
        "Invalid structured responses are retried within the configured limit.",
        (
            T + "test_course_generator.RetryTests.test_first_attempt_fails_second_succeeds",
            T + "test_course_generator.RetryTests.test_both_attempts_fail",
            T + "test_course_generator.RetryTests.test_unrelated_errors_are_not_retried",
        ),
    ),
    Scenario(
        7,
        "Valid lesson generation",
        "Lessons",
        "A lesson is generated for the selected lesson in the course outline.",
        (
            T + "test_lesson_generator.LessonGeneratorTests.test_generates_selected_lesson",
            T + "test_lesson_generator.LessonGeneratorTests.test_prompt_contains_course_context",
            T + "test_lesson_generator.LessonGeneratorTests.test_schema_pins_selected_lesson",
        ),
    ),
    Scenario(
        8,
        "Lesson validation",
        "Lessons",
        "Generated lessons must satisfy the lesson content requirements.",
        (
            T + "test_lesson_generator.LessonModelTests.test_valid_lesson_passes",
            T + "test_lesson_generator.LessonModelTests.test_section_and_exercise_counts",
            T + "test_lesson_generator.LessonModelTests.test_wrong_lesson_number_rejected",
            T + "test_lesson_generator.LessonModelTests.test_wrong_title_rejected",
        ),
    ),
    Scenario(
        9,
        "Lesson generation failures",
        "Errors and retries",
        "Lesson generation handles invalid responses and service failures safely.",
        (
            T + "test_lesson_generator.LessonGeneratorTests.test_invalid_content_not_retried",
            T + "test_lesson_generator.LessonGeneratorTests.test_structured_failure_retried_once_then_succeeds",
            T + "test_lesson_generator.LessonGeneratorTests.test_structured_failure_twice",
        ),
    ),
    Scenario(
        10,
        "Valid quiz generation",
        "Quizzes",
        "A quiz is generated using the selected lesson content.",
        (
            T + "test_quiz.QuizGeneratorTests.test_generated_quiz_uses_lesson_content",
            T + "test_quiz.QuizGeneratorTests.test_prompt_includes_lesson_content",
            T + "test_quiz.QuizGeneratorTests.test_schema_pins_lesson_information",
        ),
    ),
    Scenario(
        11,
        "Quiz structure validation",
        "Quizzes",
        "Quizzes contain the required number of questions and valid options.",
        (
            T + "test_quiz.QuizModelTests.test_valid_quiz_passes",
            T + "test_quiz.QuizModelTests.test_rejects_four_questions",
            T + "test_quiz.QuizModelTests.test_rejects_six_questions",
            T + "test_quiz.QuizModelTests.test_rejects_five_options",
        ),
    ),
    Scenario(
        12,
        "Quiz answer validation",
        "Quizzes",
        "Quiz questions reject invalid answers and duplicate content.",
        (
            T + "test_quiz.QuizModelTests.test_rejects_invalid_correct_answer_indices",
            T + "test_quiz.QuizModelTests.test_rejects_duplicate_options",
            T + "test_quiz.QuizModelTests.test_rejects_duplicate_questions",
        ),
    ),
    Scenario(
        13,
        "Quiz grading",
        "Quizzes",
        "Quiz answers are graded locally and return the correct feedback.",
        (
            T + "test_quiz.GradingTests.test_all_correct_answers_give_100_percent",
            T + "test_quiz.GradingTests.test_three_correct_answers_give_60_percent",
            T + "test_quiz.GradingTests.test_zero_correct_answers_give_zero_percent",
            T + "test_quiz.GradingTests.test_question_feedback_is_returned",
        ),
    ),
    Scenario(
        14,
        "PDF upload validation",
        "State",
        "PDF uploads reject invalid, empty, and oversized files.",
        (
            T + "test_pdf_processor.TestValidatePDFUpload.test_accepts_valid_pdf",
            T + "test_pdf_processor.TestValidatePDFUpload.test_rejects_empty_file",
            T + "test_pdf_processor.TestValidatePDFUpload.test_rejects_non_pdf_content",
            T + "test_pdf_processor.TestValidatePDFUpload.test_rejects_oversized_file",
        ),
    ),
    Scenario(
        15,
        "PDF text processing",
        "State",
        "Valid PDFs are processed into clean text and page-aware chunks.",
        (
            T + "test_pdf_processor.TestProcessPDF.test_processes_valid_pdf",
            T + "test_pdf_processor.TestProcessPDF.test_document_consistency",
            T + "test_pdf_processor.TestExtractPages.test_extracts_multiple_pages",
        ),
    ),
    Scenario(
        16,
        "PDF processing safety",
        "State",
        "Scanned, corrupted, and invalid PDFs are handled safely.",
        (
            T + "test_pdf_processor.TestProcessPDF.test_rejects_scanned_pdf_without_text",
            T + "test_pdf_processor.TestProcessPDF.test_rejects_page_less_pdf",
            T + "test_pdf_processor.TestExtractPages.test_rejects_corrupted_pdf",
        ),
    ),
    Scenario(
        17,
        "Document chunking",
        "State",
        "Document chunks preserve order, page boundaries, and configured sizes.",
        (
            T + "test_chunker.TestChunkPages.test_chunks_never_span_pages",
            T + "test_chunker.TestChunkPages.test_chunk_ids_and_metadata",
            T + "test_chunker.TestChunkText.test_chunk_size_limit",
            T + "test_chunker.TestChunkText.test_ordered_coverage",
        ),
    ),
    Scenario(
        18,
        "Embedding validation",
        "State",
        "Embedding inputs and outputs are validated before retrieval.",
        (
            T + "test_retrieval.TestEmbeddingValidation.test_valid_embedding_matrix",
            T + "test_retrieval.TestEmbeddingValidation.test_rejects_wrong_dimension",
            T + "test_retrieval.TestEmbeddingValidation.test_rejects_nan_values",
            T + "test_retrieval.TestEmbeddingValidation.test_rejects_zero_vectors",
        ),
    ),
    Scenario(
        19,
        "Document retrieval",
        "State",
        "Search returns ranked results with the correct document metadata.",
        (
            T + "test_retrieval.TestSearch.test_returns_ranked_results",
            T + "test_retrieval.TestSearch.test_respects_top_k",
            T + "test_retrieval.TestSearch.test_result_contains_chunk_metadata",
            T + "test_retrieval.TestSearch.test_rejects_empty_query",
        ),
    ),
    Scenario(
        20,
        "Retrieval index consistency",
        "State",
        "Retrieval indexes are reused only when they match the current document.",
        (
            T + "test_retrieval.TestCheckIndex.test_accepts_matching_index",
            T + "test_retrieval.TestCheckIndex.test_rejects_different_fingerprint",
            T + "test_retrieval.TestSearchState.test_rebuilds_index_for_different_document",
            T + "test_retrieval.TestSearchState.test_run_search_reuses_existing_index",
        ),
    ),
    Scenario(
        21,
        "Grounded lesson citations",
        "RAG citations",
        "Grounded lessons use valid citations from retrieved source passages.",
        (
            T + "test_grounded_lessons.TestDraftToLesson.test_converts_draft_to_grounded_lesson",
            T + "test_grounded_lessons.TestDraftToLesson.test_preserves_cited_sources",
            T + "test_grounded_lessons.TestDraftToLesson.test_rejects_draft_without_citations",
        ),
    ),
    Scenario(
        22,
        "Grounded lesson evidence",
        "RAG citations",
        "Grounded lessons reject irrelevant evidence and unknown source references.",
        (
            T + "test_grounded_lessons.TestGroundedLessonDraft.test_rejects_unknown_source_ids",
            T + "test_grounded_lessons.TestGroundedLessonGenerator.test_generate_rejects_irrelevant_draft",
            T + "test_grounded_lessons.TestGroundedLessonGenerator.test_generate_rejects_low_similarity_evidence",
        ),
    ),
    Scenario(
        23,
        "Grounded lesson citation retries",
        "RAG citations",
        "Grounded lesson generation retries missing citations and rejects uncited page mentions.",
        (
            T + "test_grounded_lessons.TestGroundedLessonGenerator.test_generate_retries_when_no_citations",
            T + "test_grounded_lessons.TestGroundedLessonGenerator.test_generate_rejects_missing_citations_after_retry",
            T + "test_grounded_lessons.TestUncitedPageMentions.test_detects_uncited_page_mentions",
        ),
    ),
    Scenario(
        24,
        "Application state handling",
        "State",
        "Course, lesson, and quiz state is maintained or cleared in the expected situations.",
        (
            T + "test_app.AppTests.test_valid_submit_generates_once_and_survives_reruns",
            T + "test_app.AppTests.test_lessons_generated_individually_and_cached",
            T + "test_app.QuizAppTests.test_new_course_clears_quiz_state",
            T + "test_document_state.TestDocumentState.test_removed_file_clears_document_and_derived_state",
        ),
    ),
    Scenario(
        25,
        "API reliability and secret protection",
        "Errors and retries",
        "Temporary API errors are retried safely and API keys are never exposed.",
        (
            T + "test_reliability.SDKRetryTests.test_temporary_server_error_is_retried",
            T + "test_reliability.SDKRetryTests.test_client_errors_are_not_retried",
            T + "test_reliability.SecretRedactionTests.test_api_key_is_redacted",
            T + "test_reliability.RetrySettingsTests.test_retry_value_is_clamped",
        ),
    ),
)
