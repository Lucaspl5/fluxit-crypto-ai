import aiohttp
import pandas as pd

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Mapa símbolo → ID de CoinGecko
SYMBOL_TO_CG: dict[str, str] = {
    "BTC":   "bitcoin",
    "ETH":   "ethereum",
    "BNB":   "binancecoin",
    "SOL":   "solana",
    "ADA":   "cardano",
    "XRP":   "ripple",
    "DOGE":  "dogecoin",
    "AVAX":  "avalanche-2",
    "MATIC": "matic-network",
    "LINK":  "chainlink",
    "DOT":   "polkadot",
    "UNI":   "uniswap",
    "LTC":   "litecoin",
    "BCH":   "bitcoin-cash",
    "ATOM":  "cosmos",
    "NEAR":  "near",
    "ALGO":  "algorand",
    "SHIB":  "shiba-inu",
    "TRX":   "tron",
    "FIL":   "filecoin",
}

_INTERVAL_DAYS = {"15m": 2, "1h": 14, "4h": 60, "1d": 365}


def _cg_id(symbol: str) -> str:
    return SYMBOL_TO_CG.get(symbol.upper(), symbol.lower())


async def _get(url: str, params: dict | None = None):
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_price(symbol: str, quote: str = "USDT") -> float:
    cg_id = _cg_id(symbol)
    data = await _get(f"{COINGECKO_BASE}/simple/price", {"ids": cg_id, "vs_currencies": "usd"})
    return float(data[cg_id]["usd"])


async def get_ticker_24h(symbol: str, quote: str = "USDT") -> dict:
    cg_id = _cg_id(symbol)
    data = await _get(
        f"{COINGECKO_BASE}/coins/markets",
        {"vs_currency": "usd", "ids": cg_id, "price_change_percentage": "24h"},
    )
    c = data[0]
    return {
        "price":        float(c["current_price"] or 0),
        "change_pct":   float(c.get("price_change_percentage_24h") or 0),
        "change":       float(c.get("price_change_24h") or 0),
        "high":         float(c.get("high_24h") or 0),
        "low":          float(c.get("low_24h") or 0),
        "volume":       float(c.get("total_volume") or 0),
        "quote_volume": float(c.get("total_volume") or 0),
    }


async def get_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
    quote: str = "USDT",
) -> pd.DataFrame:
    cg_id = _cg_id(symbol)
    days = _INTERVAL_DAYS.get(interval, 14)

    data = await _get(
        f"{COINGECKO_BASE}/coins/{cg_id}/market_chart",
        {"vs_currency": "usd", "days": days},
    )

    prices  = data["prices"]          # [[ts_ms, price], ...]
    volumes = dict(data.get("total_volumes", []))

    df = pd.DataFrame(prices, columns=["timestamp", "close"])
    df["close"]  = df["close"].astype(float)
    df["open"]   = df["close"].shift(1).fillna(df["close"])
    df["high"]   = df["close"]
    df["low"]    = df["close"]
    df["volume"] = df["timestamp"].map(volumes).fillna(0).astype(float)

    # Resample to coarser intervals
    if interval in ("4h", "1d"):
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        rule = "4h" if interval == "4h" else "1D"
        df = (
            df.set_index("timestamp")
            .resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
            .reset_index()
        )

    return df.tail(limit).reset_index(drop=True)
