import asyncio
import logging

from aiohttp import web
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PORT, ALERT_CHECK_INTERVAL, SIGNAL_SCAN_INTERVAL
from database.db import init_db
from trading.alerts import check_alerts, check_sl_tp
from trading.binance_client import close_client
from bot.handlers import (
    cmd_start, cmd_price, cmd_analysis,
    cmd_add_alert, cmd_list_alerts,
    cmd_signals, cmd_watchlist,
    cmd_portfolio, cmd_balance,
    cmd_buy, cmd_sell, cmd_positions,
    callback_handler,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Health check server ────────────────────────────────────────────────────────

async def _health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def run_health_server() -> None:
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Health server escuchando en puerto {PORT}")


# ── Background jobs ────────────────────────────────────────────────────────────

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


async def _sl_tp_job(context) -> None:
    try:
        triggered = await check_sl_tp()
        for order in triggered:
            emoji = "🛑" if order["type"] == "SL" else "✅"
            label = "STOP LOSS" if order["type"] == "SL" else "TAKE PROFIT"
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    f"{emoji} *{label} ACTIVADO*\n\n"
                    f"*{order['symbol']}/USDT*\n"
                    f"Cantidad vendida: `{order['quantity']:.6f}`\n"
                    f"Precio objetivo: `${order['target']:,.4f}`\n"
                    f"Precio ejecutado: `${order['price']:,.4f}`\n"
                    f"Ingresado: `${order['received']:,.2f} USDT`"
                ),
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Error en job de SL/TP")


async def _signal_job(context) -> None:
    """Scan watchlist every SIGNAL_SCAN_INTERVAL and notify strong signals."""
    if not TELEGRAM_CHAT_ID:
        return
    try:
        from database.db import get_watchlist
        from trading.signals import scan_watchlist
        from config import WATCHLIST_DEFAULT
        from bot.messages import format_signal

        watchlist = get_watchlist(TELEGRAM_CHAT_ID) or WATCHLIST_DEFAULT
        results = await scan_watchlist(watchlist, interval="1h")
        strong = [r for r in results if abs(r["score"]) >= 3]
        if strong:
            lines = ["📡 *Señal fuerte detectada*\n"]
            for sig in strong:
                lines.append(format_signal(sig))
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text="\n".join(lines),
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Error en job de señales")


# ── Bot builder ────────────────────────────────────────────────────────────────

def _build_app() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_start))
    app.add_handler(CommandHandler("precio",     cmd_price))
    app.add_handler(CommandHandler("analisis",   cmd_analysis))
    app.add_handler(CommandHandler("alerta",     cmd_add_alert))
    app.add_handler(CommandHandler("alertas",    cmd_list_alerts))
    app.add_handler(CommandHandler("senales",    cmd_signals))
    app.add_handler(CommandHandler("watchlist",  cmd_watchlist))
    app.add_handler(CommandHandler("portfolio",  cmd_portfolio))
    app.add_handler(CommandHandler("balance",    cmd_balance))
    app.add_handler(CommandHandler("comprar",    cmd_buy))
    app.add_handler(CommandHandler("vender",     cmd_sell))
    app.add_handler(CommandHandler("posiciones", cmd_positions))
    app.add_handler(CallbackQueryHandler(callback_handler))

    app.job_queue.run_repeating(_alert_job,  interval=ALERT_CHECK_INTERVAL,  first=15)
    app.job_queue.run_repeating(_sl_tp_job,  interval=ALERT_CHECK_INTERVAL,  first=20)
    app.job_queue.run_repeating(_signal_job, interval=SIGNAL_SCAN_INTERVAL,  first=60)

    return app


# ── Entry point ────────────────────────────────────────────────────────────────

async def _run() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado.")

    init_db()
    await run_health_server()

    tg_app = _build_app()
    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("FluxIT Crypto Bot iniciado.")
        await asyncio.Event().wait()   # block forever
        await tg_app.updater.stop()
        await tg_app.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
