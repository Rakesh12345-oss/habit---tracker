from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = "secret123"

DB_NAME = "database.db"

# ---------------- BAD HABITS LIST ----------------
bad_habits = [
    "procrastination",
    "overthinking",
    "too much mobile use",
    "sleeping late",
    "laziness"
]

# ---------------- DB CONNECTION ----------------
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- INIT DB ----------------
def init_db():
    with get_db() as conn:
        cur = conn.cursor()

        # USERS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
        """)

        # HABITS (UPDATED)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            streak INTEGER DEFAULT 0,
            is_bad INTEGER DEFAULT 0,
            bad_count INTEGER DEFAULT 0
        )
        """)

        # LOGS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER,
            date TEXT
        )
        """)

        # 🔥 Auto add columns if missing (important)
        try:
            cur.execute("ALTER TABLE habits ADD COLUMN is_bad INTEGER DEFAULT 0")
        except:
            pass

        try:
            cur.execute("ALTER TABLE habits ADD COLUMN bad_count INTEGER DEFAULT 0")
        except:
            pass

init_db()

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("login"))

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return "Please fill all fields"

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE username=? AND password=?",
                (username, password)
            )
            user = cur.fetchone()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        return "Invalid username or password"

    return render_template("login.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return "Username and password cannot be empty"

        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users(username, password) VALUES (?, ?)",
                    (username, password)
                )
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return "Username already exists"

    return render_template("register.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))

    result = []

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT * FROM habits WHERE user_id=?", (user_id,))
        habits = cur.fetchall()

        for h in habits:
            # today status
            cur.execute(
                "SELECT 1 FROM logs WHERE habit_id=? AND date=?",
                (h["id"], today)
            )
            done = cur.fetchone()

            # last 7 days
            cur.execute("""
            SELECT date FROM logs 
            WHERE habit_id=? 
            ORDER BY date DESC LIMIT 7
            """, (h["id"],))
            dates = [row["date"] for row in cur.fetchall()]

            # yesterday check
            cur.execute(
                "SELECT 1 FROM logs WHERE habit_id=? AND date=?",
                (h["id"], yesterday)
            )
            yesterday_done = cur.fetchone()

            # reset streak
            if not yesterday_done and h["streak"] != 0:
                cur.execute(
                    "UPDATE habits SET streak=0 WHERE id=?",
                    (h["id"],)
                )

            result.append({
                "id": h["id"],
                "name": h["name"],
                "done": bool(done),
                "streak": h["streak"],
                "history": dates,
                "is_bad": h["is_bad"],
                "bad_count": h["bad_count"]
            })

    total = len(result)
    completed = sum(1 for r in result if r["done"])
    progress = int((completed / total) * 100) if total > 0 else 0

    return render_template(
        "dashboard.html",
        habits=result,
        progress=progress,
        user=session["username"]
    )

# ---------------- ADD HABIT ----------------
@app.route("/add_habit", methods=["POST"])
def add_habit():
    if "user_id" not in session:
        return redirect(url_for("login"))

    name = request.form.get("habit_name", "").lower().strip()

    if name:
        is_bad = 1 if name in bad_habits else 0

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO habits (user_id, name, streak, is_bad, bad_count)
                VALUES (?, ?, 0, ?, ?)
            """, (
                session["user_id"],
                name,
                is_bad,
                1 if is_bad else 0
            ))

    return redirect(url_for("dashboard"))

# ---------------- COMPLETE ----------------
@app.route("/complete/<int:habit_id>")
def complete(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))

    with get_db() as conn:
        cur = conn.cursor()

        # already done?
        cur.execute(
            "SELECT 1 FROM logs WHERE habit_id=? AND date=?",
            (habit_id, today)
        )

        if not cur.fetchone():
            cur.execute(
                "INSERT INTO logs(habit_id, date) VALUES (?, ?)",
                (habit_id, today)
            )

            # check yesterday
            cur.execute(
                "SELECT 1 FROM logs WHERE habit_id=? AND date=?",
                (habit_id, yesterday)
            )

            if cur.fetchone():
                cur.execute(
                    "UPDATE habits SET streak = streak + 1 WHERE id=?",
                    (habit_id,)
                )
            else:
                cur.execute(
                    "UPDATE habits SET streak = 1 WHERE id=?",
                    (habit_id,)
                )

            # 🔥 increment bad habit frequency
            cur.execute("SELECT is_bad FROM habits WHERE id=?", (habit_id,))
            habit = cur.fetchone()

            if habit and habit["is_bad"]:
                cur.execute(
                    "UPDATE habits SET bad_count = bad_count + 1 WHERE id=?",
                    (habit_id,)
                )

    return redirect(url_for("dashboard"))

# ---------------- DELETE ----------------
@app.route("/delete/<int:habit_id>")
def delete(habit_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM habits WHERE id=? AND user_id=?",
            (habit_id, session["user_id"])
        )
        cur.execute("DELETE FROM logs WHERE habit_id=?", (habit_id,))

    return redirect(url_for("dashboard"))

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)