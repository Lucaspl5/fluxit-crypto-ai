import math
import pandas as pd
import pandas_ta as ta
from trading.binance_client import get_klines


def _safe_float(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    val = series.iloc[-1]
    return None if (val is None or (isinstance(val, float) and math.isnan(val))) else float(val)


def _first_col(df: pd.DataFrame, prefix: str) -> str:
    return next(c for c in df.columns if c.startswith(prefix))


async def get_analysis(
    symbol: str,
    interval: str = "1h",
    quote: str = "USDT",
) -> dict:
    df = await get_klines(symbol, interval=interval, limit=200, quote=quote)
    close = df["close"]
    current_price = float(close.iloc[-1])

    # RSI
    rsi_s = ta.rsi(close, length=14)
    rsi = _safe_float(rsi_s)

    # MACD
    macd_df = ta.macd(close)
    if macd_df is not None:
        macd = _safe_float(macd_df[_first_col(macd_df, "MACD_")])
        macd_signal = _safe_float(macd_df[_first_col(macd_df, "MACDs_")])
        macd_hist = _safe_float(macd_df[_first_col(macd_df, "MACDh_")])
    else:
        macd = macd_signal = macd_hist = None

    # Bollinger Bands
    bb_df = ta.bbands(close, length=20)
    if bb_df is not None:
        bb_lower = _safe_float(bb_df[_first_col(bb_df, "BBL_")])
        bb_mid = _safe_float(bb_df[_first_col(bb_df, "BBM_")])
        bb_upper = _safe_float(bb_df[_first_col(bb_df, "BBU_")])
    else:
        bb_lower = bb_mid = bb_upper = None

    # EMAs
    ema_20 = _safe_float(ta.ema(close, length=20))
    ema_50 = _safe_float(ta.ema(close, length=50))
    ema_200 = _safe_float(ta.ema(close, length=200)) if len(close) >= 200 else None

    # Volume
    avg_vol = float(df["volume"].rolling(20).mean().iloc[-1])
    cur_vol = float(df["volume"].iloc[-1])
    volume_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

    # Trend (price vs long-term EMA)
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
