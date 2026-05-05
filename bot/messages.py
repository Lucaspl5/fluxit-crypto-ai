def _price_fmt(price: float) -> str:
    """Format price: 4 decimals for small coins, 2 for large."""
    return f"{price:,.2f}" if price >= 1 else f"{price:,.6f}"


def format_price(symbol: str, data: dict) -> str:
    pct = data["change_pct"]
    sign = "+" if pct >= 0 else ""
    arrow = "📈" if pct >= 0 else "📉"
    return (
        f"*{symbol}/USDT* {arrow}\n"
        f"💰 Precio: `${_price_fmt(data['price'])}`\n"
        f"📊 Cambio 24h: `{sign}{pct:.2f}%`\n"
        f"⬆️ Máx: `${_price_fmt(data['high'])}`\n"
        f"⬇️ Mín: `${_price_fmt(data['low'])}`\n"
        f"📦 Volumen: `${data['quote_volume']:,.0f} USDT`"
    )


def format_analysis(data: dict) -> str:
    price = data["price"]
    rsi = data.get("rsi")

    # RSI
    if rsi is None:
        rsi_str = "N/A"
    else:
        label = ""
        if rsi < 30:   label = " 🟢 SOBREVENTA"
        elif rsi > 70: label = " 🔴 SOBRECOMPRA"
        elif rsi < 40: label = " 🟡 Zona compra"
        elif rsi > 60: label = " 🟡 Zona venta"
        rsi_str = f"`{rsi:.1f}`{label}"

    # MACD
    macd = data.get("macd")
    macd_sig = data.get("macd_signal")
    if macd is not None:
        cross = "🟢 Alcista" if macd > macd_sig else "🔴 Bajista"
        macd_str = f"`{macd:.4f}` / señal `{macd_sig:.4f}` — {cross}"
    else:
        macd_str = "N/A"

    # Bollinger Bands
    bb_l, bb_m, bb_u = data.get("bb_lower"), data.get("bb_mid"), data.get("bb_upper")
    if bb_l and bb_u:
        pos = "🔴 SOBRE BANDA" if price > bb_u else ("🟢 BAJO BANDA" if price < bb_l else "⚪ Dentro")
        bb_str = f"`{_price_fmt(bb_l)}` / `{_price_fmt(bb_m)}` / `{_price_fmt(bb_u)}` — {pos}"
    else:
        bb_str = "N/A"

    # EMAs
    e20, e50, e200 = data.get("ema_20"), data.get("ema_50"), data.get("ema_200")
    ema_str = f"`{_price_fmt(e20)}` / `{_price_fmt(e50)}`" if e20 and e50 else "N/A"
    if e200:
        ema_str += f" / `{_price_fmt(e200)}`"

    # Volume
    vr = data.get("volume_ratio", 1.0)
    vol_str = f"`{vr:.1f}x`" + (" 🔥" if vr > 1.5 else "")

    trend = data.get("trend", "")
    trend_emoji = "🟢" if trend == "ALCISTA" else "🔴"

    return (
        f"📊 *Análisis — {data['symbol']}/USDT ({data['interval']})*\n"
        f"💰 Precio: `${_price_fmt(price)}`\n\n"
        f"📈 *RSI (14):* {rsi_str}\n"
        f"⚡ *MACD:* {macd_str}\n"
        f"📉 *Bollinger (inf/mid/sup):* {bb_str}\n"
        f"📊 *EMA 20/50/200:* {ema_str}\n"
        f"📦 *Volumen relativo:* {vol_str}\n"
        f"🧭 *Tendencia:* {trend_emoji} {trend}"
    )


def format_signal(sig: dict) -> str:
    signal = sig["signal"]
    strength = sig.get("strength", "")
    score = sig.get("score", 0)

    emoji = {"COMPRA": "🟢", "VENTA": "🔴"}.get(signal, "⚪")
    label = f"{signal} {strength}".strip()
    lines = [f"{emoji} *{sig['symbol']}/USDT* — {label} (score: {score:+d})"]
    for s in sig.get("signals", []):
        lines.append(f"  • {s}")
    return "\n".join(lines)


def format_portfolio(
    portfolio: dict[str, float],
    prices: dict[str, float],
    usdt_balance: float,
) -> str:
    lines = ["💼 *Portfolio (Paper Trading)*\n"]
    total = usdt_balance

    for symbol, qty in portfolio.items():
        price = prices.get(symbol, 0.0)
        value = qty * price
        total += value
        lines.append(f"• *{symbol}*: `{qty:.6f}` ≈ `${value:,.2f} USDT`")

    if not portfolio:
        lines.append("_Sin posiciones abiertas._")

    lines.append(f"\n💵 *USDT disponible:* `${usdt_balance:,.2f}`")
    lines.append(f"📊 *Valor total:* `${total:,.2f} USDT`")
    return "\n".join(lines)
