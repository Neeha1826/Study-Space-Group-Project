from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

from spaces_service import build_spaces_payload
from thingsboard_client import ThingsBoardClient

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'students.db'
STATIC_DIR = BASE_DIR / 'static'

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path='')
app.config['SECRET_KEY'] = 'change-this-to-a-random-secret-key'

_TB_CLIENT: ThingsBoardClient | None = None
_TB_RESOLVED: bool = False


def get_thingsboard_client() -> ThingsBoardClient | None:
    """Singleton from environment variables; returns None if not configured."""
    global _TB_CLIENT, _TB_RESOLVED
    if _TB_RESOLVED:
        return _TB_CLIENT
    _TB_RESOLVED = True
    url = os.environ.get('THINGSBOARD_URL', '').strip()
    user = os.environ.get('THINGSBOARD_USERNAME', '').strip()
    pw = os.environ.get('THINGSBOARD_PASSWORD', '').strip()
    if not (url and user and pw):
        return None
    verify = os.environ.get('THINGSBOARD_VERIFY_SSL', '1').strip().lower() in ('1', 'true', 'yes', 'on')
    _TB_CLIENT = ThingsBoardClient(
        url,
        user,
        pw,
        verify_ssl=verify,
    )
    return _TB_CLIENT


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL UNIQUE,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            course TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()
    conn.close()


def current_user() -> dict[str, Any] | None:
    user_id = session.get('user_id')
    if not user_id:
        return None

    conn = get_db()
    row = conn.execute(
        'SELECT id, student_id, first_name, last_name, email, course FROM students WHERE id = ?',
        (user_id,),
    ).fetchone()
    conn.close()

    if not row:
        session.clear()
        return None

    return dict(row)


@app.route('/')
def index() -> Any:
    return send_from_directory(STATIC_DIR, 'index.html')


@app.post('/api/register')
def register() -> Any:
    data = request.get_json(silent=True) or {}

    first_name = str(data.get('firstName', '')).strip()
    last_name = str(data.get('lastName', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    student_id = str(data.get('studentId', '')).strip().upper()
    course = str(data.get('course', '')).strip()
    password = str(data.get('password', ''))

    if not all([first_name, last_name, email, student_id, course, password]):
        return jsonify({'ok': False, 'message': 'Please complete all registration fields.'}), 400

    if '@' not in email or '.' not in email:
        return jsonify({'ok': False, 'message': 'Please enter a valid email address.'}), 400

    if len(password) < 6:
        return jsonify({'ok': False, 'message': 'Password must be at least 6 characters.'}), 400

    password_hash = generate_password_hash(password)

    conn = get_db()
    try:
        cur = conn.execute(
            '''
            INSERT INTO students (student_id, first_name, last_name, email, password_hash, course)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (student_id, first_name, last_name, email, password_hash, course),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'ok': False, 'message': 'This email or student ID is already registered.'}), 409

    row = conn.execute(
        'SELECT id, student_id, first_name, last_name, email, course FROM students WHERE id = ?',
        (user_id,),
    ).fetchone()
    conn.close()

    session.clear()
    session['user_id'] = row['id']

    return jsonify({'ok': True, 'message': 'Registration successful.', 'user': dict(row)})


@app.post('/api/login')
def login() -> Any:
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))

    if not email or not password:
        return jsonify({'ok': False, 'message': 'Please enter email and password.'}), 400

    conn = get_db()
    row = conn.execute(
        'SELECT id, student_id, first_name, last_name, email, password_hash, course FROM students WHERE email = ?',
        (email,),
    ).fetchone()
    conn.close()

    if not row or not check_password_hash(row['password_hash'], password):
        return jsonify({'ok': False, 'message': 'Incorrect email or password.'}), 401

    session.clear()
    session['user_id'] = row['id']

    return jsonify({
        'ok': True,
        'message': 'Login successful.',
        'user': {
            'id': row['id'],
            'student_id': row['student_id'],
            'first_name': row['first_name'],
            'last_name': row['last_name'],
            'email': row['email'],
            'course': row['course'],
        },
    })


@app.post('/api/logout')
def logout() -> Any:
    session.clear()
    return jsonify({'ok': True, 'message': 'Logged out successfully.'})


@app.get('/api/session')
def get_session() -> Any:
    user = current_user()
    return jsonify({'ok': True, 'authenticated': bool(user), 'user': user})


@app.get('/api/students/me')
def get_profile() -> Any:
    user = current_user()
    if not user:
        return jsonify({'ok': False, 'message': 'Please log in first.'}), 401
    return jsonify({'ok': True, 'user': user})


@app.get('/api/spaces/live')
def spaces_live() -> Any:
    """
    Merge ThingsBoard telemetry with local metadata. Keys must match the Pi (e.g. CAPACITY = people count).
    See data/spaces_map.json and THINGSBOARD_URL / THINGSBOARD_USERNAME / THINGSBOARD_PASSWORD.
    """
    tb = get_thingsboard_client()
    try:
        spaces, source, err = build_spaces_payload(tb)
    except OSError as e:
        return jsonify({'ok': False, 'message': str(e), 'source': 'error', 'spaces': []}), 500
    return jsonify({
        'ok': True,
        'source': source,
        'thingsboardConfigured': bool(tb),
        'warning': err,
        'spaces': spaces,
    })


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
