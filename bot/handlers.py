import uuid
import logging
from functools import wraps

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import TELEGRAM_CHAT_ID, TRADING_MODE, QUOTE_CURRENCY, WATCHLIST_DEFAULT
from database.db import (
    add_alert, get_alerts, delete_alert,
    add_to_watchlist, remove_from_watchlist, get_watchlist,
    get_paper_balance, update_paper_balance, add_paper_trade, get_paper_portfolio,
    add_sl_tp_order, get_sl_tp_orders_by_user, cancel_sl_tp_order,
    get_avg_entry_price, get_protected_symbols,
    get_recent_trades,
)
from trading.binance_client import get_ticker_24h, get_price, place_market_order, get_account_balance
from trading.analysis import get_analysis
from trading.signals import generate_signal, scan_watchlist
from bot.keyboards import confirm_order_keyboard, analysis_interval_keyboard, delete_alert_keyboard, cancel_sltp_keyboard, main_menu_keyboard, back_to_menu_keyboard
from bot.messages import format_price, format_analysis, format_signal, format_portfolio, format_menu_header, format_performance, format_recent_trades, format_status

logger = logging.getLogger(__name__)


# ── Auth ───────────────────────────────────────────────────────────────────────

def auth_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if TELEGRAM_CHAT_ID and update.effective_user.id != TELEGRAM_CHAT_ID:
            await update.message.reply_text("⛔ No autorizado.")
            return
        return await func(update, context)
    return wrapper


# ── Pending orders store ───────────────────────────────────────────────────────

def _store_order(context: ContextTypes.DEFAULT_TYPE, payload: dict) -> str:
    order_id = uuid.uuid4().hex[:8]
    context.bot_data.setdefault("pending_orders", {})[order_id] = payload
    return order_id


def _pop_order(context: ContextTypes.DEFAULT_TYPE, order_id: str) -> dict | None:
    return context.bot_data.get("pending_orders", {}).pop(order_id, None)


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if TELEGRAM_CHAT_ID and update.effective_user.id != TELEGRAM_CHAT_ID:
        await update.message.reply_text("⛔ No autorizado.")
        return
    mode_label = "📄 Paper Trading" if TRADING_MODE == "paper" else "⚡ Live Trading"
    text = (
        "🤖 *FluxIT Crypto Bot*\n\n"
        "💰 `/precio BTC` — Precio y stats 24h\n"
        "📊 `/analisis BTC` — Análisis técnico\n"
        "📡 `/senales` — Señales del mercado\n"
        "🔔 `/alerta BTC 50000 above` — Alerta de precio\n"
        "📋 `/alertas` — Ver alertas activas\n"
        "👁 `/watchlist` — Gestionar watchlist\n"
        "💼 `/portfolio` — Ver posiciones\n"
        "💳 `/balance` — Balance de cuenta\n"
        "🟢 `/comprar BTC 100` — Comprar con 100 USDT\n"
        "       _Opciones: `sl=45000 tp=55000`_\n"
        "🔴 `/vender BTC 0.001` — Vender cantidad\n"
        "📌 `/posiciones` — Ver órdenes SL/TP activas\n"
        "🛡 `/proteger` — Poner SL/TP a todas las posiciones\n\n"
        f"Modo: *{mode_label}*"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ── /precio ────────────────────────────────────────────────────────────────────

@auth_required
async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: `/precio BTC`", parse_mode=ParseMode.MARKDOWN)
        return
    symbol = context.args[0].upper().removesuffix("USDT")
    msg = await update.message.reply_text("⏳ Consultando...")
    try:
        data = await get_ticker_24h(symbol, quote=QUOTE_CURRENCY)
        await msg.edit_text(format_price(symbol, data), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


# ── /analisis ──────────────────────────────────────────────────────────────────

@auth_required
async def cmd_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: `/analisis BTC [1h]`", parse_mode=ParseMode.MARKDOWN)
        return
    symbol = context.args[0].upper().removesuffix("USDT")
    interval = context.args[1] if len(context.args) > 1 else "1h"
    msg = await update.message.reply_text("⏳ Analizando...")
    try:
        data = await get_analysis(symbol, interval=interval, quote=QUOTE_CURRENCY)
        await msg.edit_text(
            format_analysis(data),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=analysis_interval_keyboard(symbol),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


# ── /alerta ────────────────────────────────────────────────────────────────────

@auth_required
async def cmd_add_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "Uso: `/alerta BTC 50000 above`\n`above` = cuando suba | `below` = cuando baje",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    symbol = context.args[0].upper().removesuffix("USDT")
    try:
        target = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Precio inválido.")
        return
    direction = context.args[2].lower()
    if direction not in ("above", "below"):
        await update.message.reply_text("❌ Usa `above` o `below`.", parse_mode=ParseMode.MARKDOWN)
        return
    add_alert(update.effective_user.id, symbol, target, direction)
    verb = "suba por encima" if direction == "above" else "baje por debajo"
    await update.message.reply_text(
        f"🔔 Alerta creada: te avisaré cuando *{symbol}* {verb} de `${target:,.4f}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /alertas ───────────────────────────────────────────────────────────────────

@auth_required
async def cmd_list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts = get_alerts(user_id=update.effective_user.id, active_only=True)
    if not alerts:
        await update.message.reply_text("No tienes alertas activas.")
        return
    for alert in alerts:
        verb = "⬆️ suba sobre" if alert["direction"] == "above" else "⬇️ baje bajo"
        await update.message.reply_text(
            f"🔔 `[{alert['id']}]` *{alert['symbol']}* — {verb} `${alert['target_price']:,.4f}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=delete_alert_keyboard(alert["id"]),
        )


# ── /senales ───────────────────────────────────────────────────────────────────

@auth_required
async def cmd_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    watchlist = get_watchlist(user_id) or WATCHLIST_DEFAULT
    interval = context.args[0] if context.args else "1h"
    msg = await update.message.reply_text(f"⏳ Escaneando {len(watchlist)} pares ({interval})...")
    try:
        results = await scan_watchlist(watchlist, interval=interval)
        lines = [f"📡 *Señales del mercado ({interval})*\n"]
        for sig in results:
            lines.append(format_signal(sig))
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


# ── /watchlist ─────────────────────────────────────────────────────────────────

@auth_required
async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        action = context.args[0].lower()
        if action in ("add", "agregar") and len(context.args) > 1:
            symbol = context.args[1].upper().removesuffix("USDT")
            add_to_watchlist(user_id, symbol)
            await update.message.reply_text(f"✅ *{symbol}* añadido.", parse_mode=ParseMode.MARKDOWN)
            return
        if action in ("remove", "eliminar") and len(context.args) > 1:
            symbol = context.args[1].upper().removesuffix("USDT")
            remove_from_watchlist(user_id, symbol)
            await update.message.reply_text(f"❌ *{symbol}* eliminado.", parse_mode=ParseMode.MARKDOWN)
            return

    wl = get_watchlist(user_id)
    if not wl:
        await update.message.reply_text(
            "Tu watchlist está vacía.\n`/watchlist add BTC` para añadir.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "👁 *Tu Watchlist:*\n" + "\n".join(f"• {s}" for s in wl),
            parse_mode=ParseMode.MARKDOWN,
        )


# ── /portfolio ─────────────────────────────────────────────────────────────────

@auth_required
async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if TRADING_MODE == "paper":
        portfolio = get_paper_portfolio(user_id)
        usdt = get_paper_balance(user_id)
        try:
            from trading.market_data import get_prices_batch
            prices = await get_prices_batch(list(portfolio.keys()))
        except Exception:
            prices = {}
        await update.message.reply_text(
            format_portfolio(portfolio, prices, usdt), parse_mode=ParseMode.MARKDOWN
        )
    else:
        try:
            balances = await get_account_balance()
            lines = ["💼 *Balance en Binance*\n"]
            for b in balances:
                lines.append(f"• *{b['asset']}*: libre `{b['free']:.6f}` | bloq. `{b['locked']:.6f}`")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")


# ── /balance ───────────────────────────────────────────────────────────────────

@auth_required
async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if TRADING_MODE == "paper":
        usdt = get_paper_balance(user_id)
        portfolio = get_paper_portfolio(user_id)
        crypto_val = 0.0
        for sym, qty in portfolio.items():
            try:
                crypto_val += qty * await get_price(sym, quote=QUOTE_CURRENCY)
            except Exception:
                pass
        await update.message.reply_text(
            f"💳 *Balance (Paper Trading)*\n"
            f"💵 USDT: `${usdt:,.2f}`\n"
            f"📊 En cripto: `${crypto_val:,.2f}`\n"
            f"💰 Total: `${usdt + crypto_val:,.2f}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        try:
            balances = await get_account_balance()
            lines = ["💳 *Balance en Binance*\n"]
            for b in balances:
                total = b["free"] + b["locked"]
                lines.append(f"• *{b['asset']}*: `{total:.6f}` (libre: `{b['free']:.6f}`)")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")


# ── /comprar ───────────────────────────────────────────────────────────────────

def _parse_sl_tp(args: list[str]) -> tuple[float | None, float | None]:
    """Extract sl=X and tp=X from args list."""
    sl = tp = None
    for arg in args:
        if arg.lower().startswith("sl="):
            try:
                sl = float(arg.split("=")[1])
            except ValueError:
                pass
        elif arg.lower().startswith("tp="):
            try:
                tp = float(arg.split("=")[1])
            except ValueError:
                pass
    return sl, tp


@auth_required
async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: `/comprar BTC 100`\nOpcional: `/comprar BTC 100 sl=45000 tp=55000`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    symbol = context.args[0].upper().removesuffix("USDT")
    try:
        amount_usdt = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.")
        return
    if amount_usdt <= 0:
        await update.message.reply_text("❌ El monto debe ser positivo.")
        return

    sl, tp = _parse_sl_tp(context.args[2:])

    try:
        price = await get_price(symbol, quote=QUOTE_CURRENCY)
        qty = amount_usdt / price

        # Validate SL/TP
        if sl and sl >= price:
            await update.message.reply_text(f"❌ El Stop Loss (`${sl:,.4f}`) debe estar por debajo del precio actual (`${price:,.4f}`).", parse_mode=ParseMode.MARKDOWN)
            return
        if tp and tp <= price:
            await update.message.reply_text(f"❌ El Take Profit (`${tp:,.4f}`) debe estar por encima del precio actual (`${price:,.4f}`).", parse_mode=ParseMode.MARKDOWN)
            return

        order_id = _store_order(context, {
            "side": "BUY", "symbol": symbol,
            "amount_usdt": amount_usdt, "quantity": qty,
            "user_id": update.effective_user.id,
            "sl": sl, "tp": tp,
        })

        sl_line = f"\n🛑 Stop Loss: `${sl:,.4f}`" if sl else ""
        tp_line = f"\n✅ Take Profit: `${tp:,.4f}`" if tp else ""
        mode_label = "📄 Paper Trading" if TRADING_MODE == "paper" else "⚡ LIVE TRADING"

        await update.message.reply_text(
            f"⚠️ *Confirmar compra*\n\n"
            f"Par: *{symbol}/USDT*\n"
            f"Precio: `${price:,.4f}`\n"
            f"Gasto: `${amount_usdt:,.2f} USDT`\n"
            f"Recibes ≈ `{qty:.6f} {symbol}`"
            f"{sl_line}{tp_line}\n\n"
            f"Modo: *{mode_label}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=confirm_order_keyboard(order_id),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ── /vender ────────────────────────────────────────────────────────────────────

@auth_required
async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Uso: `/vender BTC 0.001`", parse_mode=ParseMode.MARKDOWN)
        return
    symbol = context.args[0].upper().removesuffix("USDT")
    try:
        quantity = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Cantidad inválida.")
        return
    if quantity <= 0:
        await update.message.reply_text("❌ La cantidad debe ser positiva.")
        return

    try:
        price = await get_price(symbol, quote=QUOTE_CURRENCY)
        value = quantity * price
        order_id = _store_order(context, {
            "side": "SELL", "symbol": symbol,
            "quantity": quantity, "amount_usdt": value,
            "user_id": update.effective_user.id,
            "sl": None, "tp": None,
        })
        mode_label = "📄 Paper Trading" if TRADING_MODE == "paper" else "⚡ LIVE TRADING"
        await update.message.reply_text(
            f"⚠️ *Confirmar venta*\n\n"
            f"Par: *{symbol}/USDT*\n"
            f"Precio: `${price:,.4f}`\n"
            f"Vendes: `{quantity:.6f} {symbol}`\n"
            f"Recibes ≈ `${value:,.2f} USDT`\n\n"
            f"Modo: *{mode_label}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=confirm_order_keyboard(order_id),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ── /posiciones ────────────────────────────────────────────────────────────────

@auth_required
async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = get_sl_tp_orders_by_user(user_id)
    if not orders:
        await update.message.reply_text("No tienes órdenes SL/TP activas.")
        return
    for order in orders:
        sl_str = f"🛑 SL: `${order['stop_loss']:,.4f}`" if order["stop_loss"] else "🛑 SL: —"
        tp_str = f"✅ TP: `${order['take_profit']:,.4f}`" if order["take_profit"] else "✅ TP: —"
        await update.message.reply_text(
            f"📌 *{order['symbol']}/USDT* `[{order['id']}]`\n"
            f"Cantidad: `{order['quantity']:.6f}`\n"
            f"Entrada: `${order['entry_price']:,.4f}`\n"
            f"{sl_str}\n{tp_str}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_sltp_keyboard(order["id"]),
        )


# ── /menu — Dashboard principal ───────────────────────────────────────────────

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if TELEGRAM_CHAT_ID and update.effective_user.id != TELEGRAM_CHAT_ID:
        await update.message.reply_text("⛔ No autorizado.")
        return
    from datetime import datetime
    now = datetime.now().strftime("%H:%M")
    await update.message.reply_text(
        format_menu_header(now),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── /proteger ─────────────────────────────────────────────────────────────────

@auth_required
async def cmd_protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    portfolio = get_paper_portfolio(user_id)

    if not portfolio:
        await update.message.reply_text("No tienes posiciones abiertas.")
        return

    # Parse optional SL% and TP%
    try:
        sl_pct = float(context.args[0]) if len(context.args) > 0 else 5.0
        tp_pct = float(context.args[1]) if len(context.args) > 1 else 10.0
    except ValueError:
        await update.message.reply_text("Uso: `/proteger [sl%] [tp%]`\nEjemplo: `/proteger 5 10`", parse_mode=ParseMode.MARKDOWN)
        return

    already_protected = get_protected_symbols(user_id)
    to_protect = {s: q for s, q in portfolio.items() if s not in already_protected}

    if not to_protect:
        await update.message.reply_text("✅ Todas tus posiciones ya tienen SL/TP activo.")
        return

    msg = await update.message.reply_text(f"⏳ Protegiendo {len(to_protect)} posiciones...")

    lines = [f"🛡 *Protección automática aplicada* (SL -{sl_pct}% / TP +{tp_pct}%)\n"]
    errors = []

    for symbol, qty in to_protect.items():
        try:
            from trading.market_data import get_price as _get_price
            entry = get_avg_entry_price(user_id, symbol) or await _get_price(symbol)
            sl = round(entry * (1 - sl_pct / 100), 6)
            tp = round(entry * (1 + tp_pct / 100), 6)
            add_sl_tp_order(user_id, symbol, qty, entry, sl, tp)
            lines.append(
                f"• *{symbol}*: entrada `${entry:,.4f}` | 🛑 SL `${sl:,.4f}` | ✅ TP `${tp:,.4f}`"
            )
        except Exception as e:
            errors.append(f"• {symbol}: {e}")

    if errors:
        lines.append("\n⚠️ Errores:\n" + "\n".join(errors))

    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── Callbacks ──────────────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    user_id = query.from_user.id

    if TELEGRAM_CHAT_ID and user_id != TELEGRAM_CHAT_ID:
        await query.answer("⛔ No autorizado.")
        return

    await query.answer()
    data = query.data

    # ── Menú principal
    if data in ("menu_refresh", "menu_signals", "menu_trades", "menu_performance",
                "menu_positions", "menu_balance", "menu_status"):
        await _handle_menu_callback(query, user_id, data, context)
        return

    if data == "cancel_order":
        await query.edit_message_text("❌ Orden cancelada.")
        return

    if data.startswith("delete_alert_"):
        alert_id = int(data.removeprefix("delete_alert_"))
        delete_alert(alert_id, user_id)
        await query.edit_message_text("🗑 Alerta eliminada.")
        return

    if data.startswith("cancel_sltp_"):
        order_id = int(data.removeprefix("cancel_sltp_"))
        cancel_sl_tp_order(order_id, user_id)
        await query.edit_message_text("🗑 Orden SL/TP cancelada.")
        return

    if data.startswith("analysis_"):
        _, symbol, interval = data.split("_", 2)
        try:
            analysis = await get_analysis(symbol, interval=interval, quote=QUOTE_CURRENCY)
            await query.edit_message_text(
                format_analysis(analysis),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=analysis_interval_keyboard(symbol),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
        return

    if data.startswith("confirm_"):
        order_id = data.removeprefix("confirm_")
        order = _pop_order(context, order_id)
        if order is None:
            await query.edit_message_text("⚠️ La orden ya no está disponible.")
            return
        if order["user_id"] != user_id:
            await query.edit_message_text("⛔ No autorizado.")
            return
        if TRADING_MODE == "paper":
            await _execute_paper_order(query, order)
        else:
            await _execute_live_order(query, order)


async def _handle_menu_callback(query, user_id: int, data: str, context) -> None:
    from datetime import datetime
    from trading.market_data import get_prices_batch
    from telegram.error import BadRequest

    now = datetime.now().strftime("%H:%M")

    if data == "menu_refresh":
        try:
            await query.edit_message_text(
                format_menu_header(now),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    if data == "menu_signals":
        watchlist = get_watchlist(user_id) or WATCHLIST_DEFAULT
        try:
            await query.edit_message_text(
                f"⏳ Escaneando {len(watchlist)} pares...",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_menu_keyboard(),
            )
            results = await scan_watchlist(watchlist, interval="1h")
            lines = ["📊 *Señales del mercado (1h)*\n"]
            for sig in results:
                lines.append(format_signal(sig))
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=back_to_menu_keyboard())

    elif data == "menu_trades":
        try:
            trades = get_recent_trades(user_id)
            await query.edit_message_text(
                format_recent_trades(trades),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=back_to_menu_keyboard())

    elif data == "menu_performance":
        try:
            portfolio = get_paper_portfolio(user_id)
            usdt = get_paper_balance(user_id)
            try:
                prices = await get_prices_batch(list(portfolio.keys()))
            except Exception:
                prices = {}
            entry_prices = {sym: get_avg_entry_price(user_id, sym) or prices.get(sym, 0) for sym in portfolio}
            await query.edit_message_text(
                format_performance(portfolio, prices, entry_prices, usdt),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=back_to_menu_keyboard())

    elif data == "menu_positions":
        try:
            orders = get_sl_tp_orders_by_user(user_id)
            if not orders:
                text = "📍 *Posiciones SL/TP*\n\n_Sin órdenes activas._"
            else:
                lines = ["📍 *Posiciones con SL/TP activo*\n"]
                for o in orders:
                    sl_str = f"SL: `${float(o['stop_loss']):,.4f}`" if o["stop_loss"] else "SL: —"
                    tp_str = f"TP: `${float(o['take_profit']):,.4f}`" if o["take_profit"] else "TP: —"
                    lines.append(
                        f"*{o['symbol']}* `{float(o['quantity']):.6f}` @ `${float(o['entry_price']):,.4f}`\n"
                        f"  {sl_str}  |  {tp_str}"
                    )
                text = "\n".join(lines)
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_to_menu_keyboard())
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=back_to_menu_keyboard())

    elif data == "menu_balance":
        try:
            usdt = get_paper_balance(user_id)
            portfolio = get_paper_portfolio(user_id)
            try:
                prices = await get_prices_batch(list(portfolio.keys()))
            except Exception:
                prices = {}
            crypto_val = sum(portfolio.get(s, 0) * prices.get(s, 0) for s in portfolio)
            await query.edit_message_text(
                f"🏦 *Cuenta (Paper Trading)*\n\n"
                f"💵 USDT disponible: `${usdt:,.2f}`\n"
                f"📊 En cripto: `${crypto_val:,.2f}`\n"
                f"💰 Total: `${usdt + crypto_val:,.2f}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=back_to_menu_keyboard())

    elif data == "menu_status":
        try:
            active_alerts = len(get_alerts(user_id=user_id, active_only=True))
            active_sltp = len(get_sl_tp_orders_by_user(user_id))
            watchlist = get_watchlist(user_id) or WATCHLIST_DEFAULT
            await query.edit_message_text(
                format_status(TRADING_MODE, active_alerts, active_sltp, len(watchlist)),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=back_to_menu_keyboard())


async def _execute_paper_order(query, order: dict) -> None:
    user_id = order["user_id"]
    symbol = order["symbol"]
    side = order["side"]
    sl = order.get("sl")
    tp = order.get("tp")

    try:
        price = await get_price(symbol, quote=QUOTE_CURRENCY)
    except Exception as e:
        await query.edit_message_text(f"❌ Error obteniendo precio: {e}")
        return

    if side == "BUY":
        amount = order["amount_usdt"]
        balance = get_paper_balance(user_id)
        if balance < amount:
            await query.edit_message_text(
                f"❌ Saldo insuficiente.\nTienes `${balance:,.2f} USDT`.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        qty = amount / price
        update_paper_balance(user_id, balance - amount)
        add_paper_trade(user_id, symbol, "BUY", qty, price)

        # Register SL/TP if set
        sltp_line = ""
        if sl or tp:
            add_sl_tp_order(user_id, symbol, qty, price, sl, tp)
            sltp_line = "\n📌 _Orden SL/TP registrada y activa._"

        await query.edit_message_text(
            f"✅ *Compra ejecutada (Paper)*\n"
            f"Compraste `{qty:.6f} {symbol}` a `${price:,.4f}`\n"
            f"Total: `${amount:,.2f} USDT` debitados"
            f"{sltp_line}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        qty = order["quantity"]
        portfolio = get_paper_portfolio(user_id)
        available = portfolio.get(symbol, 0.0)
        if available < qty:
            await query.edit_message_text(
                f"❌ Solo tienes `{available:.6f} {symbol}`.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        received = qty * price
        update_paper_balance(user_id, get_paper_balance(user_id) + received)
        add_paper_trade(user_id, symbol, "SELL", qty, price)
        await query.edit_message_text(
            f"✅ *Venta ejecutada (Paper)*\n"
            f"Vendiste `{qty:.6f} {symbol}` a `${price:,.4f}`\n"
            f"Recibiste `${received:,.2f} USDT`",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _execute_live_order(query, order: dict) -> None:
    symbol = order["symbol"]
    side = order["side"]
    try:
        if side == "BUY":
            result = await place_market_order(symbol, "BUY", quote_qty=order["amount_usdt"])
        else:
            result = await place_market_order(symbol, "SELL", quantity=order["quantity"])
        await query.edit_message_text(
            f"✅ *Orden enviada a Binance*\n"
            f"ID: `{result['orderId']}`\n"
            f"Estado: `{result['status']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Error en Binance: {e}")
