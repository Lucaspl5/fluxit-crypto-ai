from telegram import InlineKeyboardButton, InlineKeyboardMarkup

INTERVALS = ["15m", "1h", "4h", "1d"]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Señales",      callback_data="menu_signals"),
            InlineKeyboardButton("📋 Órdenes",      callback_data="menu_trades"),
        ],
        [
            InlineKeyboardButton("💰 Rendimiento",  callback_data="menu_performance"),
            InlineKeyboardButton("📍 Posiciones",   callback_data="menu_positions"),
        ],
        [
            InlineKeyboardButton("🏦 Cuenta",       callback_data="menu_balance"),
            InlineKeyboardButton("⚙️ Estado",       callback_data="menu_status"),
        ],
        [
            InlineKeyboardButton("🔄 Actualizar",   callback_data="menu_refresh"),
        ],
    ])


def confirm_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_{order_id}"),
        InlineKeyboardButton("❌ Cancelar",  callback_data="cancel_order"),
    ]])


def analysis_interval_keyboard(symbol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(iv, callback_data=f"analysis_{symbol}_{iv}")
        for iv in INTERVALS
    ]])


def delete_alert_keyboard(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Eliminar alerta", callback_data=f"delete_alert_{alert_id}")
    ]])


def cancel_sltp_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Cancelar orden SL/TP", callback_data=f"cancel_sltp_{order_id}")
    ]])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Volver al menú", callback_data="menu_refresh")
    ]])
