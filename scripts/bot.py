import asyncio
import logging
import json
import os
import signal
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import sys
from pathlib import Path
from datetime import datetime, timezone
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.database import init_db, save_user_settings, get_user, set_user_active, get_active_users_grouped, get_all_users
from utils.keyboards import main_menu_kb, symbol_kb, timeframe_kb, confirm_kb
from utils.signal_engine import get_signal, run_full_top_coins_pipeline
from utils.config import BOT_TOKEN, ADMIN_ID
from utils.log_config import setup_logging

setup_logging("bot.log")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------------------------------------------------------------
# Health Check Server برای Render (جلوگیری از خطای Port/Health Check)
# ---------------------------------------------------------------------
async def health_check(request):
    return web.Response(text="Bot is live and running!")

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"🌐 Health check server started on port {port}")

# ---------------------------------------------------------------------
# قفل سراسری برای جلوگیری از اسپم و درخواست‌های همزمان (Rate Limit Protection)
# ---------------------------------------------------------------------
is_top_coins_processing = False

# --- FSM States ---
class Onboarding(StatesGroup):
    waiting_for_name = State()
    waiting_for_symbol = State()
    waiting_for_timeframe = State()
    waiting_for_confirmation = State()

class OnDemand(StatesGroup):
    waiting_for_symbol = State()
    waiting_for_timeframe = State()

# =====================================================================
# 1. هندلرهای شروع و ثبت‌نام (بدون تغییر نسبت به قبل)
# =====================================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user:
        await message.answer(f"👋 خوش برگشتی {user['name']}!\nاز منوی زیر انتخاب کن:", reply_markup=main_menu_kb())
    else:
        await message.answer("👋 به ربات سیگنال‌دهی هوشمند خوش آمدید!\n\nبرای شروع، لطفاً نام خود را وارد کنید:")
        await state.set_state(Onboarding.waiting_for_name)

@dp.message(Onboarding.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    if message.text in ["📊 تحلیل درخواستی", "🔥 سیگنال‌های برتر امروز", "⚙️ تنظیمات", "⏸ توقف / فعال‌سازی"]:
        await state.clear()
        await message.answer("عملیات لغو شد.", reply_markup=main_menu_kb())
        return
    await state.update_data(name=message.text)
    await message.answer("🪙 لطفاً ارز دیجیتال مورد نظر خود را انتخاب کنید:", reply_markup=symbol_kb())
    await state.set_state(Onboarding.waiting_for_symbol)

@dp.callback_query(Onboarding.waiting_for_symbol, F.data.startswith("sym_"))
async def process_symbol(cb: CallbackQuery, state: FSMContext):
    if cb.data == "sym_search":
        await cb.message.edit_text("🔍 لطفاً نماد ارز را به انگلیسی تایپ کنید (مثال: ADAUSDT):")
        return
    symbol = cb.data.split("sym_")[1]
    await state.update_data(symbol=symbol)
    await cb.message.edit_text(f"✅ ارز انتخاب شده: {symbol}\n\n⏱ حالا تایم‌فریم را انتخاب کنید:", reply_markup=timeframe_kb())
    await state.set_state(Onboarding.waiting_for_timeframe)

@dp.message(Onboarding.waiting_for_symbol)
async def process_symbol_search(message: Message, state: FSMContext):
    symbol = message.text.upper()
    await state.update_data(symbol=symbol)
    await message.answer(f"✅ ارز انتخاب شده: {symbol}\n\n⏱ حالا تایم‌فریم را انتخاب کنید:", reply_markup=timeframe_kb())
    await state.set_state(Onboarding.waiting_for_timeframe)

@dp.callback_query(Onboarding.waiting_for_timeframe, F.data.startswith("tf_"))
async def process_timeframe(cb: CallbackQuery, state: FSMContext):
    timeframe = cb.data.split("tf_")[1]
    await state.update_data(timeframe=timeframe)
    data = await state.get_data()
    await cb.message.edit_text(
        f"📋 <b>تایید نهایی تنظیمات</b>\n\n👤 نام: {data.get('name')}\n🪙 ارز: {data.get('symbol')}\n⏱ تایم‌فریم: {timeframe}\n\nاگر همه چیز درست است، دکمه زیر را بزنید:",
        reply_markup=confirm_kb(), parse_mode="HTML"
    )
    await state.set_state(Onboarding.waiting_for_confirmation)

@dp.callback_query(Onboarding.waiting_for_confirmation, F.data == "confirm_start")
async def process_confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('name') or not data.get('symbol'):
        await cb.message.answer("❌ خطا! اطلاعات ناقص است. /start")
        await state.clear()
        return
    await save_user_settings(cb.from_user.id, data['name'], data['symbol'], data['timeframe'])
    await cb.message.delete()
    await cb.message.answer("🎉 تنظیمات شما ذخیره شد و تحلیل زمان‌دار فعال شد! ⚙️", reply_markup=main_menu_kb())
    await state.clear()

# =====================================================================
# 2. هندلرهای منوی اصلی
# =====================================================================

# --- گزینه 1: تحلیل درخواستی ---
@dp.message(F.text == "📊 تحلیل درخواستی")
async def on_demand_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔍 تحلیل درخواستی:\nلطفاً ارز دیجیتال مورد نظر را انتخاب کنید:", reply_markup=symbol_kb())
    await state.set_state(OnDemand.waiting_for_symbol)

@dp.callback_query(OnDemand.waiting_for_symbol, F.data.startswith("sym_"))
async def on_demand_sym(cb: CallbackQuery, state: FSMContext):
    if cb.data == "sym_search":
        await cb.message.edit_text("🔍 نماد ارز را انگلیسی تایپ کنید (مثال: ADAUSDT):")
        return
    symbol = cb.data.split("sym_")[1]
    await state.update_data(symbol=symbol)
    await cb.message.edit_text(f"✅ ارز: {symbol}\n\n⏱ تایم‌فریم تحلیل را انتخاب کنید:", reply_markup=timeframe_kb())
    await state.set_state(OnDemand.waiting_for_timeframe)

@dp.message(OnDemand.waiting_for_symbol)
async def on_demand_sym_search(message: Message, state: FSMContext):
    symbol = message.text.upper()
    await state.update_data(symbol=symbol)
    await message.answer(f"✅ ارز: {symbol}\n\n⏱ تایم‌فریم تحلیل را انتخاب کنید:", reply_markup=timeframe_kb())
    await state.set_state(OnDemand.waiting_for_timeframe)

@dp.callback_query(OnDemand.waiting_for_timeframe, F.data.startswith("tf_"))
async def on_demand_tf(cb: CallbackQuery, state: FSMContext):
    timeframe = cb.data.split("tf_")[1]
    data = await state.get_data()
    symbol = data.get('symbol')
    await cb.message.delete()
    wait_msg = await cb.message.answer(f"⏳ در حال تحلیل درخواستی {symbol} در تایم‌فریم {timeframe}...\nلطفاً صبور باشید.")
    asyncio.create_task(process_and_send_on_demand(cb.from_user.id, symbol, timeframe, wait_msg.message_id))
    await state.clear()

async def process_and_send_on_demand(user_id: int, symbol: str, timeframe: str, wait_msg_id: int):
    try:
        signal_text = await get_signal(symbol, timeframe)
        await bot.send_message(user_id, signal_text, parse_mode="HTML")
        await bot.delete_message(user_id, wait_msg_id)
    except Exception as e:
        logging.error(f"On-demand error: {e}")
        await bot.send_message(user_id, "⚠️ خطا در تحلیل.", parse_mode="HTML")


# --- گزینه 2: سیگنال‌های برتر امروز (منطق جدید درخواستی) ---
@dp.message(F.text == "🔥 سیگنال‌های برتر امروز")
async def show_top_today(message: Message):
    global is_top_coins_processing
    
    # بررسی قفل سراسری
    if is_top_coins_processing:
        await message.answer(
            "⏳ <b>سیستم در حال پردازش است!</b>\n\n"
            "در حال حاضر یک کاربر دیگر درخواست تحلیل ۴ کوین برتر را داده است و سیستم مشغول تحلیل هوش مصنوعی می‌باشد.\n"
            "برای جلوگیری از قطعی سرویس (Rate Limit)، لطفاً ۱۵ دقیقه دیگر تلاش کنید.",
            parse_mode="HTML"
        )
        return

    # فعال کردن قفل
    is_top_coins_processing = True
    
    # پاسخ فوری به کاربر
    await message.answer(
        "✅ <b>درخواست شما ثبت شد.</b>\n\n"
        "🤖 سیستم به زودی شروع به اسکن کل بازار و سپس تحلیل عمیق ۲ لانگ برتر و ۲ شورت برتر در تایم فریم 4 ساعته خواهد کرد.\n"
        "⏳ این پروسه حدود ۱۰ الی ۱۵ دقیقه زمان می‌برد. نتیجه نهایی بلافاصله پس از اتمام برای شما ارسال می‌شود.",
        parse_mode="HTML"
    )
    
    # اجرای پردازش سنگین در پس‌زمینه
    asyncio.create_task(process_top_coins_background(message.from_user.id))

async def process_top_coins_background(user_id: int):
    """این تابع در پس‌زمینه ران می‌شود تا ربات هنگ نکند"""
    global is_top_coins_processing
    try:
        await run_full_top_coins_pipeline(bot, user_id)
    except Exception as e:
        logging.error(f"Background Top Coins Error: {e}")
        await bot.send_message(user_id, "❌ پردازش با خطا مواجه شد.", parse_mode="HTML")
    finally:
        # مهم: هر اتفاقی افتاد، قفل باید باز شود تا کاربران بعدی بتوانند درخواست دهند
        is_top_coins_processing = False


# --- گزینه 3 و 4 (تنظیمات و توقف) ---
@dp.message(F.text == "⚙️ تنظیمات")
async def change_settings(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔄 تنظیمات جدید:\nلطفاً نام خود را وارد کنید:")
    await state.set_state(Onboarding.waiting_for_name)

@dp.message(F.text == "⏸ توقف / فعال‌سازی")
async def toggle_active(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("❌ ابتدا از منوی تنظیمات ثبت‌نام کنید.")
        return
    new_status = not user['is_active']
    await set_user_active(message.from_user.id, new_status)
    status_text = "✅ فعال شدید (تحلیل زمان‌دار ارسال می‌شود)" if new_status else "⏸ متوقف شدید"
    await message.answer(status_text)

# =====================================================================
# 3. زمان‌بند (فقط برای تحلیل زمان‌دار کاربران ثبت نام شده)
# =====================================================================
async def scheduled_signal_job():
    now_utc = datetime.now(timezone.utc)
    grouped_users = await get_active_users_grouped()
    if not grouped_users: return
        
    for (symbol, timeframe), user_ids in grouped_users.items():
        is_candle_closed = False
        tf = timeframe.lower().strip()
        current_minute = now_utc.minute
        current_hour = now_utc.hour
        
        if tf == "1m": is_candle_closed = True
        elif tf == "5m" and current_minute % 5 == 0: is_candle_closed = True
        elif tf == "15m" and current_minute % 15 == 0: is_candle_closed = True
        elif tf == "30m" and current_minute % 30 == 0: is_candle_closed = True
        elif tf in ["1h", "60m"] and current_minute == 0: is_candle_closed = True
        elif tf == "4h" and current_minute == 0 and current_hour % 4 == 0: is_candle_closed = True

        if not is_candle_closed: continue

        logging.info(f"📈 [Scheduler] Candle closed for {symbol} ({timeframe}). Users: {len(user_ids)}")
        signal_text = await get_signal(symbol, timeframe)
        
        for user_id in user_ids:
            try:
                await bot.send_message(user_id, f"🔔 سیگنال زمان‌بندی شده:\n\n{signal_text}", parse_mode='HTML')
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.error(f"Failed to send to {user_id}: {e}")

# =====================================================================
# 4. پنل ادمین
# =====================================================================
@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("فرمت: /broadcast <پیام>")
        return
    users = await get_all_users()
    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 اطلاعیه:\n\n{text}")
            await asyncio.sleep(0.05)
        except Exception: pass
    await message.answer("✅ ارسال انجام شد.")



def restart_bot():
    """پروسه پایتون را کاملاً ری‌استارت می‌کند تا کدهای جدید بارگذاری شوند"""
    logging.info("🔄 Restarting bot with new code changes...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def listen_for_restart_key():
    """گوش دادن به ورودی ترمینال برای ری‌استارت"""
    loop = asyncio.get_event_loop()
    while True:
        # خواندن ورودی از ترمینال به صورت غیربلاک‌کننده
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line.strip().lower() in ['r', 'restart', 'ctrl+r']:
            restart_bot()

# =====================================================================
# 5. اجرای ربات
# =====================================================================
async def main():
    await init_db()
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    scheduler.add_job(scheduled_signal_job, trigger=CronTrigger(minute='*/5', second=5, timezone='UTC'))
    scheduler.start()
    
    # اجرای سرور Health Check در پس‌زمینه همزمان با ربات (برای Render)
    await start_health_server()
    
    # فعال‌سازی گوش‌به‌زنگ ورودی ترمینال در پس‌زمینه
    asyncio.create_task(listen_for_restart_key())
    
    logging.info("🚀 Bot is running... (Press 'r' + Enter in terminal to restart)")
    
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()

def handle_signal(signum, frame):
    logging.info(f"Received signal {signum}, shutting down gracefully...")
    raise SystemExit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("👋 Bot stopped manually.")