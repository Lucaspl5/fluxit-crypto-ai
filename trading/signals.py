import asyncio
from trading.analysis import get_analysis

COMPRA = "COMPRA"
VENTA = "VENTA"
NEUTRO = "NEUTRO"


def _evaluate(analysis: dict) -> dict:
    score = 0
    signals: list[str] = []

    rsi = analysis.get("rsi")
    if rsi is not None:
        if rsi < 30:
            signals.append(f"RSI {rsi:.1f} — sobreventa")
            score += 2
        elif rsi < 40:
            signals.append(f"RSI {rsi:.1f} — zona de compra")
            score += 1
        elif rsi > 70:
            signals.append(f"RSI {rsi:.1f} — sobrecompra")
            score -= 2
        elif rsi > 60:
            signals.append(f"RSI {rsi:.1f} — zona de venta")
            score -= 1

    macd = analysis.get("macd")
    macd_sig = analysis.get("macd_signal")
    macd_hist = analysis.get("macd_hist")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and macd_hist and macd_hist > 0:
            signals.append("MACD cruce alcista")
            score += 1
        elif macd < macd_sig and macd_hist and macd_hist < 0:
            signals.append("MACD cruce bajista")
            score -= 1

    price = analysis.get("price")
    bb_lower = analysis.get("bb_lower")
    bb_upper = analysis.get("bb_upper")
    if price and bb_lower and bb_upper:
        if price < bb_lower:
            signals.append("Precio bajo banda inferior (BB)")
            score += 2
        elif price > bb_upper:
            signals.append("Precio sobre banda superior (BB)")
            score -= 2

    ema_20 = analysis.get("ema_20")
    ema_50 = analysis.get("ema_50")
    if ema_20 and ema_50:
        if ema_20 > ema_50:
            signals.append("EMA20 > EMA50 (tendencia alcista)")
            score += 1
        else:
            signals.append("EMA20 < EMA50 (tendencia bajista)")
            score -= 1

    if score >= 3:
        signal, strength = COMPRA, "FUERTE"
    elif score >= 1:
        signal, strength = COMPRA, "DÉBIL"
    elif score <= -3:
        signal, strength = VENTA, "FUERTE"
    elif score <= -1:
        signal, strength = VENTA, "DÉBIL"
    else:
        signal, strength = NEUTRO, ""

    return {
        "symbol": analysis["symbol"],
        "signal": signal,
        "strength": strength,
        "score": score,
        "signals": signals,
        "analysis": analysis,
    }


async def generate_signal(symbol: str, interval: str = "1h") -> dict:
    analysis = await get_analysis(symbol, interval=interval)
    return _evaluate(analysis)


async def scan_watchlist(symbols: list[str], interval: str = "1h") -> list[dict]:
    tasks = [generate_signal(s, interval) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid = [r for r in results if isinstance(r, dict)]
    valid.sort(key=lambda x: -x["score"])
    return valid
