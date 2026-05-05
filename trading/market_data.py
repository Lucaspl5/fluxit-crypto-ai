import asyncio
import time
import aiohttp
import pandas as pd

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

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

# ── Caché de precios (TTL 20s) ─────────────────────────────────────────────────
_price_cache: dict[str, tuple[float, float]] = {}   # cg_id -> (price, timestamp)
CACHE_TTL = 20


def _cg_id(symbol: str) -> str:
    return SYMBOL_TO_CG.get(symbol.upper(), symbol.lower())


# ── HTTP con reintentos en 429 ─────────────────────────────────────────────────

async def _get(url: str, params: dict | None = None) -> dict | list:
    timeout = aiohttp.ClientTimeout(total=15)
    for attempt in range(4):
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 429:
                    wait = 2 ** attempt          # 1s, 2s, 4s, 8s
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return await resp.json()
    raise RuntimeError("CoinGecko: demasiadas peticiones, intenta en unos segundos.")


# ── Precio individual (con caché) ──────────────────────────────────────────────

async def get_price(symbol: str, quote: str = "USDT") -> float:
    cg_id = _cg_id(symbol)
    now = time.monotonic()

    if cg_id in _price_cache:
        price, ts = _price_cache[cg_id]
        if now - ts < CACHE_TTL:
            return price

    data = await _get(f"{COINGECKO_BASE}/simple/price", {"ids": cg_id, "vs_currencies": "usd"})
    price = float(data[cg_id]["usd"])
    _price_cache[cg_id] = (price, now)
    return price


# ── Precios en batch (una sola llamada para varios símbolos) ───────────────────

async def get_prices_batch(symbols: list[str]) -> dict[str, float]:
    now = time.monotonic()
    result: dict[str, float] = {}
    to_fetch: list[str] = []

    for sym in symbols:
        cg_id = _cg_id(sym)
        if cg_id in _price_cache:
            price, ts = _price_cache[cg_id]
            if now - ts < CACHE_TTL:
                result[sym] = price
                continue
        to_fetch.append(sym)

    if to_fetch:
        ids = ",".join(_cg_id(s) for s in to_fetch)
        data = await _get(f"{COINGECKO_BASE}/simple/price", {"ids": ids, "vs_currencies": "usd"})
        for sym in to_fetch:
            cg_id = _cg_id(sym)
            if cg_id in data:
                price = float(data[cg_id]["usd"])
                _price_cache[cg_id] = (price, now)
                result[sym] = price

    return result


# ── Stats 24h ─────────────────────────────────────────────────────────────────

async def get_ticker_24h(symbol: str, quote: str = "USDT") -> dict:
    cg_id = _cg_id(symbol)
    data = await _get(
        f"{COINGECKO_BASE}/coins/markets",
        {"vs_currency": "usd", "ids": cg_id, "price_change_percentage": "24h"},
    )
    c = data[0]
    price = float(c["current_price"] or 0)
    _price_cache[cg_id] = (price, time.monotonic())
    return {
        "price":        price,
        "change_pct":   float(c.get("price_change_percentage_24h") or 0),
        "change":       float(c.get("price_change_24h") or 0),
        "high":         float(c.get("high_24h") or 0),
        "low":          float(c.get("low_24h") or 0),
        "volume":       float(c.get("total_volume") or 0),
        "quote_volume": float(c.get("total_volume") or 0),
    }


# ── OHLCV ────────────────────────────────────────────────────────────────────

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

    prices  = data["prices"]
    volumes = dict(data.get("total_volumes", []))

    df = pd.DataFrame(prices, columns=["timestamp", "close"])
    df["close"]  = df["close"].astype(float)
    df["open"]   = df["close"].shift(1).fillna(df["close"])
    df["high"]   = df["close"]
    df["low"]    = df["close"]
    df["volume"] = df["timestamp"].map(volumes).fillna(0).astype(float)

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
