import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import TELEGRAM_TOKEN, ALERT_CHECK_INTERVAL
from database.db import init_db
from trading.alerts import check_alerts
from trading.binance_client import close_client
from bot.handlers import (
    cmd_start, cmd_price, cmd_analysis,
    cmd_add_alert, cmd_list_alerts,
    cmd_signals, cmd_watchlist,
    cmd_portfolio, cmd_balance,
    cmd_buy, cmd_sell,
    callback_handler,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _alert_job(context) -> None:
    try:
        triggered = await check_alerts()
        for alert in triggered:
            verb = "subido por encima" if alert["direction"] == "above" else "bajado por debajo"
            await context.bot.send_message(
                chat_id=alert["user_id"],
                text=(
                    f"🔔 *ALERTA ACTIVADA*\n\n"
                    f"*{alert['symbol']}/USDT* ha {verb} de `${alert['target']:,.4f}`\n"
                    f"Precio actual: `${alert['price']:,.4f}`"
                ),
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Error en job de alertas")


async def _on_shutdown(app: Application) -> None:
    await close_client()


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN no configurado. Copia .env.example a .env y rellénalo.")

    init_db()

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_shutdown(_on_shutdown)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_start))
    app.add_handler(CommandHandler("precio",    cmd_price))
    app.add_handler(CommandHandler("analisis",  cmd_analysis))
    app.add_handler(CommandHandler("alerta",    cmd_add_alert))
    app.add_handler(CommandHandler("alertas",   cmd_list_alerts))
    app.add_handler(CommandHandler("senales",   cmd_signals))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("balance",   cmd_balance))
    app.add_handler(CommandHandler("comprar",   cmd_buy))
    app.add_handler(CommandHandler("vender",    cmd_sell))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Periodic alert checker
    app.job_queue.run_repeating(_alert_job, interval=ALERT_CHECK_INTERVAL, first=15)

    logger.info("FluxIT Crypto Bot iniciado.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
