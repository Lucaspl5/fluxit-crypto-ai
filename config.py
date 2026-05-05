import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

DATABASE_URL = os.getenv("DATABASE_URL", "")

PORT = int(os.getenv("PORT", "8080"))

TRADING_MODE = os.getenv("TRADING_MODE", "paper")      # "paper" | "live"
USE_TESTNET = os.getenv("USE_TESTNET", "false").lower() == "true"
QUOTE_CURRENCY = os.getenv("QUOTE_CURRENCY", "USDT")

ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))
SIGNAL_SCAN_INTERVAL = int(os.getenv("SIGNAL_SCAN_INTERVAL", "300"))

WATCHLIST_DEFAULT: list[str] = [
    s.strip() for s in os.getenv(
        "WATCHLIST_DEFAULT", "BTC,ETH,BNB,SOL,ADA,XRP,DOGE,AVAX,MATIC,LINK"
    ).split(",") if s.strip()
]
