import os
import json
import time
import hmac
import hashlib
import sqlite3
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "anistorm.db")


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS shadow_points (
            telegram_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 1000,
            total_earned INTEGER NOT NULL DEFAULT 1000,
            total_spent INTEGER NOT NULL DEFAULT 0,
            games_played INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.commit()
    db.close()


def validate_telegram_init_data(init_data):
    bot_token = os.getenv("BOT_TOKEN", "").strip()

    if not bot_token:
        return None, "BOT_TOKEN تنظیم نشده"

    if not init_data:
        return None, "initData ارسال نشده"

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None, "initData نامعتبر است"

    received_hash = parsed.pop("hash", None)

    if not received_hash:
        return None, "hash وجود ندارد"

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(parsed.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None, "اعتبارسنجی Telegram ناموفق بود"

    auth_date = parsed.get("auth_date")

    if auth_date:
        try:
            auth_time = int(auth_date)

            if time.time() - auth_time > 86400:
                return None, "initData منقضی شده است"

        except ValueError:
            return None, "auth_date نامعتبر است"

    user_raw = parsed.get("user")

    if not user_raw:
        return None, "اطلاعات کاربر Telegram وجود ندارد"

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None, "اطلاعات کاربر نامعتبر است"

    telegram_id = user.get("id")

    if not telegram_id:
        return None, "Telegram ID پیدا نشد"

    return {
        "telegram_id": int(telegram_id),
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name")
    }, None


def get_current_user():
    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    ).strip()

    if not init_data:
        return None, "هدر Telegram ارسال نشده"

    return validate_telegram_init_data(init_data)


@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "service": "AniStorm API",
        "status": "online"
    })


@app.get("/api/shadow/status")
def shadow_status():
    return jsonify({
        "ok": True,
        "service": "Shadow Arcade",
        "status": "online"
    })


@app.get("/api/me")
def me():
    user, error = get_current_user()

    if error:
        return jsonify({
            "ok": False,
            "error": error
        }), 401

    db = get_db()

    db.execute("""
        INSERT INTO users
        (telegram_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = CURRENT_TIMESTAMP
    """, (
        user["telegram_id"],
        user["username"],
        user["first_name"],
        user["last_name"]
    ))

    db.execute("""
        INSERT OR IGNORE INTO shadow_points
        (telegram_id, balance, total_earned, total_spent, games_played)
        VALUES (?, 1000, 1000, 0, 0)
    """, (user["telegram_id"],))

    db.commit()

    shadow = db.execute("""
        SELECT
            balance,
            total_earned,
            total_spent,
            games_played
        FROM shadow_points
        WHERE telegram_id = ?
    """, (user["telegram_id"],)).fetchone()

    db.close()

    return jsonify({
        "ok": True,
        "user": {
            "telegram_id": user["telegram_id"],
            "username": user["username"],
            "first_name": user["first_name"],
            "last_name": user["last_name"]
        },
        "shadow_points": {
            "balance": shadow["balance"],
            "total_earned": shadow["total_earned"],
            "total_spent": shadow["total_spent"],
            "games_played": shadow["games_played"]
        }
    })


@app.get("/api/shadow/balance")
def shadow_balance():
    user, error = get_current_user()

    if error:
        return jsonify({
            "ok": False,
            "error": error
        }), 401

    db = get_db()

    db.execute("""
        INSERT OR IGNORE INTO shadow_points
        (telegram_id, balance, total_earned, total_spent, games_played)
        VALUES (?, 1000, 1000, 0, 0)
    """, (user["telegram_id"],))

    db.commit()

    shadow = db.execute("""
        SELECT
            balance,
            total_earned,
            total_spent,
            games_played
        FROM shadow_points
        WHERE telegram_id = ?
    """, (user["telegram_id"],)).fetchone()

    db.close()

    return jsonify({
        "ok": True,
        "telegram_id": user["telegram_id"],
        "shadow_points": {
            "balance": shadow["balance"],
            "total_earned": shadow["total_earned"],
            "total_spent": shadow["total_spent"],
            "games_played": shadow["games_played"]
        }
    })


init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )
