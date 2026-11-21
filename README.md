# Mini ClassBuild

An AI-powered learning application that generates structured courses, lesson content, and quizzes using the Groq API. It also supports PDF learning materials, semantic search, and lessons grounded in uploaded documents.

## 1. Overview

Mini ClassBuild helps learners create personalized learning courses based on a selected topic and difficulty level. It generates course outlines, detailed lessons, and quizzes while supporting PDF-based learning and source references.

The application is built with Python and Streamlit, with Pydantic models used to validate generated content.

## 2. Features

- Generate structured course outlines based on a topic and difficulty level.
- Generate detailed lesson content.
- Create quizzes based on generated lessons.
- Grade quiz submissions and provide feedback.
- Validate AI-generated content using Pydantic models.
- Upload PDF files as learning materials.
- Extract, clean, and split PDF text into smaller chunks.
- Generate local text embeddings for semantic search.
- Retrieve relevant PDF passages using semantic similarity.
- Generate lessons grounded in relevant PDF content.
- Display source references and page numbers in grounded lessons.
- Cache document processing and search indexes.
- Save courses locally as JSON files.
- Load and update previously saved courses.
- Export courses as readable Markdown documents.
- Preserve saved lesson content and citations when restoring a course.

## 3. Technologies

- Python
- Streamlit
- Groq API
- Pydantic
- python-dotenv
- pypdf
- Sentence Transformers
- NumPy
- PyTorch

## 4. Project Structure

```text
class_build/
│
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
│
├── .streamlit/
│   └── config.toml
│
├── classbuild/
│   ├── config.py
│   ├── export/
│   │   ├── __init__.py
│   │   └── markdown_export.py
│   ├── llm/
│   ├── models/
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── course_store.py
│   │   └── saved_course.py
│   ├── rag/
│   └── services/
│
├── docs/
│   ├── how_it_works.md
│   └── validation_audit.md
│
├── scripts/
│   ├── evaluation_scenarios.py
│   ├── run_evaluation.py
│   ├── final_check.py
│   └── test_groq_connection.py
│
└── tests/
    ├── test_app.py
    ├── test_end_to_end.py
    ├── test_persistence.py
    └── test_reliability.py
```

## 5. Prerequisites

Before installing the project, make sure you have:

- Python 3.11 or later.
- pip.
- A valid Groq API key.
- Internet access for API requests and the initial download of the embedding model.

## 6. Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   ```

2. Navigate to the project directory:

   ```bash
   cd class_build
   ```

3. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Activate the virtual environment on Windows:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

5. Install the required dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

## 7. Environment Setup

Create a `.env` file in the project root directory using `.env.example` as a template.

Add your Groq API key:

```env
GROQ_API_KEY=your_groq_api_key
```

Do not share your API key or commit the `.env` file to Git.

## 8. Configuration

The application supports the following environment variables:

| Variable | Description | Default |
|---|---|---|
| `GROQ_API_KEY` | Required Groq API key | No default |
| `GROQ_MODEL` | Groq model name | `openai/gpt-oss-20b` |
| `GROQ_TIMEOUT_SECONDS` | Request timeout in seconds | `60` |
| `GROQ_MAX_RETRIES` | Maximum SDK retry count | `1` |
| `MINICLASSBUILD_SAVE_DIR` | Optional directory for saved courses | `saved_courses` |

`GROQ_MAX_RETRIES` is limited to a range from 0 to 3. Invalid values fall back to the default.

## 9. Running the Application

From the project root, activate the virtual environment and run:

```bash
python -m streamlit run app.py
```

Streamlit will start the application and provide a local URL to open in your browser.

## 10. Using the Application

The main workflow includes:

1. Enter a course topic.
2. Select the desired difficulty level.
3. Choose the number of lessons.
4. Generate a structured course outline.
5. Generate lesson content.
6. Generate quizzes and submit answers.
7. Upload a PDF when document-based learning is needed.
8. Use semantic search to retrieve relevant document passages.
9. Generate grounded lessons with source references.

## 11. Saving and Loading Courses

Mini ClassBuild supports local course persistence using JSON files.

Users can:

- Save a generated course.
- Update an existing saved course.
- View previously saved courses.
- Load a saved course without generating it again.
- Restore course outlines, generated lessons, quizzes, and citations.

Saved courses are stored locally in the configured save directory. The default directory is `saved_courses`.

The application validates saved data when writing and reading course files. It also uses independent course identifiers and safe file-handling mechanisms.

For PDF-based courses, the original PDF must be uploaded again with a matching fingerprint before PDF-based generation and answers become available.

## 12. Exporting Courses

Courses can be exported as Markdown files.

The exported document includes:

- Course title and description.
- Learning objectives.
- Lesson outline.
- Generated lesson content.
- PDF source references.
- Quiz questions and options.
- A separate answer key at the end of the document.

Lessons that have not been generated yet are identified in the export.

Markdown export is performed locally and does not require a Groq API request.

## 13. Testing and Evaluation

The project includes unit tests, reliability tests, persistence tests, end-to-end tests, and an offline evaluation suite.

Run all unit tests:

```bash
python -m unittest discover -s tests -t . -v
```

Run the evaluation suite:

```bash
python scripts/run_evaluation.py
```

To run the evaluation without generating a JSON report:

```bash
python scripts/run_evaluation.py --no-json
```

Run the end-to-end test:

```bash
python -m unittest tests.test_end_to_end -v
```

Run the final project verification:

```bash
python scripts/final_check.py --verbose
```

The final checker verifies the Python version, dependencies, unit tests, evaluation suite, and end-to-end workflow.

Offline tests use prepared responses and do not require a real Groq API key.

## 14. Troubleshooting

**Missing Groq API key**

- Check that the `.env` file exists in the project root.
- Verify that `GROQ_API_KEY` contains a valid API key.
- Restart the application after changing environment settings.

**Groq request timeout**

- Check your internet connection.
- Review `GROQ_TIMEOUT_SECONDS`.
- Check whether the selected model is available.

**PDF processing issues**

- Make sure the uploaded PDF contains extractable text.
- Check that the file does not exceed the configured upload size limit.

**Saved course cannot be loaded**

- Check the saved-course directory.
- Make sure the JSON file is valid and has not been modified incorrectly.
- Review the error message displayed by the application.

**Dependency or test errors**

- Activate the correct virtual environment.
- Install dependencies using `python -m pip install -r requirements.txt`.
- Run the relevant test command to identify the failure.

## 15. Limitations and Documentation

### Limitations

- PDF processing depends on extractable text. Scanned documents without extractable text may not be processed successfully.
- Semantic search uses a locally generated Sentence Transformers embedding model.
- The initial embedding model download may require an internet connection.
- Course and lesson generation require a valid Groq API key and an available model.
- Grounded lessons depend on the availability and relevance of information in the uploaded PDF.
- Offline evaluation verifies predefined test cases but does not guarantee the factual accuracy of every live AI-generated response.
- Saved courses store course data and PDF metadata, not the original PDF file or embedding vectors.

### Additional Documentation

For more technical details, see:

- `docs/how_it_works.md` — Explains the application's internal workflow and technical implementation.
- `docs/validation_audit.md` — Documents validation and reliability rules enforced by the project.

### Security

- Keep API keys in the local `.env` file.
- Never commit secrets or personal saved-course data.
- Generated evaluation reports and saved course files should remain local unless intentionally shared.