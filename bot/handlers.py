import uuid
import logging
from functools import wraps

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ALLOWED_USERS, TRADING_MODE, QUOTE_CURRENCY, WATCHLIST_DEFAULT
from database.db import (
    add_alert, get_alerts, delete_alert,
    add_to_watchlist, remove_from_watchlist, get_watchlist,
    get_paper_balance, update_paper_balance, add_paper_trade, get_paper_portfolio,
)
from trading.binance_client import get_ticker_24h, get_price, place_market_order, get_account_balance
from trading.analysis import get_analysis
from trading.signals import generate_signal, scan_watchlist
from bot.keyboards import confirm_order_keyboard, analysis_interval_keyboard, delete_alert_keyboard
from bot.messages import format_price, format_analysis, format_signal, format_portfolio

logger = logging.getLogger(__name__)

# ── Auth decorator ─────────────────────────────────────────────────────────────

def auth_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text("⛔ No autorizado.")
            return
        return await func(update, context)
    return wrapper


# ── Pending orders (in-memory store, keyed by short UUID) ─────────────────────

def _store_order(context: ContextTypes.DEFAULT_TYPE, payload: dict) -> str:
    order_id = uuid.uuid4().hex[:8]
    context.bot_data.setdefault("pending_orders", {})[order_id] = payload
    return order_id


def _pop_order(context: ContextTypes.DEFAULT_TYPE, order_id: str) -> dict | None:
    return context.bot_data.get("pending_orders", {}).pop(order_id, None)


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ No autorizado.")
        return
    mode_label = "📄 Paper Trading" if TRADING_MODE == "paper" else "⚡ Live Trading"
    text = (
        "🤖 *FluxIT Crypto Bot*\n\n"
        "💰 `/precio BTC` — Precio y stats 24h\n"
        "📊 `/analisis BTC` — Análisis técnico (RSI, MACD, BB)\n"
        "📡 `/senales` — Señales del mercado en tu watchlist\n"
        "🔔 `/alerta BTC 50000 above` — Crear alerta de precio\n"
        "📋 `/alertas` — Ver y eliminar alertas activas\n"
        "👁 `/watchlist` — Gestionar watchlist\n"
        "💼 `/portfolio` — Ver posiciones y valor\n"
        "💳 `/balance` — Balance de cuenta\n"
        "🟢 `/comprar BTC 100` — Comprar con 100 USDT\n"
        "🔴 `/vender BTC 0.001` — Vender cantidad\n\n"
        f"Modo actual: *{mode_label}*"
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
        await update.message.reply_text("❌ Dirección debe ser `above` o `below`.", parse_mode=ParseMode.MARKDOWN)
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
    user_id = update.effective_user.id
    alerts = get_alerts(user_id=user_id, active_only=True)
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
            if add_to_watchlist(user_id, symbol):
                await update.message.reply_text(f"✅ *{symbol}* añadido a tu watchlist.", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(f"*{symbol}* ya está en tu watchlist.", parse_mode=ParseMode.MARKDOWN)
            return
        if action in ("remove", "eliminar") and len(context.args) > 1:
            symbol = context.args[1].upper().removesuffix("USDT")
            remove_from_watchlist(user_id, symbol)
            await update.message.reply_text(f"❌ *{symbol}* eliminado de tu watchlist.", parse_mode=ParseMode.MARKDOWN)
            return

    wl = get_watchlist(user_id)
    if not wl:
        await update.message.reply_text(
            "Tu watchlist está vacía.\n"
            "Añade: `/watchlist add BTC`\n"
            "Elimina: `/watchlist remove BTC`",
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
        prices = {}
        for sym in portfolio:
            try:
                prices[sym] = await get_price(sym, quote=QUOTE_CURRENCY)
            except Exception:
                prices[sym] = 0.0
        await update.message.reply_text(
            format_portfolio(portfolio, prices, usdt),
            parse_mode=ParseMode.MARKDOWN,
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

@auth_required
async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Uso: `/comprar BTC 100` (gasta 100 USDT)", parse_mode=ParseMode.MARKDOWN)
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
    try:
        price = await get_price(symbol, quote=QUOTE_CURRENCY)
        qty = amount_usdt / price
        order_id = _store_order(context, {
            "side": "BUY", "symbol": symbol,
            "amount_usdt": amount_usdt, "quantity": qty,
            "user_id": update.effective_user.id,
        })
        mode_label = "📄 Paper Trading" if TRADING_MODE == "paper" else "⚡ LIVE TRADING"
        await update.message.reply_text(
            f"⚠️ *Confirmar compra*\n\n"
            f"Par: *{symbol}/USDT*\n"
            f"Precio: `${price:,.4f}`\n"
            f"Gasto: `${amount_usdt:,.2f} USDT`\n"
            f"Recibes ≈ `{qty:.6f} {symbol}`\n\n"
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


# ── Callback query handler ─────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await query.answer("⛔ No autorizado.")
        return

    await query.answer()
    data = query.data

    # ── Cancel order
    if data == "cancel_order":
        await query.edit_message_text("❌ Orden cancelada.")
        return

    # ── Delete alert
    if data.startswith("delete_alert_"):
        alert_id = int(data.removeprefix("delete_alert_"))
        delete_alert(alert_id, user_id)
        await query.edit_message_text("🗑 Alerta eliminada.")
        return

    # ── Change analysis interval
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

    # ── Confirm order
    if data.startswith("confirm_"):
        order_id = data.removeprefix("confirm_")
        order = _pop_order(context, order_id)
        if order is None:
            await query.edit_message_text("⚠️ La orden ya no está disponible.")
            return
        if order["user_id"] != user_id:
            await query.edit_message_text("⛔ No autorizado.")
            return

        symbol = order["symbol"]
        side = order["side"]

        if TRADING_MODE == "paper":
            await _execute_paper_order(query, context, order)
        else:
            await _execute_live_order(query, order)
        return


async def _execute_paper_order(query, context, order: dict) -> None:
    user_id = order["user_id"]
    symbol = order["symbol"]
    side = order["side"]

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
                f"❌ Saldo insuficiente.\nTienes `${balance:,.2f} USDT` y necesitas `${amount:,.2f}`.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        qty = amount / price
        update_paper_balance(user_id, balance - amount)
        add_paper_trade(user_id, symbol, "BUY", qty, price)
        await query.edit_message_text(
            f"✅ *Compra ejecutada (Paper)*\n"
            f"Compraste `{qty:.6f} {symbol}` a `${price:,.4f}`\n"
            f"Total: `${amount:,.2f} USDT` debitados",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        qty = order["quantity"]
        portfolio = get_paper_portfolio(user_id)
        available = portfolio.get(symbol, 0.0)
        if available < qty:
            await query.edit_message_text(
                f"❌ Saldo insuficiente.\nTienes `{available:.6f} {symbol}` y quieres vender `{qty:.6f}`.",
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
