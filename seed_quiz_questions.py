"""
Optional: seeds a small starter set of quiz categories and questions so
you have something to demo right away, instead of starting from a
completely empty quiz section. This is NOT run automatically - the app
never creates quiz content on its own, matching how materials work
(everything comes from the admin panel unless you choose to run this).

Safe to run more than once - it skips any category that already exists.

Usage:
    python seed_quiz_questions.py
"""
from app import app
from models import db, QuizCategory, QuizQuestion

STARTER_DATA = {
    "General Knowledge": [
        ("What is the capital of Nigeria?", "Lagos", "Abuja", "Kano", "Ibadan", "b",
         "Abuja became Nigeria's capital in 1991, replacing Lagos."),
        ("How many continents are there?", "5", "6", "7", "8", "c", None),
        ("What is the largest ocean on Earth?", "Atlantic", "Indian", "Arctic", "Pacific", "d", None),
        ("Which gas do plants absorb from the atmosphere?", "Oxygen", "Carbon dioxide", "Nitrogen", "Hydrogen", "b", None),
        ("What is the currency of Nigeria?", "Cedi", "Naira", "Franc", "Rand", "b", None),
    ],
    "Science": [
        ("What planet is known as the Red Planet?", "Venus", "Mars", "Jupiter", "Saturn", "b", None),
        ("What is the chemical symbol for water?", "H2O", "O2", "CO2", "HO2", "a", None),
        ("What force pulls objects toward the Earth?", "Magnetism", "Friction", "Gravity", "Tension", "c", None),
        ("How many bones are in the adult human body?", "196", "206", "216", "226", "b", None),
        ("What is the powerhouse of the cell?", "Nucleus", "Ribosome", "Mitochondria", "Cytoplasm", "c", None),
    ],
    "History": [
        ("In what year did Nigeria gain independence?", "1957", "1960", "1963", "1970", "b", None),
        ("Who was the first president of the United States?", "Abraham Lincoln", "Thomas Jefferson", "George Washington", "John Adams", "c", None),
        ("The Great Wall is located in which country?", "Japan", "China", "Mongolia", "Vietnam", "b", None),
        ("Which war ended in 1945?", "World War I", "World War II", "The Cold War", "The Vietnam War", "b", None),
        ("Who was Nigeria's first president?", "Nnamdi Azikiwe", "Tafawa Balewa", "Yakubu Gowon", "Obafemi Awolowo", "a", None),
    ],
    "Computer Science": [
        ("What does CPU stand for?", "Central Process Unit", "Central Processing Unit", "Computer Personal Unit", "Central Processor Unifier", "b", None),
        ("Which language is primarily used for styling web pages?", "HTML", "CSS", "Python", "SQL", "b", None),
        ("What does SQL stand for?", "Structured Query Language", "Simple Query Language", "Sequential Query Logic", "Standard Query Language", "a", None),
        ("What is the binary representation of the decimal number 2?", "01", "10", "11", "00", "b", None),
        ("Which of these is not a programming language?", "Python", "Java", "HTML", "C++", "c",
         "HTML is a markup language, not a programming language - it has no logic or control flow."),
    ],
    "Geography": [
        ("What is the longest river in the world?", "Amazon", "Nile", "Yangtze", "Mississippi", "b", None),
        ("Which is the largest country by land area?", "USA", "China", "Canada", "Russia", "d", None),
        ("Mount Everest is located in which mountain range?", "Andes", "Alps", "Himalayas", "Rockies", "c", None),
        ("Which African country has the largest population?", "Egypt", "Nigeria", "Ethiopia", "South Africa", "b", None),
        ("What is the smallest country in the world?", "Monaco", "San Marino", "Vatican City", "Liechtenstein", "c", None),
    ],
}

with app.app_context():
    created_categories = 0
    created_questions = 0

    for category_name, questions in STARTER_DATA.items():
        category = QuizCategory.query.filter_by(name=category_name).first()
        if not category:
            category = QuizCategory(name=category_name, description=f"Test your knowledge of {category_name.lower()}.")
            db.session.add(category)
            db.session.flush()  # get category.id before adding questions
            created_categories += 1

        for question_text, a, b, c, d, correct, explanation in questions:
            exists = QuizQuestion.query.filter_by(
                category_id=category.id, question_text=question_text
            ).first()
            if not exists:
                db.session.add(QuizQuestion(
                    question_text=question_text,
                    option_a=a, option_b=b, option_c=c, option_d=d,
                    correct_option=correct,
                    explanation=explanation,
                    category_id=category.id
                ))
                created_questions += 1

    db.session.commit()
    print(f"Done. Created {created_categories} new categories and {created_questions} new questions.")
