# Binance client — solo para live trading (órdenes reales)
# Los datos de mercado (precios, OHLCV) usan CoinGecko via trading/market_data.py
# porque Binance bloquea IPs de Railway por restricción geográfica.

from binance import AsyncClient
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET

# Re-exportamos las funciones de datos desde market_data para compatibilidad
from trading.market_data import get_price, get_ticker_24h, get_klines  # noqa: F401

_client: AsyncClient | None = None


async def _get_client() -> AsyncClient:
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


async def get_account_balance() -> list[dict]:
    client = await _get_client()
    account = await client.get_account()
    return [
        {"asset": b["asset"], "free": float(b["free"]), "locked": float(b["locked"])}
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
    client = await _get_client()
    pair = f"{symbol.upper()}{quote.upper()}"
    if side.upper() == "BUY" and quote_qty is not None:
        return await client.order_market_buy(symbol=pair, quoteOrderQty=round(quote_qty, 2))
    if side.upper() == "SELL" and quantity is not None:
        return await client.order_market_sell(symbol=pair, quantity=quantity)
    raise ValueError("BUY requiere quote_qty; SELL requiere quantity")
