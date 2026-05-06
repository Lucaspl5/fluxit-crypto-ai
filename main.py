import asyncio
import json
import logging
import os

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
    cmd_buy, cmd_sell, cmd_positions, cmd_protect, cmd_menu,
    callback_handler,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


# ── Web server ─────────────────────────────────────────────────────────────────

async def _landing(request: web.Request) -> web.Response:
    return web.FileResponse(os.path.join(_WEB_DIR, "landing.html"))


async def _dashboard(request: web.Request) -> web.Response:
    return web.FileResponse(os.path.join(_WEB_DIR, "dashboard.html"))


async def _health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def _api_dashboard(request: web.Request) -> web.Response:
    """JSON endpoint consumed by the dashboard page."""
    from database.db import (
        get_paper_balance, get_paper_portfolio,
        get_active_sl_tp_orders, get_recent_trades, get_avg_entry_price,
    )
    from trading.market_data import get_prices_batch
    from config import TELEGRAM_CHAT_ID

    user_id = TELEGRAM_CHAT_ID
    portfolio = get_paper_portfolio(user_id)
    usdt = get_paper_balance(user_id)

    try:
        prices = await get_prices_batch(list(portfolio.keys()))
    except Exception:
        prices = {}

    sl_tp_orders = get_active_sl_tp_orders()
    sl_tp_map: dict[str, dict] = {}
    for o in sl_tp_orders:
        if o["user_id"] == user_id:
            sl_tp_map[o["symbol"]] = {
                "stop_loss": float(o["stop_loss"]) if o["stop_loss"] else None,
                "take_profit": float(o["take_profit"]) if o["take_profit"] else None,
            }

    positions = []
    crypto_value = 0.0
    for sym, qty in portfolio.items():
        price = prices.get(sym, 0.0)
        entry = get_avg_entry_price(user_id, sym) or price
        value = qty * price
        crypto_value += value
        sltp = sl_tp_map.get(sym, {})
        positions.append({
            "symbol": sym,
            "quantity": qty,
            "current_price": price,
            "avg_entry": entry,
            "value": value,
            "invested": qty * entry,
            "stop_loss": sltp.get("stop_loss"),
            "take_profit": sltp.get("take_profit"),
        })

    recent_trades = [dict(t) for t in get_recent_trades(user_id, limit=10)]

    payload = {
        "usdt": usdt,
        "crypto_value": crypto_value,
        "total": usdt + crypto_value,
        "positions": positions,
        "recent_trades": recent_trades,
    }
    return web.Response(
        text=json.dumps(payload, default=str),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def run_web_server() -> None:
    app = web.Application()
    app.router.add_get("/",              _landing)
    app.router.add_get("/dashboard",     _dashboard)
    app.router.add_get("/health",        _health)
    app.router.add_get("/api/dashboard", _api_dashboard)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Web server en puerto {PORT}")


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
    if not TELEGRAM_CHAT_ID:
        return
    try:
        from database.db import get_watchlist
        from trading.signals import scan_watchlist
        from config import WATCHLIST_DEFAULT
        from bot.messages import format_signal

        watchlist = get_watchlist(TELEGRAM_CHAT_ID) or WATCHLIST_DEFAULT
        results = await scan_watchlist(watchlist, interval="1h")

        # Guardar resultado en bot_data para que el menú lo use instantáneamente
        context.bot_data["last_signals"] = results

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

    app.add_handler(CommandHandler("menu",       cmd_menu))
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
    app.add_handler(CommandHandler("proteger",   cmd_protect))
    app.add_handler(CallbackQueryHandler(callback_handler))

    app.job_queue.run_repeating(_alert_job,  interval=ALERT_CHECK_INTERVAL, first=15)
    app.job_queue.run_repeating(_sl_tp_job,  interval=ALERT_CHECK_INTERVAL, first=20)
    app.job_queue.run_repeating(_signal_job, interval=SIGNAL_SCAN_INTERVAL, first=60)

    return app


# ── Entry point ────────────────────────────────────────────────────────────────

async def _run() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado.")

    init_db()
    await run_web_server()

    tg_app = _build_app()
    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("FluxIT Crypto Bot iniciado.")
        await asyncio.Event().wait()
        await tg_app.updater.stop()
        await tg_app.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
