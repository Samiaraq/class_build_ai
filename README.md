# ClassBuild

An AI-powered learning application that generates structured courses, lesson content, and quizzes using the Groq API. It also supports PDF learning materials, semantic search, and lessons grounded in uploaded documents.

## Features

- Generate course outlines based on a topic and difficulty.
- Generate detailed lesson content.
- Create quizzes based on lesson content.
- Grade quiz submissions and provide feedback.
- Validate generated content using Pydantic models.
- Upload PDF files as learning materials.
- Extract and clean text from PDF documents.
- Split document text into smaller chunks for processing.
- Generate local text embeddings for semantic search.
- Search uploaded PDF content using semantic similarity.
- Generate lessons grounded in relevant PDF passages.
- Display source references and page numbers in grounded lessons.
- Track document state and reuse cached search indexes.

## Technologies

- Python
- Streamlit
- Groq API
- Pydantic
- python-dotenv
- pypdf
- Sentence Transformers
- NumPy
- PyTorch

## Project Structure

```text
class_build/
│
├── app.py
├── requirements.txt
├── README.md
├── .env.example
│
├── .streamlit/
│   └── config.toml
│
├── classbuild/
│   ├── config.py
│   ├── llm/
│   ├── models/
│   ├── rag/
│   └── services/
│
└── tests/
```

## Setup

1. Clone the repository:

   ```bash
   git clone <repository-url>
   ```

2. Navigate to the project directory:

   ```bash
   cd class_build
   ```

3. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Create a `.env` file based on `.env.example`.

6. Add your Groq API key to the `.env` file.

## Run

Start the application using:

```bash
streamlit run app.py
```

## Testing

Run the test suite using:

```bash
python -m unittest discover -s tests -t . -v
```

## Limitations

- PDF processing depends on extractable text. Scanned documents without extractable text may not be processed successfully.
- Semantic search uses a local Sentence Transformers embedding model.
- Generating courses and lessons requires a valid Groq API key.
- Grounded lessons depend on the availability and relevance of information in the uploaded PDF.
