import sqlite3
from datetime import datetime

DB_PATH = "articles.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                url         TEXT UNIQUE NOT NULL,
                source      TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT '',
                summary     TEXT,
                published   TEXT,
                fetched_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_feeds (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                url         TEXT UNIQUE NOT NULL,
                category    TEXT NOT NULL DEFAULT 'AI Models',
                added_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def get_custom_feeds() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM custom_feeds ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_custom_feed(name: str, url: str, category: str) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO custom_feeds (name, url, category) VALUES (?, ?, ?)",
            (name, url, category),
        )
        conn.commit()
        return cursor.lastrowid


def delete_custom_feed(feed_id: int):
    with get_conn() as conn:
        # Fetch name first so we can clean up its articles
        feed = conn.execute(
            "SELECT name FROM custom_feeds WHERE id = ?", (feed_id,)
        ).fetchone()
        conn.execute("DELETE FROM custom_feeds WHERE id = ?", (feed_id,))
        if feed:
            conn.execute("DELETE FROM articles WHERE source = ?", (feed["name"],))
        conn.commit()


def insert_articles(articles: list[dict]):
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO articles (title, url, source, category, summary, published)
            VALUES (:title, :url, :source, :category, :summary, :published)
            """,
            articles,
        )
        conn.commit()


def get_articles(keyword: str | None = None, limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        if keyword:
            kw = f"%{keyword}%"
            rows = conn.execute(
                """
                SELECT * FROM articles
                WHERE title LIKE ? OR summary LIKE ?
                ORDER BY published DESC, fetched_at DESC
                LIMIT ?
                """,
                (kw, kw, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM articles
                ORDER BY published DESC, fetched_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        latest = conn.execute(
            "SELECT fetched_at FROM articles ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    return {
        "total": count,
        "last_fetched": latest[0] if latest else None,
    }
