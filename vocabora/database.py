"""SQLite persistence, safe schema migration, vocabulary import, and learning history."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from vocabora.data import DEFAULT_WORDS, VOCABULARY_FILE, normalize_word

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "vocabora.db"
DEFAULT_DB_PATH = DB_PATH.resolve()
LEGACY_CUSTOM_FILE = PROJECT_DIR / "custom_words.json"
LEGACY_REVIEW_FILE = PROJECT_DIR / "review_words.json"
LEGACY_DB_PATH = PROJECT_DIR / "vocabora_data.db"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


@contextmanager
def _connect():
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, sql_type: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def _get_meta(conn: sqlite3.Connection, key: str, default: str = "0") -> str:
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def _insert_word(conn: sqlite3.Connection, raw: Mapping[str, Any], *, is_custom: int = 0, allow_duplicate: bool = True) -> int | None:
    item = normalize_word(dict(raw))
    existing = conn.execute("SELECT id FROM words WHERE word=? COLLATE NOCASE", (item["word"],)).fetchone()
    if existing:
        word_id = int(existing["id"])
        # Enrich missing metadata only; do not silently overwrite saved meanings or examples.
        conn.execute(
            "UPDATE words SET pos=CASE WHEN pos='' THEN ? ELSE pos END, "
            "cefr=CASE WHEN cefr='' OR cefr IS NULL THEN ? ELSE cefr END, "
            "pronunciation=CASE WHEN pronunciation='' THEN ? ELSE pronunciation END, "
            "example=CASE WHEN example='' THEN ? ELSE example END, "
            "example_translation=CASE WHEN example_translation='' THEN ? ELSE example_translation END, "
            "synonyms=CASE WHEN synonyms='' THEN ? ELSE synonyms END WHERE id=?",
            (item["pos"], item["cefr"], item["pronunciation"], item["example"], item["example_translation"], _json(item["synonyms"]), word_id),
        )
        return word_id if allow_duplicate else None
    cursor = conn.execute(
        "INSERT INTO words(word, meaning, category, example, is_custom, created_at, pos, cefr, pronunciation, example_translation, synonyms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item["word"], item["translation"], item["category"], item["example"], int(is_custom), _now(),
         item["pos"], item["cefr"], item["pronunciation"], item["example_translation"], _json(item["synonyms"])),
    )
    return int(cursor.lastrowid)


def initialize_database() -> None:
    """Create/migrate tables, then safely merge the bundled dictionary and legacy data."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE COLLATE NOCASE,
            meaning TEXT NOT NULL,
            category TEXT NOT NULL,
            example TEXT NOT NULL DEFAULT '',
            is_custom INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS quiz_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            total_questions INTEGER NOT NULL,
            correct INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'in_progress'
        );
        CREATE TABLE IF NOT EXISTS quiz_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
            question_index INTEGER NOT NULL,
            word_id INTEGER NOT NULL REFERENCES words(id),
            selected_answer TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            answered_at TEXT NOT NULL,
            UNIQUE(session_id, question_index)
        );
        CREATE TABLE IF NOT EXISTS mistakes (
            word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
            wrong_answer TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 1,
            last_wrong TEXT NOT NULL,
            reviewed INTEGER NOT NULL DEFAULT 0,
            reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS word_progress (
            word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'new',
            box INTEGER NOT NULL DEFAULT 0,
            due_at TEXT,
            last_reviewed TEXT,
            review_count INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS saved_words (
            word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
            saved_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_words_category ON words(category);
        CREATE INDEX IF NOT EXISTS idx_quiz_sessions_started ON quiz_sessions(started_at);
        CREATE INDEX IF NOT EXISTS idx_quiz_answers_session ON quiz_answers(session_id);
        CREATE INDEX IF NOT EXISTS idx_progress_due ON word_progress(due_at);
        """)

        # Older database versions may lack metadata columns used by this redesign.
        for column, sql_type in {
            "pos": "TEXT NOT NULL DEFAULT ''", "cefr": "TEXT NOT NULL DEFAULT ''",
            "pronunciation": "TEXT NOT NULL DEFAULT ''", "example_translation": "TEXT NOT NULL DEFAULT ''",
            "synonyms": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(conn, "words", column, sql_type)

        # Merge the bundled vocabulary only when its source file changes. This keeps normal
        # Streamlit reruns from performing 1,000+ unnecessary writes while preserving safe
        # one-time migration/enrichment of an existing user's database.
        try:
            seed_hash = hashlib.sha256(Path(VOCABULARY_FILE).read_bytes()).hexdigest()
        except OSError:
            seed_hash = ""
        if seed_hash and _get_meta(conn, "vocabulary_seed_hash", "") != seed_hash:
            for item in DEFAULT_WORDS:
                try:
                    _insert_word(conn, item, is_custom=0, allow_duplicate=True)
                except sqlite3.IntegrityError:
                    # One malformed/duplicate row should not prevent the rest of the data loading.
                    continue
            _set_meta(conn, "vocabulary_seed_hash", seed_hash)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_words_cefr ON words(cefr)")
        conn.execute("UPDATE words SET category='โรงเรียนและการศึกษา' WHERE category='การเรียน'")
        conn.execute("UPDATE words SET category='ธุรกิจและสำนักงาน' WHERE category='การทำงาน'")
        conn.execute("INSERT OR IGNORE INTO user_settings(key, value) VALUES('theme', 'light')")
        _set_meta(conn, "schema_version", "3")

        # Migrate legacy JSON files only once. The original files are never deleted or changed.
        if _get_meta(conn, "legacy_json_migrated", "0") != "1":
            _migrate_legacy_json(conn)
            _set_meta(conn, "legacy_json_migrated", "1")

        # The archive contains an older, separate statistics database. Read it only once and
        # leave that source database untouched. Skip this import when tests point DB_PATH elsewhere.
        try:
            current_db = Path(DB_PATH).resolve()
        except Exception:
            current_db = DEFAULT_DB_PATH
        if current_db == DEFAULT_DB_PATH and _get_meta(conn, "legacy_db_migrated", "0") != "1":
            _migrate_legacy_database(conn)
            _set_meta(conn, "legacy_db_migrated", "1")


def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
    custom_path = Path(LEGACY_CUSTOM_FILE)
    if custom_path.exists():
        try:
            payload = json.loads(custom_path.read_text(encoding="utf-8"))
            rows = payload.get("words", payload) if isinstance(payload, dict) else payload
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        try:
                            _insert_word(conn, row, is_custom=1, allow_duplicate=True)
                        except (ValueError, sqlite3.IntegrityError):
                            continue
        except (OSError, json.JSONDecodeError):
            pass
    review_path = Path(LEGACY_REVIEW_FILE)
    if review_path.exists():
        try:
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            rows = payload.get("words", payload) if isinstance(payload, dict) else payload
            if isinstance(rows, list):
                for raw in rows:
                    word = str(raw.get("word", "")).strip() if isinstance(raw, dict) else str(raw).strip()
                    if not word:
                        continue
                    row = conn.execute("SELECT id, meaning FROM words WHERE word=? COLLATE NOCASE", (word,)).fetchone()
                    if row:
                        conn.execute(
                            "INSERT INTO mistakes(word_id, wrong_answer, correct_answer, attempts, last_wrong, reviewed) "
                            "VALUES (?, '', ?, 1, ?, 0) ON CONFLICT(word_id) DO NOTHING",
                            (row["id"], row["meaning"], _now()),
                        )
        except (OSError, json.JSONDecodeError):
            pass


def _migrate_legacy_database(conn: sqlite3.Connection) -> None:
    old_path = Path(LEGACY_DB_PATH)
    if not old_path.exists() or old_path.resolve() == Path(DB_PATH).resolve():
        return
    try:
        legacy = sqlite3.connect(f"file:{old_path.resolve().as_posix()}?mode=ro", uri=True, timeout=2)
        legacy.row_factory = sqlite3.Row
    except sqlite3.Error:
        return
    try:
        names = {r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "stats" in names:
            try:
                stat = legacy.execute("SELECT total_questions, correct_answers FROM stats WHERE id=1").fetchone()
                if stat:
                    _set_meta(conn, "legacy_total_answered", str(int(stat["total_questions"] or 0)))
                    _set_meta(conn, "legacy_correct", str(int(stat["correct_answers"] or 0)))
            except sqlite3.Error:
                pass
        if "mistakes" in names:
            try:
                for old in legacy.execute("SELECT word, translation, correct_answer, attempts FROM mistakes"):
                    word = str(old["word"] or "").strip()
                    translation = str(old["translation"] or "").strip()
                    if not word or not translation:
                        continue
                    row = conn.execute("SELECT id FROM words WHERE word=? COLLATE NOCASE", (word,)).fetchone()
                    if row is None:
                        wid = _insert_word(conn, {"word": word, "translation": translation, "category": "คำศัพท์นำเข้า", "cefr": "A1"}, is_custom=1)
                    else:
                        wid = int(row["id"])
                    if wid:
                        conn.execute(
                            "INSERT INTO mistakes(word_id, wrong_answer, correct_answer, attempts, last_wrong, reviewed) "
                            "VALUES (?, ?, ?, ?, ?, 0) ON CONFLICT(word_id) DO UPDATE SET "
                            "attempts=MAX(mistakes.attempts, excluded.attempts)",
                            (wid, str(old["correct_answer"] or ""), translation, max(1, int(old["attempts"] or 1)), _now()),
                        )
            except sqlite3.Error:
                pass
    finally:
        legacy.close()


def init_db() -> None:
    """Compatibility alias for the original app."""
    initialize_database()


def add_word(word: str, meaning: str, category: str = "ชีวิตประจำวัน", example: str = "", *,
             pos: str = "", cefr: str = "A1", pronunciation: str = "", example_translation: str = "",
             synonyms: list[str] | str | None = None, is_custom: bool = True) -> int:
    word = str(word).strip()
    meaning = str(meaning).strip()
    if not word or not meaning:
        raise ValueError("กรุณากรอกคำศัพท์ภาษาอังกฤษและคำแปลภาษาไทย")
    syns = synonyms if synonyms is not None else []
    raw = {"word": word, "translation": meaning, "category": category or "ชีวิตประจำวัน", "example": example,
           "pos": pos, "cefr": cefr, "pronunciation": pronunciation,
           "example_translation": example_translation, "synonyms": syns}
    with _connect() as conn:
        exists = conn.execute("SELECT id FROM words WHERE word=? COLLATE NOCASE", (word,)).fetchone()
        if exists:
            raise ValueError(f"มีคำว่า ‘{word}’ อยู่ในคลังแล้ว")
        word_id = _insert_word(conn, raw, is_custom=int(is_custom), allow_duplicate=False)
        if word_id is None:
            raise ValueError(f"มีคำว่า ‘{word}’ อยู่ในคลังแล้ว")
        return word_id


def get_all_words(*, include_progress: bool = True) -> list[dict[str, Any]]:
    with _connect() as conn:
        query = """
            SELECT w.*, COALESCE(p.status, 'new') AS status, COALESCE(p.box, 0) AS box,
                   p.due_at, p.last_reviewed, COALESCE(p.review_count, 0) AS review_count,
                   COALESCE(p.correct_count, 0) AS correct_count, COALESCE(p.wrong_count, 0) AS wrong_count,
                   CASE WHEN s.word_id IS NULL THEN 0 ELSE 1 END AS is_saved
            FROM words w
            LEFT JOIN word_progress p ON p.word_id=w.id
            LEFT JOIN saved_words s ON s.word_id=w.id
            ORDER BY w.word COLLATE NOCASE
        """
        rows = conn.execute(query).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["translation"] = item.get("meaning", "")
        try:
            item["synonyms"] = json.loads(item.get("synonyms") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["synonyms"] = []
        result.append(item)
    return result


def get_word(word_id: int) -> dict[str, Any] | None:
    return next((w for w in get_all_words() if int(w["id"]) == int(word_id)), None)


def get_word_by_text(word: str) -> dict[str, Any] | None:
    target = str(word).casefold().strip()
    return next((w for w in get_all_words() if str(w["word"]).casefold() == target), None)


def get_categories() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM words WHERE TRIM(category)<>'' ORDER BY category COLLATE NOCASE").fetchall()
    return [str(r[0]) for r in rows]


def import_words(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    added = skipped = 0
    with _connect() as conn:
        for raw in rows:
            try:
                item = normalize_word(dict(raw))
            except ValueError:
                skipped += 1
                continue
            exists = conn.execute("SELECT 1 FROM words WHERE word=? COLLATE NOCASE", (item["word"],)).fetchone()
            if exists:
                # Enrich empty optional fields but don't overwrite meanings or examples.
                _insert_word(conn, item, is_custom=1, allow_duplicate=True)
                skipped += 1
                continue
            try:
                _insert_word(conn, item, is_custom=1, allow_duplicate=False)
                added += 1
            except (sqlite3.IntegrityError, ValueError):
                skipped += 1
    return {"added": added, "skipped": skipped}


def create_quiz_session(category: str, total_questions: int) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO quiz_sessions(category, started_at, total_questions, status) VALUES (?, ?, ?, 'in_progress')",
            (category or "ทั้งหมด", _now(), max(0, int(total_questions))),
        )
        return int(cur.lastrowid)


def record_answer(session_id: int, question_index: int, word_id: int, selected_answer: str,
                  correct_answer: str, is_correct: bool, score: int = 0, streak: int = 0) -> bool:
    """Record a quiz answer exactly once per session/question; return False on duplicate submit."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO quiz_answers(session_id, question_index, word_id, selected_answer, correct_answer, is_correct, answered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(session_id), int(question_index), int(word_id), str(selected_answer), str(correct_answer), int(bool(is_correct)), _now()),
        )
        if cur.rowcount != 1:
            return False
        conn.execute(
            "UPDATE quiz_sessions SET correct=correct+?, max_streak=MAX(max_streak, ?) WHERE id=?",
            (int(bool(is_correct)), max(0, int(streak)), int(session_id)),
        )
        existing = conn.execute("SELECT box, review_count, correct_count, wrong_count FROM word_progress WHERE word_id=?", (int(word_id),)).fetchone()
        now = _now()
        if is_correct:
            box = min(5, max(0, int(existing["box"] or 0)) + 1) if existing else 1
            interval_days = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}.get(box, 1)
            conn.execute("DELETE FROM mistakes WHERE word_id=?", (int(word_id),))
            due = (datetime.now().astimezone() + timedelta(days=interval_days)).isoformat(timespec="seconds")
            progress_status = "mastered" if box >= 4 else "learning"
            if existing:
                conn.execute(
                    "UPDATE word_progress SET status=?, box=?, due_at=?, last_reviewed=?, review_count=review_count+1, "
                    "correct_count=correct_count+1, updated_at=? WHERE word_id=?",
                    (progress_status, box, due, now, now, int(word_id))
                )
            else:
                conn.execute(
                    "INSERT INTO word_progress(word_id, status, box, due_at, last_reviewed, review_count, correct_count, wrong_count, updated_at) "
                    "VALUES (?, 'learning', 1, ?, ?, 1, 1, 0, ?)",
                    (int(word_id), due, now, now),
                )
        else:
            conn.execute(
                "INSERT INTO mistakes(word_id, wrong_answer, correct_answer, attempts, last_wrong, reviewed) VALUES (?, ?, ?, 1, ?, 0) "
                "ON CONFLICT(word_id) DO UPDATE SET wrong_answer=excluded.wrong_answer, correct_answer=excluded.correct_answer, "
                "attempts=mistakes.attempts+1, last_wrong=excluded.last_wrong, reviewed=0, reviewed_at=NULL",
                (int(word_id), str(selected_answer), str(correct_answer), now),
            )
            if existing:
                conn.execute(
                    "UPDATE word_progress SET status='learning', box=1, due_at=?, last_reviewed=?, review_count=review_count+1, "
                    "wrong_count=wrong_count+1, updated_at=? WHERE word_id=?",
                    (now, now, now, int(word_id)),
                )
            else:
                conn.execute(
                    "INSERT INTO word_progress(word_id, status, box, due_at, last_reviewed, review_count, correct_count, wrong_count, updated_at) "
                    "VALUES (?, 'learning', 1, ?, ?, 1, 0, 1, ?)",
                    (int(word_id), now, now, now),
                )
        return True


def finish_quiz_session(session_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE quiz_sessions SET completed_at=?, status='completed' WHERE id=?", (_now(), int(session_id)))


def get_stats() -> dict[str, int | float]:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS total, COALESCE(SUM(is_correct),0) AS correct FROM quiz_answers").fetchone()
        legacy_total = int(_get_meta(conn, "legacy_total_answered", "0"))
        legacy_correct = int(_get_meta(conn, "legacy_correct", "0"))
        total = int(row["total"] or 0) + legacy_total
        correct = int(row["correct"] or 0) + legacy_correct
        words_total = int(conn.execute("SELECT COUNT(*) FROM words").fetchone()[0])
        practiced = int(conn.execute("SELECT COUNT(*) FROM word_progress WHERE review_count>0 OR correct_count>0 OR wrong_count>0").fetchone()[0])
        mastered = int(conn.execute("SELECT COUNT(*) FROM word_progress WHERE status='mastered'").fetchone()[0])
        due = int(conn.execute("SELECT COUNT(*) FROM word_progress WHERE due_at IS NOT NULL AND due_at<=?", (_now(),)).fetchone()[0])
    incorrect = max(0, total - correct)
    return {
        "total_answered": total, "total_questions": total, "correct": correct, "correct_answers": correct,
        "incorrect": incorrect, "accuracy": (correct / total * 100) if total else 0.0,
        "words_total": words_total, "practiced_words": practiced, "mastered_words": mastered, "due_words": due,
    }


def update_stats(is_correct: bool) -> None:
    """Compatibility helper for older builds that did not track individual answers."""
    with _connect() as conn:
        total = int(_get_meta(conn, "legacy_total_answered", "0")) + 1
        correct = int(_get_meta(conn, "legacy_correct", "0")) + int(bool(is_correct))
        _set_meta(conn, "legacy_total_answered", str(total))
        _set_meta(conn, "legacy_correct", str(correct))


def add_mistake(word: str, translation: str, correct_answer: str = "", *, word_id: int | None = None) -> None:
    """Compatibility API: third argument is the previously selected/wrong answer."""
    target = get_word(int(word_id)) if word_id is not None else get_word_by_text(word)
    if target is None:
        try:
            new_id = add_word(word, translation, "ชีวิตประจำวัน", is_custom=True)
            target = get_word(new_id)
        except ValueError:
            target = get_word_by_text(word)
    if not target:
        return
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO mistakes(word_id, wrong_answer, correct_answer, attempts, last_wrong, reviewed) VALUES (?, ?, ?, 1, ?, 0) "
            "ON CONFLICT(word_id) DO UPDATE SET wrong_answer=excluded.wrong_answer, correct_answer=excluded.correct_answer, "
            "attempts=mistakes.attempts+1, last_wrong=excluded.last_wrong, reviewed=0, reviewed_at=NULL",
            (int(target["id"]), str(correct_answer or ""), str(translation or target["translation"]), now),
        )
        conn.execute(
            "INSERT INTO word_progress(word_id, status, box, due_at, last_reviewed, review_count, correct_count, wrong_count, updated_at) "
            "VALUES (?, 'learning', 1, ?, ?, 1, 0, 1, ?) ON CONFLICT(word_id) DO UPDATE SET status='learning', box=1, due_at=excluded.due_at, "
            "wrong_count=word_progress.wrong_count+1, updated_at=excluded.updated_at",
            (int(target["id"]), now, now, now),
        )


def get_mistakes(include_reviewed: bool = False) -> list[dict[str, Any]]:
    query = """
        SELECT w.id, w.word, w.meaning AS translation, m.wrong_answer, m.correct_answer,
               m.attempts, m.last_wrong, m.reviewed, m.reviewed_at, w.category, w.cefr
        FROM mistakes m JOIN words w ON w.id=m.word_id
    """
    if not include_reviewed:
        query += " WHERE m.reviewed=0"
    query += " ORDER BY m.last_wrong DESC, w.word COLLATE NOCASE"
    with _connect() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def remove_mistake(word: str | int) -> None:
    with _connect() as conn:
        if isinstance(word, int):
            conn.execute("DELETE FROM mistakes WHERE word_id=?", (word,))
        else:
            conn.execute("DELETE FROM mistakes WHERE word_id IN (SELECT id FROM words WHERE word=? COLLATE NOCASE)", (str(word),))


def record_review(word_id: int, remembered: bool) -> dict[str, Any]:
    """Leitner-style review: missed words return today; known words move to longer intervals."""
    now_dt = datetime.now().astimezone()
    now = now_dt.isoformat(timespec="seconds")
    intervals = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}
    with _connect() as conn:
        row = conn.execute("SELECT box, review_count, correct_count, wrong_count FROM word_progress WHERE word_id=?", (int(word_id),)).fetchone()
        previous_box = int(row["box"] or 0) if row else 0
        count = int(row["review_count"] or 0) if row else 0
        correct_count = int(row["correct_count"] or 0) if row else 0
        wrong_count = int(row["wrong_count"] or 0) if row else 0
        if remembered:
            box = min(5, max(1, previous_box + 1))
            due = (now_dt + timedelta(days=intervals[box])).isoformat(timespec="seconds")
            status = "mastered" if box >= 4 else "learning"
            correct_count += 1
            conn.execute("DELETE FROM mistakes WHERE word_id=?", (int(word_id),))
        else:
            box, due, status = 1, now, "learning"
            wrong_count += 1
            word = conn.execute("SELECT word, meaning FROM words WHERE id=?", (int(word_id),)).fetchone()
            if word:
                conn.execute(
                    "INSERT INTO mistakes(word_id, wrong_answer, correct_answer, attempts, last_wrong, reviewed) VALUES (?, '', ?, 1, ?, 0) "
                    "ON CONFLICT(word_id) DO UPDATE SET attempts=mistakes.attempts+1, last_wrong=excluded.last_wrong, reviewed=0, reviewed_at=NULL",
                    (int(word_id), word["meaning"], now),
                )
        count += 1
        conn.execute(
            "INSERT INTO word_progress(word_id, status, box, due_at, last_reviewed, review_count, correct_count, wrong_count, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(word_id) DO UPDATE SET status=excluded.status, box=excluded.box, due_at=excluded.due_at, "
            "last_reviewed=excluded.last_reviewed, review_count=excluded.review_count, correct_count=excluded.correct_count, wrong_count=excluded.wrong_count, updated_at=excluded.updated_at",
            (int(word_id), status, box, due, now, count, correct_count, wrong_count, now),
        )
    return {"status": status, "box": box, "due_at": due, "review_count": count}


def get_due_words(limit: int | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        query = """
            SELECT w.*, COALESCE(p.status, 'new') AS status, COALESCE(p.box,0) AS box, p.due_at,
                   COALESCE(p.review_count,0) AS review_count, 0 AS is_saved
            FROM word_progress p JOIN words w ON w.id=p.word_id
            WHERE p.due_at IS NOT NULL AND p.due_at<=? ORDER BY p.due_at, p.wrong_count DESC, w.word COLLATE NOCASE
        """
        params: tuple[Any, ...] = (_now(),)
        if limit is not None:
            query += " LIMIT ?"
            params = (_now(), max(0, int(limit)))
        rows = conn.execute(query, params).fetchall()
    result=[]
    for row in rows:
        item=dict(row); item["translation"]=item.get("meaning", "")
        try: item["synonyms"]=json.loads(item.get("synonyms") or "[]")
        except (TypeError, json.JSONDecodeError): item["synonyms"]=[]
        result.append(item)
    return result


def toggle_saved_word(word_id: int) -> bool:
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM saved_words WHERE word_id=?", (int(word_id),)).fetchone()
        if exists:
            conn.execute("DELETE FROM saved_words WHERE word_id=?", (int(word_id),))
            return False
        conn.execute("INSERT INTO saved_words(word_id, saved_at) VALUES (?, ?)", (int(word_id), _now()))
        return True


def save_word(word_id: int, saved: bool = True) -> None:
    with _connect() as conn:
        if saved:
            conn.execute("INSERT OR IGNORE INTO saved_words(word_id, saved_at) VALUES (?, ?)", (int(word_id), _now()))
        else:
            conn.execute("DELETE FROM saved_words WHERE word_id=?", (int(word_id),))


def get_saved_words() -> list[dict[str, Any]]:
    with _connect() as conn:
        ids = [int(r[0]) for r in conn.execute("SELECT word_id FROM saved_words ORDER BY saved_at DESC").fetchall()]
    if not ids:
        return []
    lookup = {int(w["id"]): w for w in get_all_words()}
    return [lookup[i] for i in ids if i in lookup]


def get_quiz_history(limit: int = 30) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.category, s.started_at, s.completed_at, s.total_questions, s.correct, s.max_streak, s.status, "
            "COUNT(a.id) AS answered, COALESCE(SUM(a.is_correct),0) AS actual_correct "
            "FROM quiz_sessions s LEFT JOIN quiz_answers a ON a.session_id=s.id "
            "GROUP BY s.id ORDER BY s.started_at DESC LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        item["correct"] = int(item.get("actual_correct") or 0)
        item["accuracy"] = (item["correct"] / item["answered"] * 100) if item["answered"] else 0.0
        result.append(item)
    return result


def get_category_performance() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT w.category, COUNT(a.id) AS total, COALESCE(SUM(a.is_correct),0) AS correct "
            "FROM quiz_answers a JOIN words w ON w.id=a.word_id GROUP BY w.category ORDER BY total DESC, w.category COLLATE NOCASE"
        ).fetchall()
    return [{"category": r["category"], "total": int(r["total"]), "correct": int(r["correct"]),
             "accuracy": (int(r["correct"])/int(r["total"])*100 if r["total"] else 0.0)} for r in rows]


def get_cefr_performance() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT w.cefr, COUNT(a.id) AS total, COALESCE(SUM(a.is_correct),0) AS correct "
            "FROM quiz_answers a JOIN words w ON w.id=a.word_id GROUP BY w.cefr ORDER BY w.cefr"
        ).fetchall()
    return [{"cefr": r["cefr"], "total": int(r["total"]), "correct": int(r["correct"]),
             "accuracy": (int(r["correct"])/int(r["total"])*100 if r["total"] else 0.0)} for r in rows]


def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM user_settings WHERE key=?", (str(key),)).fetchone()
    return str(row[0]) if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT INTO user_settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(key), str(value)))


def reset_learning_history() -> None:
    """Reset attempts and scheduling without deleting the vocabulary, saved words, or settings."""
    with _connect() as conn:
        conn.execute("DELETE FROM quiz_answers")
        conn.execute("DELETE FROM quiz_sessions")
        conn.execute("DELETE FROM mistakes")
        conn.execute("DELETE FROM word_progress")
        _set_meta(conn, "legacy_total_answered", "0")
        _set_meta(conn, "legacy_correct", "0")


def export_words_csv() -> str:
    import io
    buffer = io.StringIO(newline="")
    fields = ["word", "translation", "pos", "cefr", "category", "pronunciation", "example", "example_translation", "synonyms"]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for item in get_all_words():
        row = {key: item.get(key, "") for key in fields}
        row["synonyms"] = ", ".join(row["synonyms"]) if isinstance(row["synonyms"], list) else row["synonyms"]
        writer.writerow(row)
    return buffer.getvalue()


# Older code/tests imported this name directly.
initialize_database = initialize_database
