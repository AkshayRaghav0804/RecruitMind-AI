"""SQLite storage layer."""
import json
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "recruit.db")


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT, name TEXT, email TEXT, phone TEXT,
                skills TEXT DEFAULT '[]', years_experience REAL DEFAULT 0,
                education TEXT, summary TEXT, raw_text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, description TEXT,
                required_skills TEXT DEFAULT '[]', min_experience REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER, candidate_id INTEGER,
                score REAL, skill_score REAL, text_score REAL, exp_score REAL,
                matched_skills TEXT, missing_skills TEXT, explanation TEXT,
                UNIQUE(job_id, candidate_id)
            );
            """
        )


def row(r: sqlite3.Row | None, json_fields=("skills", "required_skills", "matched_skills", "missing_skills")):
    if r is None:
        return None
    d = dict(r)
    for f in json_fields:
        if f in d and isinstance(d[f], str):
            d[f] = json.loads(d[f] or "[]")
    return d
