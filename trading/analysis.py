import math
import pandas as pd
from trading.binance_client import get_klines


# ── Indicadores con pandas puro ────────────────────────────────────────────────

def _rsi(close: pd.Series, length: int = 14) -> float | None:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=length - 1, min_periods=length).mean()
    avg_loss = loss.ewm(com=length - 1, min_periods=length).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return None if math.isnan(val) else float(val)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    def _v(s):
        v = s.iloc[-1]
        return None if math.isnan(v) else float(v)

    return _v(macd_line), _v(signal_line), _v(histogram)


def _bbands(close: pd.Series, length: int = 20, std: float = 2.0) -> tuple:
    mid = close.rolling(length).mean()
    dev = close.rolling(length).std()
    upper = mid + std * dev
    lower = mid - std * dev

    def _v(s):
        v = s.iloc[-1]
        return None if math.isnan(v) else float(v)

    return _v(lower), _v(mid), _v(upper)


def _ema(close: pd.Series, length: int) -> float | None:
    if len(close) < length:
        return None
    val = close.ewm(span=length, adjust=False).mean().iloc[-1]
    return None if math.isnan(val) else float(val)


# ── Análisis completo ──────────────────────────────────────────────────────────

async def get_analysis(
    symbol: str,
    interval: str = "1h",
    quote: str = "USDT",
) -> dict:
    df = await get_klines(symbol, interval=interval, limit=200, quote=quote)
    close = df["close"]
    current_price = float(close.iloc[-1])

    rsi = _rsi(close)
    macd, macd_signal, macd_hist = _macd(close)
    bb_lower, bb_mid, bb_upper = _bbands(close)
    ema_20 = _ema(close, 20)
    ema_50 = _ema(close, 50)
    ema_200 = _ema(close, 200)

    avg_vol = float(df["volume"].rolling(20).mean().iloc[-1])
    cur_vol = float(df["volume"].iloc[-1])
    volume_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

    ref_ema = ema_200 or ema_50 or ema_20
    trend = "ALCISTA" if (ref_ema and current_price > ref_ema) else "BAJISTA"

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "price": current_price,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "bb_upper": bb_upper,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "volume_ratio": volume_ratio,
        "trend": trend,
    }
