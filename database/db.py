import os
import sqlite3
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "data/fluxit.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                symbol      TEXT    NOT NULL,
                target_price REAL   NOT NULL,
                direction   TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                triggered   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol  TEXT    NOT NULL,
                UNIQUE(user_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS paper_balance (
                user_id      INTEGER PRIMARY KEY,
                usdt_balance REAL NOT NULL DEFAULT 10000.0
            );

            CREATE TABLE IF NOT EXISTS paper_trades (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                symbol     TEXT    NOT NULL,
                side       TEXT    NOT NULL,
                quantity   REAL    NOT NULL,
                price      REAL    NOT NULL,
                total_usdt REAL    NOT NULL,
                timestamp  TEXT    NOT NULL
            );
        """)


# ── Alerts ────────────────────────────────────────────────────────────────────

def add_alert(user_id: int, symbol: str, target_price: float, direction: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO alerts (user_id, symbol, target_price, direction, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, symbol.upper(), target_price, direction, datetime.utcnow().isoformat()),
        )


def get_alerts(user_id: int | None = None, active_only: bool = True) -> list:
    with _connect() as conn:
        where = ["triggered = 0"] if active_only else []
        params: list = []
        if user_id is not None:
            where.append("user_id = ?")
            params.append(user_id)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        return conn.execute(f"SELECT * FROM alerts {clause} ORDER BY id", params).fetchall()


def mark_alert_triggered(alert_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE alerts SET triggered = 1 WHERE id = ?", (alert_id,))


def delete_alert(alert_id: int, user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM alerts WHERE id = ? AND user_id = ?", (alert_id, user_id))


# ── Watchlist ─────────────────────────────────────────────────────────────────

def add_to_watchlist(user_id: int, symbol: str) -> bool:
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (?, ?)",
                (user_id, symbol.upper()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_from_watchlist(user_id: int, symbol: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
            (user_id, symbol.upper()),
        )


def get_watchlist(user_id: int) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT symbol FROM watchlist WHERE user_id = ? ORDER BY symbol",
            (user_id,),
        ).fetchall()
    return [r["symbol"] for r in rows]


# ── Paper trading ─────────────────────────────────────────────────────────────

def get_paper_balance(user_id: int) -> float:
    with _connect() as conn:
        row = conn.execute(
            "SELECT usdt_balance FROM paper_balance WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO paper_balance (user_id, usdt_balance) VALUES (?, 10000.0)",
                (user_id,),
            )
            return 10000.0
        return float(row["usdt_balance"])


def update_paper_balance(user_id: int, new_balance: float) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO paper_balance (user_id, usdt_balance) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET usdt_balance = excluded.usdt_balance",
            (user_id, new_balance),
        )


def add_paper_trade(
    user_id: int, symbol: str, side: str, quantity: float, price: float
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO paper_trades (user_id, symbol, side, quantity, price, total_usdt, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, symbol, side, quantity, price, quantity * price, datetime.utcnow().isoformat()),
        )


def get_paper_portfolio(user_id: int) -> dict[str, float]:
    """Returns {symbol: net_quantity} for positions with quantity > 0."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT symbol, side, SUM(quantity) AS qty "
            "FROM paper_trades WHERE user_id = ? GROUP BY symbol, side",
            (user_id,),
        ).fetchall()

    portfolio: dict[str, float] = {}
    for row in rows:
        sym = row["symbol"]
        delta = float(row["qty"]) if row["side"] == "BUY" else -float(row["qty"])
        portfolio[sym] = portfolio.get(sym, 0.0) + delta

    return {k: v for k, v in portfolio.items() if v > 1e-10}
