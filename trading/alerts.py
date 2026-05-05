from database.db import (
    get_alerts, mark_alert_triggered,
    get_active_sl_tp_orders, close_sl_tp_order,
    get_paper_balance, update_paper_balance, add_paper_trade,
)
from trading.market_data import get_prices_batch
from config import TRADING_MODE


async def check_alerts() -> list[dict]:
    active = get_alerts(active_only=True)
    if not active:
        return []

    symbols = list({a["symbol"] for a in active})
    prices = await get_prices_batch(symbols)

    triggered: list[dict] = []
    for alert in active:
        price = prices.get(alert["symbol"])
        if price is None:
            continue
        target = alert["target_price"]
        hit = (
            (alert["direction"] == "above" and price >= target) or
            (alert["direction"] == "below" and price <= target)
        )
        if hit:
            mark_alert_triggered(alert["id"])
            triggered.append({
                "user_id":   alert["user_id"],
                "symbol":    alert["symbol"],
                "price":     price,
                "target":    target,
                "direction": alert["direction"],
            })
    return triggered


async def check_sl_tp() -> list[dict]:
    orders = get_active_sl_tp_orders()
    if not orders:
        return []

    symbols = list({o["symbol"] for o in orders})
    prices = await get_prices_batch(symbols)

    triggered: list[dict] = []
    for order in orders:
        price = prices.get(order["symbol"])
        if price is None:
            continue

        sl, tp = order["stop_loss"], order["take_profit"]
        qty, user_id = order["quantity"], order["user_id"]
        hit_type = None

        if sl and price <= sl:
            hit_type, target = "SL", sl
        elif tp and price >= tp:
            hit_type, target = "TP", tp

        if not hit_type:
            continue

        if TRADING_MODE == "paper":
            received = qty * price
            update_paper_balance(user_id, get_paper_balance(user_id) + received)
            add_paper_trade(user_id, order["symbol"], "SELL", qty, price)

        close_sl_tp_order(order["id"], f"triggered_{hit_type.lower()}")
        triggered.append({
            "user_id":  user_id,
            "symbol":   order["symbol"],
            "type":     hit_type,
            "quantity": qty,
            "target":   target,
            "price":    price,
            "received": qty * price,
        })

    return triggered
