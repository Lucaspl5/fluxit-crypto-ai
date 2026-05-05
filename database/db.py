import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from datetime import datetime
from config import DATABASE_URL

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool


def _conn():
    return _get_pool().getconn()


def _put(conn):
    _get_pool().putconn(conn)


def _execute(sql: str, params=(), fetch: str = "none"):
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            conn.commit()
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
    finally:
        _put(conn)


def init_db() -> None:
    _execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id           SERIAL PRIMARY KEY,
            user_id      BIGINT  NOT NULL,
            symbol       TEXT    NOT NULL,
            target_price REAL    NOT NULL,
            direction    TEXT    NOT NULL,
            created_at   TEXT    NOT NULL,
            triggered    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id      SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            symbol  TEXT   NOT NULL,
            UNIQUE(user_id, symbol)
        );

        CREATE TABLE IF NOT EXISTS paper_balance (
            user_id      BIGINT PRIMARY KEY,
            usdt_balance REAL NOT NULL DEFAULT 10000.0
        );

        CREATE TABLE IF NOT EXISTS paper_trades (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL,
            symbol     TEXT   NOT NULL,
            side       TEXT   NOT NULL,
            quantity   REAL   NOT NULL,
            price      REAL   NOT NULL,
            total_usdt REAL   NOT NULL,
            timestamp  TEXT   NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sl_tp_orders (
            id           SERIAL PRIMARY KEY,
            user_id      BIGINT NOT NULL,
            symbol       TEXT   NOT NULL,
            quantity     REAL   NOT NULL,
            entry_price  REAL   NOT NULL,
            stop_loss    REAL,
            take_profit  REAL,
            status       TEXT   NOT NULL DEFAULT 'active',
            created_at   TEXT   NOT NULL,
            triggered_at TEXT
        );
    """)


# ── Alerts ─────────────────────────────────────────────────────────────────────

def add_alert(user_id: int, symbol: str, target_price: float, direction: str) -> None:
    _execute(
        "INSERT INTO alerts (user_id, symbol, target_price, direction, created_at) VALUES (%s,%s,%s,%s,%s)",
        (user_id, symbol.upper(), target_price, direction, datetime.utcnow().isoformat()),
    )


def get_alerts(user_id: int | None = None, active_only: bool = True) -> list:
    where, params = [], []
    if active_only:
        where.append("triggered = 0")
    if user_id is not None:
        where.append("user_id = %s")
        params.append(user_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return _execute(f"SELECT * FROM alerts {clause} ORDER BY id", params, fetch="all") or []


def mark_alert_triggered(alert_id: int) -> None:
    _execute("UPDATE alerts SET triggered = 1 WHERE id = %s", (alert_id,))


def delete_alert(alert_id: int, user_id: int) -> None:
    _execute("DELETE FROM alerts WHERE id = %s AND user_id = %s", (alert_id, user_id))


# ── Watchlist ─────────────────────────────────────────────────────────────────

def add_to_watchlist(user_id: int, symbol: str) -> bool:
    try:
        _execute(
            "INSERT INTO watchlist (user_id, symbol) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (user_id, symbol.upper()),
        )
        return True
    except Exception:
        return False


def remove_from_watchlist(user_id: int, symbol: str) -> None:
    _execute("DELETE FROM watchlist WHERE user_id=%s AND symbol=%s", (user_id, symbol.upper()))


def get_watchlist(user_id: int) -> list[str]:
    rows = _execute("SELECT symbol FROM watchlist WHERE user_id=%s ORDER BY symbol", (user_id,), fetch="all") or []
    return [r["symbol"] for r in rows]


# ── Paper balance ─────────────────────────────────────────────────────────────

def get_paper_balance(user_id: int) -> float:
    row = _execute("SELECT usdt_balance FROM paper_balance WHERE user_id=%s", (user_id,), fetch="one")
    if row is None:
        _execute("INSERT INTO paper_balance (user_id, usdt_balance) VALUES (%s, 10000.0)", (user_id,))
        return 10000.0
    return float(row["usdt_balance"])


def update_paper_balance(user_id: int, new_balance: float) -> None:
    _execute(
        "INSERT INTO paper_balance (user_id, usdt_balance) VALUES (%s,%s) "
        "ON CONFLICT (user_id) DO UPDATE SET usdt_balance = EXCLUDED.usdt_balance",
        (user_id, new_balance),
    )


def add_paper_trade(user_id: int, symbol: str, side: str, quantity: float, price: float) -> None:
    _execute(
        "INSERT INTO paper_trades (user_id, symbol, side, quantity, price, total_usdt, timestamp) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (user_id, symbol, side, quantity, price, quantity * price, datetime.utcnow().isoformat()),
    )


def get_paper_portfolio(user_id: int) -> dict[str, float]:
    rows = _execute(
        "SELECT symbol, side, SUM(quantity) AS qty FROM paper_trades "
        "WHERE user_id=%s GROUP BY symbol, side",
        (user_id,), fetch="all",
    ) or []
    portfolio: dict[str, float] = {}
    for row in rows:
        delta = float(row["qty"]) if row["side"] == "BUY" else -float(row["qty"])
        portfolio[row["symbol"]] = portfolio.get(row["symbol"], 0.0) + delta
    return {k: v for k, v in portfolio.items() if v > 1e-10}


# ── Stop Loss / Take Profit ────────────────────────────────────────────────────

def add_sl_tp_order(
    user_id: int,
    symbol: str,
    quantity: float,
    entry_price: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> int:
    row = _execute(
        "INSERT INTO sl_tp_orders (user_id, symbol, quantity, entry_price, stop_loss, take_profit, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (user_id, symbol, quantity, entry_price, stop_loss, take_profit, datetime.utcnow().isoformat()),
        fetch="one",
    )
    return row["id"]


def get_active_sl_tp_orders() -> list:
    return _execute("SELECT * FROM sl_tp_orders WHERE status='active'", fetch="all") or []


def get_sl_tp_orders_by_user(user_id: int) -> list:
    return _execute(
        "SELECT * FROM sl_tp_orders WHERE user_id=%s AND status='active' ORDER BY id",
        (user_id,), fetch="all",
    ) or []


def close_sl_tp_order(order_id: int, status: str) -> None:
    _execute(
        "UPDATE sl_tp_orders SET status=%s, triggered_at=%s WHERE id=%s",
        (status, datetime.utcnow().isoformat(), order_id),
    )


def cancel_sl_tp_order(order_id: int, user_id: int) -> None:
    _execute(
        "UPDATE sl_tp_orders SET status='cancelled' WHERE id=%s AND user_id=%s",
        (order_id, user_id),
    )
