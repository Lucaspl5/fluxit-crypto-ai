from database.db import (
    get_alerts, mark_alert_triggered,
    get_active_sl_tp_orders, close_sl_tp_order,
    get_paper_balance, update_paper_balance, add_paper_trade,
)
from trading.market_data import get_price
from config import TRADING_MODE, QUOTE_CURRENCY


async def check_alerts() -> list[dict]:
    """Check price alerts; return triggered ones."""
    active = get_alerts(active_only=True)
    if not active:
        return []

    by_symbol: dict[str, list] = {}
    for alert in active:
        by_symbol.setdefault(alert["symbol"], []).append(alert)

    triggered: list[dict] = []
    for symbol, alerts in by_symbol.items():
        try:
            price = await get_price(symbol, quote=QUOTE_CURRENCY)
        except Exception:
            continue
        for alert in alerts:
            target = alert["target_price"]
            hit = (
                (alert["direction"] == "above" and price >= target) or
                (alert["direction"] == "below" and price <= target)
            )
            if hit:
                mark_alert_triggered(alert["id"])
                triggered.append({
                    "user_id": alert["user_id"],
                    "symbol": symbol,
                    "price": price,
                    "target": target,
                    "direction": alert["direction"],
                })
    return triggered


async def check_sl_tp() -> list[dict]:
    """Check Stop Loss / Take Profit orders; execute and return triggered ones."""
    orders = get_active_sl_tp_orders()
    if not orders:
        return []

    by_symbol: dict[str, list] = {}
    for order in orders:
        by_symbol.setdefault(order["symbol"], []).append(order)

    triggered: list[dict] = []
    for symbol, sym_orders in by_symbol.items():
        try:
            price = await get_price(symbol, quote=QUOTE_CURRENCY)
        except Exception:
            continue

        for order in sym_orders:
            sl = order["stop_loss"]
            tp = order["take_profit"]
            qty = order["quantity"]
            user_id = order["user_id"]
            hit_type = None

            if sl and price <= sl:
                hit_type = "SL"
                target = sl
            elif tp and price >= tp:
                hit_type = "TP"
                target = tp

            if not hit_type:
                continue

            # Execute the paper sell
            if TRADING_MODE == "paper":
                received = qty * price
                balance = get_paper_balance(user_id)
                update_paper_balance(user_id, balance + received)
                add_paper_trade(user_id, symbol, "SELL", qty, price)

            close_sl_tp_order(order["id"], f"triggered_{hit_type.lower()}")
            triggered.append({
                "user_id": user_id,
                "symbol": symbol,
                "type": hit_type,
                "quantity": qty,
                "target": target,
                "price": price,
                "received": qty * price,
            })

    return triggered
