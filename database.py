import sqlite3
from datetime import datetime, timedelta

DB_PATH = "newsletter_db.sqlite"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS newsletters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            content TEXT NOT NULL,
            sentiment TEXT,
            sector_focus TEXT,
            horizon TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trade_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            newsletter_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            company TEXT NOT NULL,
            entry_price REAL,
            direction TEXT,
            created_at TEXT NOT NULL,
            scored_at TEXT,
            exit_price REAL,
            pnl_pct REAL,
            FOREIGN KEY (newsletter_id) REFERENCES newsletters(id)
        )
    """)
    conn.commit()
    conn.close()


def save_newsletter(content, sentiment, sector_focus, horizon, picks=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO newsletters (created_at, content, sentiment, sector_focus, horizon) VALUES (?, ?, ?, ?, ?)",
        (now, content, sentiment, sector_focus, horizon),
    )
    newsletter_id = c.lastrowid
    if picks:
        for pick in picks:
            c.execute(
                "INSERT INTO trade_picks (newsletter_id, ticker, company, entry_price, direction, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    newsletter_id,
                    pick["ticker"],
                    pick["company"],
                    pick.get("entry_price"),
                    pick.get("direction"),
                    now,
                ),
            )
    conn.commit()
    conn.close()
    return newsletter_id


def get_newsletters(limit=20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM newsletters ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_newsletter():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM newsletters ORDER BY created_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_unscored_picks():
    """Return picks older than 48 hours that haven't been scored yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    c.execute(
        "SELECT * FROM trade_picks WHERE scored_at IS NULL AND created_at <= ?",
        (cutoff,),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def score_pick(pick_id, exit_price, pnl_pct):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "UPDATE trade_picks SET scored_at=?, exit_price=?, pnl_pct=? WHERE id=?",
        (now, exit_price, pnl_pct, pick_id),
    )
    conn.commit()
    conn.close()


def get_last_scored_picks():
    """Return the most recent batch of scored picks (from the last newsletter that has them)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Find the most recent newsletter_id that has scored picks
    c.execute("""
        SELECT newsletter_id FROM trade_picks
        WHERE scored_at IS NOT NULL
        ORDER BY scored_at DESC
        LIMIT 1
    """)
    row = c.fetchone()
    if not row:
        conn.close()
        return []
    newsletter_id = row["newsletter_id"]
    c.execute("""
        SELECT tp.*, n.created_at as newsletter_date
        FROM trade_picks tp
        JOIN newsletters n ON tp.newsletter_id = n.id
        WHERE tp.newsletter_id = ?
    """, (newsletter_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_newsletter_picks(newsletter_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM trade_picks WHERE newsletter_id = ?", (newsletter_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
