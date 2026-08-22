import os

from cs50 import SQL
from flask import Flask, redirect, render_template, request, session, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") 


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "satmath.db")
db = SQL(f"sqlite:///{DATABASE_PATH}")

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


def error(message, code=400):
    return render_template("error.html", message=message, code=code), code


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["POST", "GET"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username:
            return error("Username is required", 400)
        if not password:
            return error("Password is required", 400)
        if not confirmation:
            return error("Confirmation is required", 400)
        if password != confirmation:
            return error("Password and Confirmation must match", 400)
        rows = db.execute(
            " SELECT id FROM users WHERE username = ? ", username
        )
        if len(rows) != 0:
            return error("Username already exists ")

        password_hash = generate_password_hash(password)
        user_id = db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?) ", username, password_hash
        )

        session["user_id"] = user_id
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return error("Must provide a username", 403)
        if not request.form.get("password"):
            return error("Must provide a password", 403)
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get(
                "username")
        )

        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return error("Invalid username and/or password", 403)
        session["user_id"] = rows[0]["id"]
        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/practice")
@login_required
def practice():
    return render_template("practice.html")


domains = {
    "algebra": "Algebra",
    "advanced-math": "Advanced Math",
    "problem-solving": "Problem-Solving & Data Analysis",
    "geometry": "Geometry & Trigonometry"
}


@app.route("/practice/<domain>")
@login_required
def practice_domain(domain):

    if domain not in domains:
        return error("Invalid domain", 404)

    questions = db.execute(
        """SELECT * FROM questions
           WHERE domain = ?
           ORDER BY RANDOM()
           LIMIT 10""",
        domains[domain]
    )

    if len(questions) == 0:
        return error("No questions available", 404)

    question_ids = []

    for question in questions:
        question_ids.append(question["id"])

    session["practice_questions"] = question_ids
    session["current_question"] = 0
    session["score"] = 0
    session["practice_domain"] = domains[domain]

    return redirect(f"/question/{question_ids[0]}")


@app.route("/question/<int:question_id>", methods=["GET", "POST"])
@login_required
def question(question_id):
    practice_questions = session.get("practice_questions")
    current = session.get("current_question")

    # The user must start from the practice page.
    if practice_questions is None or current is None:
        return redirect("/practice")

    # The session is already complete.
    if current >= len(practice_questions):
        return redirect("/results")

    # Only allow the question expected by the current session.
    expected_question_id = practice_questions[current]
    if question_id != expected_question_id:
        return redirect(
            url_for("question", question_id=expected_question_id)
        )

    rows = db.execute(
        "SELECT * FROM questions WHERE id = ?",
        question_id
    )

    if len(rows) != 1:
        return error("Question not found", 404)

    question = rows[0]

    if request.method == "POST":
        selected_answer = request.form.get("answer")

        if selected_answer not in ["A", "B", "C", "D"]:
            return error("Please select a valid answer", 400)

        is_correct = selected_answer == question["correct_answer"]

        db.execute(
            """
            INSERT INTO attempts
                (user_id, question_id, selected_answer, is_correct)
            VALUES (?, ?, ?, ?)
            """,
            session["user_id"],
            question_id,
            selected_answer,
            is_correct
        )

        if is_correct:
            session["score"] += 1

        session["current_question"] += 1

        # Save feedback in the session before redirecting.
        session["feedback"] = {
            "question_id": question_id,
            "selected_answer": selected_answer,
            "is_correct": is_correct
        }

        return redirect("/feedback")

    return render_template(
        "question.html",
        question=question,
        selected_answer=None,
        is_correct=None,
        next_question_id=None
    )

@app.route("/feedback")
@login_required
def feedback():
    feedback_data = session.get("feedback")
    practice_questions = session.get("practice_questions")
    current = session.get("current_question")

    if (
        feedback_data is None
        or practice_questions is None
        or current is None
    ):
        return redirect("/practice")

    rows = db.execute(
        "SELECT * FROM questions WHERE id = ?",
        feedback_data["question_id"]
    )

    if len(rows) != 1:
        return error("Question not found", 404)

    question = rows[0]

    if current < len(practice_questions):
        next_question_id = practice_questions[current]
    else:
        next_question_id = None

    return render_template(
        "question.html",
        question=question,
        selected_answer=feedback_data["selected_answer"],
        is_correct=feedback_data["is_correct"],
        next_question_id=next_question_id
    )

@app.route("/dashboard")
@login_required
def dashboard():
    summary_rows = db.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(is_correct), 0) AS correct
        FROM attempts
        WHERE user_id = ?
        """,
        session["user_id"]
    )

    summary = summary_rows[0]
    total = summary["total"]
    correct = summary["correct"]

    if total > 0:
        percentage = round(correct * 100 / total)
    else:
        percentage = 0

    domains = db.execute(
        """
        SELECT
            questions.domain,
            COUNT(*) AS total,
            SUM(attempts.is_correct) AS correct
        FROM attempts
        JOIN questions
            ON attempts.question_id = questions.id
        WHERE attempts.user_id = ?
        GROUP BY questions.domain
        ORDER BY questions.domain
        """,
        session["user_id"]
    )

    recent_attempts = db.execute(
        """
        SELECT
            questions.domain,
            questions.question,
            attempts.selected_answer,
            attempts.is_correct,
            attempts.attempted_at
        FROM attempts
        JOIN questions
            ON attempts.question_id = questions.id
        WHERE attempts.user_id = ?
        ORDER BY attempts.attempted_at DESC
        LIMIT 10
        """,
        session["user_id"]
    )

    return render_template(
        "dashboard.html",
        total=total,
        correct=correct,
        percentage=percentage,
        domains=domains,
        recent_attempts=recent_attempts
    )

@app.route("/results")
@login_required
def results():
    score = session.get("score")
    questions = session.get("practice_questions")
    domain = session.get("practice_domain")
    current = session.get("current_question")

    if (
        score is None
        or questions is None
        or domain is None
        or current is None
    ):
        return redirect(url_for("practice"))

    if current < len(questions):
        return redirect(
            url_for("question", question_id=questions[current])
        )

    total = len(questions)

    if total == 0:
        return redirect("/practice")
    percentage = round((score * 100) / total)

    return render_template(
        "results.html",
        score = score,
        total = total,
        percentage = percentage,
        domain = domain
    )


