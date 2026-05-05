from telegram import InlineKeyboardButton, InlineKeyboardMarkup

INTERVALS = ["15m", "1h", "4h", "1d"]


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
