from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 تحلیل درخواستی"), KeyboardButton(text="🔥 سیگنال‌های برتر امروز")],
            [KeyboardButton(text="⚙️ تنظیمات"), KeyboardButton(text="⏸ توقف / فعال‌سازی")]
        ],
        resize_keyboard=True
    )

def symbol_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC/USDT", callback_data="sym_BTCUSDT"),
         InlineKeyboardButton(text="ETH/USDT", callback_data="sym_ETHUSDT")],
        [InlineKeyboardButton(text="SOL/USDT", callback_data="sym_SOLUSDT"),
         InlineKeyboardButton(text="BNB/USDT", callback_data="sym_BNBUSDT")],
        [InlineKeyboardButton(text="🔍 جستجوی ارز دیگر", callback_data="sym_search")]
    ])

def timeframe_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 دقیقه", callback_data="tf_5m"),
         InlineKeyboardButton(text="15 دقیقه", callback_data="tf_15m")],
        [InlineKeyboardButton(text="1 ساعت", callback_data="tf_1h"),
         InlineKeyboardButton(text="4 ساعت", callback_data="tf_4h")]
    ])

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ شروع مانیتورینگ", callback_data="confirm_start")]
    ])