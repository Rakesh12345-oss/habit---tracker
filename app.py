from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
DATABASE = 'habits.db'


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            streak INTEGER DEFAULT 0,
            last_done_date TEXT,
            target_frequency TEXT DEFAULT 'Daily',
            reminder TEXT DEFAULT '',
            habit_type TEXT DEFAULT 'good',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )"""
    )

    columns = [row[1] for row in conn.execute("PRAGMA table_info(habits)").fetchall()]
    if 'user_id' not in columns:
        conn.execute("ALTER TABLE habits ADD COLUMN user_id INTEGER")
    if 'streak' not in columns:
        conn.execute("ALTER TABLE habits ADD COLUMN streak INTEGER DEFAULT 0")
    if 'last_done_date' not in columns:
        conn.execute("ALTER TABLE habits ADD COLUMN last_done_date TEXT")
    if 'target_frequency' not in columns:
        conn.execute("ALTER TABLE habits ADD COLUMN target_frequency TEXT DEFAULT 'Daily'")
    if 'reminder' not in columns:
        conn.execute("ALTER TABLE habits ADD COLUMN reminder TEXT DEFAULT ''")
    if 'habit_type' not in columns:
        conn.execute("ALTER TABLE habits ADD COLUMN habit_type TEXT DEFAULT 'good'")

    conn.commit()
    conn.close()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user


def refresh_daily_statuses(user_id):
    today = date.today().isoformat()
    conn = get_db_connection()
    conn.execute(
        "UPDATE habits SET status = 'Not Done'"
        " WHERE user_id = ? AND status = 'Done' AND (last_done_date IS NULL OR last_done_date != ?)",
        (user_id, today)
    )
    conn.commit()
    conn.close()


@app.route('/')
@login_required
def home():
    user = get_current_user()
    refresh_daily_statuses(user['id'])
    conn = get_db_connection()
    habits = conn.execute('SELECT * FROM habits WHERE user_id = ? ORDER BY habit_type DESC, id DESC', (user['id'],)).fetchall()
    conn.close()

    today = date.today().isoformat()
    today_count = sum(1 for habit in habits if habit['last_done_date'] == today)
    longest_streak = max((habit['streak'] or 0) for habit in habits) if habits else 0
    
    good_habits = [h for h in habits if h['habit_type'] in ('good', None)]
    bad_habits = [h for h in habits if h['habit_type'] == 'bad']

    return render_template(
        'index.html',
        good_habits=good_habits,
        bad_habits=bad_habits,
        user=user,
        today_count=today_count,
        longest_streak=longest_streak
    )


@app.route('/add', methods=['POST'])
@login_required
def add_habit():
    name = request.form.get('name', '').strip()
    frequency = request.form.get('target_frequency', 'Daily')
    reminder = request.form.get('reminder', '').strip()
    habit_type = request.form.get('habit_type', 'good')
    if name:
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO habits (user_id, name, status, streak, last_done_date, target_frequency, reminder, habit_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (session['user_id'], name, 'Not Done', 0, None, frequency, reminder, habit_type)
        )
        conn.commit()
        conn.close()
    return redirect(url_for('home'))


@app.route('/edit/<int:habit_id>', methods=['GET', 'POST'])
@login_required
def edit_habit(habit_id):
    user = get_current_user()
    conn = get_db_connection()
    habit = conn.execute(
        'SELECT * FROM habits WHERE id = ? AND user_id = ?',
        (habit_id, user['id'])
    ).fetchone()
    if not habit:
        conn.close()
        return redirect(url_for('home'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        status = request.form.get('status', 'Not Done')
        frequency = request.form.get('target_frequency', 'Daily')
        reminder = request.form.get('reminder', '').strip()
        habit_type = request.form.get('habit_type', 'good')
        if name:
            conn.execute(
                'UPDATE habits SET name = ?, status = ?, target_frequency = ?, reminder = ?, habit_type = ? WHERE id = ? AND user_id = ?',
                (name, status, frequency, reminder, habit_type, habit_id, user['id'])
            )
            conn.commit()
        conn.close()
        return redirect(url_for('home'))

    conn.close()
    return render_template('edit.html', habit=habit, user=user)


@app.route('/delete/<int:habit_id>', methods=['POST'])
@login_required
def delete_habit(habit_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM habits WHERE id = ? AND user_id = ?', (habit_id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.route('/done/<int:habit_id>', methods=['POST'])
@login_required
def mark_done(habit_id):
    conn = get_db_connection()
    habit = conn.execute(
        'SELECT streak, last_done_date FROM habits WHERE id = ? AND user_id = ?',
        (habit_id, session['user_id'])
    ).fetchone()

    if habit:
        today = date.today()
        streak = habit['streak'] or 0
        last_date = None
        if habit['last_done_date']:
            try:
                last_date = date.fromisoformat(habit['last_done_date'])
            except ValueError:
                last_date = None

        if last_date == today:
            new_streak = streak
        elif last_date == today - timedelta(days=1):
            new_streak = streak + 1
        else:
            new_streak = 1

        conn.execute(
            "UPDATE habits SET status = 'Done', streak = ?, last_done_date = ? WHERE id = ? AND user_id = ?",
            (new_streak, today.isoformat(), habit_id, session['user_id'])
        )
        conn.commit()

    conn.close()
    return redirect(url_for('home'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('home'))

        flash('Invalid username or password.')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Username and password are required.')
        else:
            conn = get_db_connection()
            existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if existing:
                flash('Username already exists.')
            else:
                password_hash = generate_password_hash(password)
                conn.execute(
                    'INSERT INTO users (username, password) VALUES (?, ?)',
                    (username, password_hash)
                )
                conn.commit()
                conn.close()
                flash('Account created successfully. Please log in.')
                return redirect(url_for('login'))
            conn.close()

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))
import os

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
