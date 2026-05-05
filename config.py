import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

_raw_users = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: list[int] = [int(u.strip()) for u in _raw_users.split(",") if u.strip()]

TRADING_MODE = os.getenv("TRADING_MODE", "paper")          # "paper" | "live"
USE_TESTNET = os.getenv("USE_TESTNET", "false").lower() == "true"
QUOTE_CURRENCY = os.getenv("QUOTE_CURRENCY", "USDT")

ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "30"))

WATCHLIST_DEFAULT: list[str] = [
    s.strip() for s in os.getenv(
        "WATCHLIST_DEFAULT", "BTC,ETH,BNB,SOL,ADA,XRP,DOGE,AVAX,MATIC,LINK"
    ).split(",") if s.strip()
]
