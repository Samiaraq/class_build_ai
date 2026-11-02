
import copy


QUIZ_CORRECT_ANSWERS = [0, 1, 2, 3, 1]


def valid_outline(lesson_count=3, difficulty="Beginner"):
    return {
        "title": "Python Programming",
        "description": "A practical introduction to Python programming.",
        "difficulty": difficulty,
        "learning_objectives": [
            "Understand Python fundamentals",
            "Write simple Python programs",
            "Apply programming concepts",
        ],
        "lessons": [
            {
                "lesson_number": number,
                "title": f"Lesson {number} title",
                "description": f"Description for lesson {number}.",
                "learning_objectives": [
                    f"Understand concept {number}",
                    f"Apply concept {number}",
                ],
            }
            for number in range(1, lesson_count + 1)
        ],
    }


def valid_lesson(lesson_number=1, title="Lesson 1 title", sections=3):
    return {
        "lesson_number": lesson_number,
        "title": title,
        "introduction": "This lesson introduces important Python concepts.",
        "sections": [
            {
                "heading": f"Section {number}",
                "explanation": f"Explanation of concept {number}.",
                "example": f"Example demonstrating concept {number}.",
            }
            for number in range(1, sections + 1)
        ],
        "summary": "This lesson covered the main Python concepts.",
        "exercises": [
            {
                "question": "What is a variable in Python?",
                "hint": "Think about storing a value.",
            },
            {
                "question": "How do you display text in Python?",
                "hint": "Think about the print function.",
            },
        ],
    }


def valid_quiz(lesson_number=1, lesson_title="Lesson 1 title"):
    questions = [
        {
            "question": f"What is the main purpose of concept {number}?",
            "options": [
                f"Correct answer {number}",
                f"Incorrect option A {number}",
                f"Incorrect option B {number}",
                f"Incorrect option C {number}",
            ],
            "correct_answer": QUIZ_CORRECT_ANSWERS[number - 1],
            "explanation": f"Explanation for question {number}.",
        }
        for number in range(1, 6)
    ]

    return {
        "lesson_number": lesson_number,
        "lesson_title": lesson_title,
        "questions": questions,
    }


def copy_of(data):
    return copy.deepcopy(data)
