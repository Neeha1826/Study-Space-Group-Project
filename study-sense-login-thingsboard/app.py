from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'students.db'
STATIC_DIR = BASE_DIR / 'static'

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'change-this-to-a-random-secret-key')

THINGSBOARD_HOST = os.environ.get('THINGSBOARD_HOST', '').rstrip('/')
THINGSBOARD_USERNAME = os.environ.get('THINGSBOARD_USERNAME', '')
THINGSBOARD_PASSWORD = os.environ.get('THINGSBOARD_PASSWORD', '')

STUDY_SPACES = [
    {
        'id': 'assl',
        'deviceId': os.environ.get('TB_DEVICE_ASSL', ''),
        'name': 'Arts and Social Studies Library',
        'address': 'Colum Dr, Cardiff',
        'postcode': 'CF10 3LB',
    },
    {
        'id': 'abacws',
        'deviceId': os.environ.get('TB_DEVICE_ABACWS', ''),
        'name': 'Abacws',
        'address': 'Senghennydd Rd, Cardiff',
        'postcode': 'CF24 4AG',
    },
    {
        'id': 'mainlib',
        'deviceId': os.environ.get('TB_DEVICE_MAINLIB', ''),
        'name': 'Main Library',
        'address': 'The Parade, Cardiff',
        'postcode': 'CF10 3AY',
    },
    {
        'id': 'talybont',
        'deviceId': os.environ.get('TB_DEVICE_TALYBONT', ''),
        'name': 'Talybont Study Hub',
        'address': 'Talybont North, Cardiff',
        'postcode': 'CF14 3AX',
    },
]

TELEMETRY_KEYS = [
    'occupied', 'capacity', 'temperature', 'tempC', 'humidity',
    'noiseDb', 'noise', 'cameraOnline', 'cameraConfidence', 'cameraModel'
]

_tb_token: str | None = None


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


def require_login() -> dict[str, Any] | Any:
    user = current_user()
    if not user:
        return jsonify({'ok': False, 'message': 'Please log in first.'}), 401
    return user


def tb_is_configured() -> bool:
    return bool(THINGSBOARD_HOST and THINGSBOARD_USERNAME and THINGSBOARD_PASSWORD)


def tb_login() -> str:
    global _tb_token
    if not tb_is_configured():
        raise RuntimeError('ThingsBoard is not configured on the Flask backend.')

    response = requests.post(
        f'{THINGSBOARD_HOST}/api/auth/login',
        json={'username': THINGSBOARD_USERNAME, 'password': THINGSBOARD_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    token = response.json().get('token')
    if not token:
        raise RuntimeError('ThingsBoard login did not return a JWT token.')
    _tb_token = token
    return token


def tb_get(path: str) -> Any:
    global _tb_token
    if not _tb_token:
        tb_login()

    response = requests.get(
        f'{THINGSBOARD_HOST}{path}',
        headers={'X-Authorization': f'Bearer {_tb_token}'},
        timeout=10,
    )

    if response.status_code == 401:
        tb_login()
        response = requests.get(
            f'{THINGSBOARD_HOST}{path}',
            headers={'X-Authorization': f'Bearer {_tb_token}'},
            timeout=10,
        )

    response.raise_for_status()
    return response.json()


def tb_value(raw: dict[str, Any], key: str, fallback: Any = None) -> Any:
    item = (raw.get(key) or [None])[0]
    if not item:
        return fallback
    value = item.get('value')
    if value == 'true':
        return True
    if value == 'false':
        return False
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def tb_ts(raw: dict[str, Any], key: str) -> int | None:
    item = (raw.get(key) or [None])[0]
    return item.get('ts') if item else None


def seconds_since(ts: int | None) -> int:
    if not ts:
        return 999999
    return max(0, int((time.time() * 1000 - int(ts)) / 1000))


def build_space(space: dict[str, str], raw: dict[str, Any]) -> dict[str, Any]:
    occupied = tb_value(raw, 'occupied', 0)
    capacity = tb_value(raw, 'capacity', 0)
    temp = tb_value(raw, 'temperature', tb_value(raw, 'tempC', 0))
    noise = tb_value(raw, 'noiseDb', tb_value(raw, 'noise', 0))
    last_seen_sec = min(
        seconds_since(tb_ts(raw, 'occupied')),
        seconds_since(tb_ts(raw, 'temperature')),
        seconds_since(tb_ts(raw, 'noiseDb')),
    )

    return {
        **space,
        'occupied': int(float(occupied or 0)),
        'capacity': int(float(capacity or 0)),
        'tempC': float(temp or 0),
        'humidity': float(tb_value(raw, 'humidity', 0) or 0),
        'noiseDb': float(noise or 0),
        'camera': {
            'online': bool(tb_value(raw, 'cameraOnline', last_seen_sec < 60)),
            'model': str(tb_value(raw, 'cameraModel', 'ThingsBoard device')),
            'confidence': float(tb_value(raw, 'cameraConfidence', 1) or 0),
            'lastSeenSec': last_seen_sec,
        },
        'rawTelemetry': raw,
    }


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


@app.get('/api/spaces')
def get_spaces() -> Any:
    user = require_login()
    if not isinstance(user, dict):
        return user

    configured_spaces = [s for s in STUDY_SPACES if s.get('deviceId')]
    if not tb_is_configured() or not configured_spaces:
        return jsonify({
            'ok': False,
            'message': 'ThingsBoard backend is not configured yet.',
            'spaces': [],
        }), 503

    try:
        spaces = []
        keys = ','.join(TELEMETRY_KEYS)
        for space in configured_spaces:
            raw = tb_get(f'/api/plugins/telemetry/DEVICE/{space["deviceId"]}/values/timeseries?keys={keys}')
            spaces.append(build_space(space, raw))
        return jsonify({'ok': True, 'spaces': spaces})
    except requests.RequestException as exc:
        return jsonify({'ok': False, 'message': f'ThingsBoard request failed: {exc}'}), 502
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 500


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
