import pandas as pd
from binance import AsyncClient
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await AsyncClient.create(
            api_key=BINANCE_API_KEY or None,
            api_secret=BINANCE_API_SECRET or None,
            testnet=USE_TESTNET,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close_connection()
        _client = None


def _pair(symbol: str, quote: str) -> str:
    return f"{symbol.upper()}{quote.upper()}"


async def get_price(symbol: str, quote: str = "USDT") -> float:
    client = await get_client()
    ticker = await client.get_symbol_ticker(symbol=_pair(symbol, quote))
    return float(ticker["price"])


async def get_ticker_24h(symbol: str, quote: str = "USDT") -> dict:
    client = await get_client()
    data = await client.get_ticker(symbol=_pair(symbol, quote))
    return {
        "price": float(data["lastPrice"]),
        "change_pct": float(data["priceChangePercent"]),
        "change": float(data["priceChange"]),
        "high": float(data["highPrice"]),
        "low": float(data["lowPrice"]),
        "volume": float(data["volume"]),
        "quote_volume": float(data["quoteVolume"]),
    }


async def get_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
    quote: str = "USDT",
) -> pd.DataFrame:
    client = await get_client()
    raw = await client.get_klines(
        symbol=_pair(symbol, quote), interval=interval, limit=limit
    )
    df = pd.DataFrame(
        raw,
        columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ],
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df


async def get_account_balance() -> list[dict]:
    client = await get_client()
    account = await client.get_account()
    return [
        {
            "asset": b["asset"],
            "free": float(b["free"]),
            "locked": float(b["locked"]),
        }
        for b in account["balances"]
        if float(b["free"]) > 0 or float(b["locked"]) > 0
    ]


async def place_market_order(
    symbol: str,
    side: str,
    quote_qty: float | None = None,
    quantity: float | None = None,
    quote: str = "USDT",
) -> dict:
    client = await get_client()
    pair = _pair(symbol, quote)
    if side.upper() == "BUY" and quote_qty is not None:
        return await client.order_market_buy(symbol=pair, quoteOrderQty=round(quote_qty, 2))
    if side.upper() == "SELL" and quantity is not None:
        return await client.order_market_sell(symbol=pair, quantity=quantity)
    raise ValueError("BUY requiere quote_qty; SELL requiere quantity")
