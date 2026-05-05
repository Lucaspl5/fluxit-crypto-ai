from database.db import get_alerts, mark_alert_triggered
from trading.binance_client import get_price


async def check_alerts() -> list[dict]:
    """Check all active alerts; return list of triggered alert dicts."""
    active = get_alerts(active_only=True)
    if not active:
        return []

    # Group by symbol to minimise API calls
    by_symbol: dict[str, list] = {}
    for alert in active:
        by_symbol.setdefault(alert["symbol"], []).append(alert)

    triggered: list[dict] = []
    for symbol, alerts in by_symbol.items():
        try:
            price = await get_price(symbol)
        except Exception:
            continue

        for alert in alerts:
            target = alert["target_price"]
            direction = alert["direction"]
            hit = (direction == "above" and price >= target) or \
                  (direction == "below" and price <= target)
            if hit:
                mark_alert_triggered(alert["id"])
                triggered.append({
                    "alert_id": alert["id"],
                    "user_id": alert["user_id"],
                    "symbol": symbol,
                    "price": price,
                    "target": target,
                    "direction": direction,
                })

    return triggered
