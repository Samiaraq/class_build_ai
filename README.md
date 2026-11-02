# ClassBuild

An AI-powered learning application that generates structured courses, lesson content, and quizzes using the Groq API.

## Features

- Generate course outlines based on a topic and difficulty.
- Generate detailed lesson content.
- Create quizzes based on lesson content.
- Grade quiz submissions and provide feedback.
- Validate generated content using Pydantic models.

## Technologies

- Python
- Streamlit
- Groq API
- Pydantic
- python-dotenv

## Setup

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies:

   pip install -r requirements.txt

4. Create a `.env` file based on `.env.example`.
5. Add your Groq API key to the `.env` file.

## Run

streamlit run app.py