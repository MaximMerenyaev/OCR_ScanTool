import sqlite3
from datetime import datetime

DB_PATH = "history.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            filename     TEXT,
            created_at   TEXT,
            ocr_engine   TEXT,
            language     TEXT,
            text         TEXT,
            page_count   INTEGER DEFAULT 1,
            image        TEXT    DEFAULT ''
        )
    """)
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN image TEXT DEFAULT ''")
    except Exception:
        pass
    conn.commit()
    conn.close()


def save_document(filename: str, ocr_engine: str, language: str, text: str,
                  page_count: int = 1, image: str = "") -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO documents (filename, created_at, ocr_engine, language, text, page_count, image) "
        "VALUES (?,?,?,?,?,?,?)",
        (filename, datetime.now().isoformat(timespec="seconds"), ocr_engine, language, text, page_count, image),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_history(limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filename, created_at, ocr_engine, language, page_count, "
        "substr(text,1,200) AS preview, image "
        "FROM documents ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_document(doc_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
