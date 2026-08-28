import asyncio
import logging
import json
import os
from datetime import datetime

# ایمپورت کلاس ربات شما
from scripts.LiveTradeSignalBot import LiveSignalBot
from utils.tep import translate_en_to_fa
from scripts.watch_list import run_screener

async def get_signal(symbol: str, timeframe: str) -> str:
    logging.info(f"[Signal Engine] Starting analysis for {symbol} {timeframe}")
    bot_instance = LiveSignalBot(symbol=symbol, timeframe=timeframe)
    loop = asyncio.get_running_loop()
    
    try:
        # خروجی مستقیم از انجین گرفته می‌شود
        last_signal = await loop.run_in_executor(None, bot_instance.run_cycle)
        
        if not last_signal:
            return "⚠️ خطایی در دریافت دیتای بازار رخ داد."
            
        # اگر وضعیت HOLD بود
        if last_signal.get('direction') == 'HOLD':
            reason = translate_en_to_fa(last_signal.get('supervisor_reason', 'دلیلی ثبت نشده است'))
            return (
                f"⏸️ <b>وضعیت معامله: HOLD (بدون اقدام)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>نماد:</b> <code>{symbol}</code>\n"
                f"⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n\n"
                f"🧠 <b>دلیل سوپروایزر:</b>\n<i>{reason}</i>"
            )
        return format_signal_message(last_signal, symbol, timeframe)
        
    except Exception as e:
        logging.error(f"[Signal Engine] Error generating signal: {e}")
        return f"⚠️ خطا در هنگام تولید سیگنال:\n<code>{str(e)}</code>"


# ---------------------------------------------------------------------
# توابع کمکی (مشابه قبل با اصلاحات ریز)
# ---------------------------------------------------------------------
def _resolve_signals_file():
    # با SignalGenerator هماهنگ - Render Disk را ترجیح بده
    if os.path.exists("/app/data/signals_history.json"):
        return "/app/data/signals_history.json"
    if os.path.exists("data/signals_history.json"):
        return "data/signals_history.json"
    if os.path.exists("signals_history.json"):
        return "signals_history.json"
    # پیش‌فرض جدید
    if os.path.exists("/app/data"):
        return "/app/data/signals_history.json"
    return "data/signals_history.json"

async def get_signal_with_score(symbol: str, timeframe: str) -> dict:
    """تحلیل یک کوین و برگرداندن پیام همراه با اسکور اعتماد به نفس"""
    logging.info(f"[Top Engine] Analyzing {symbol} for scoring...")
    bot_instance = LiveSignalBot(symbol=symbol, timeframe=timeframe)
    loop = asyncio.get_running_loop()
    
    try:
        await loop.run_in_executor(None, bot_instance.run_cycle)
        signals_file = _resolve_signals_file()
        
        with open(signals_file, "r", encoding='utf-8') as f:
            signals = json.load(f)
            
        last_signal = signals[-1]
        
        if last_signal.get('symbol', '').upper() != symbol.upper():
            return {"message": f"⏳ سیگنال قطعی برای {symbol} صادر نشد.", "score": 0, "direction": "HOLD"}
        
        score = last_signal.get('supervisor_score', 0)
        direction = last_signal.get('direction', 'N/A')
        message = format_signal_message(last_signal, symbol, timeframe)
        
        return {"message": message, "score": score, "direction": direction}
        
    except Exception as e:
        logging.error(f"Error analyzing {symbol}: {e}")
        return {"message": f"⚠️ خطا در تحلیل {symbol}:\n<code>{str(e)}</code>", "score": 0, "direction": "ERROR"}


def format_signal_message(last_signal: dict, symbol: str, timeframe: str) -> str:
    """فرمت‌سازی پیام سیگنال"""
    direction_raw = last_signal.get('direction', 'N/A').upper()
    if 'BUY' in direction_raw or 'LONG' in direction_raw: dir_emoji = "🟢"
    elif 'SELL' in direction_raw or 'SHORT' in direction_raw: dir_emoji = "🔴"
    else: dir_emoji = "⚡"

    entry_price      = last_signal.get('entry_price', 0.0)
    stop_loss        = last_signal.get('stop_loss', 0.0)
    take_profit      = last_signal.get('take_profit', 0.0)
    rr_ratio         = last_signal.get('rr_ratio', 0.0)
    position_size    = last_signal.get('position_size', 0.0)

    reason           = last_signal.get('supervisor_reason', 'دلیلی ثبت نشده است')
    tech_signal      = last_signal.get('tech_signal' , 'نامشخص')
    sentiment        = last_signal.get('sentiment', 'نامشخص')
    fund_signal      = last_signal.get('fund_signal', 'نامشخص')
    macro_signal     = last_signal.get('macro_signal', 'نامشخص')

    tech_reason      = last_signal.get('tech_reason', ['توضیحی داده نشده'])[0] if isinstance(last_signal.get('tech_reason'), list) else 'توضیحی داده نشده است'
    macro_reason     = last_signal.get('macro_reason', ['توضیحی داده نشده'])[0] if isinstance(last_signal.get('macro_reason'), list) else 'توضیحی داده نشده است'
    sentiment_reason = last_signal.get('sentiment_reason', ['توضیحی داده نشده'])[0] if isinstance(last_signal.get('sentiment_reason'), list) else 'توضیحی داده نشده است'
    fund_reason      = last_signal.get('fund_reason', ['توضیحی داده نشده'])[0] if isinstance(last_signal.get('fund_reason'), list) else 'توضیحی داده نشده است'

    reason           = translate_en_to_fa(reason)
    tech_reason      = translate_en_to_fa(tech_reason)
    macro_reason     = translate_en_to_fa(macro_reason)
    sentiment_reason = translate_en_to_fa(sentiment_reason)
    fund_reason      = translate_en_to_fa(fund_reason)

    return (
        f"{dir_emoji} <b>سیگنال معامله | {direction_raw}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>نماد:</b> <code>{symbol}</code>\n"
        f"⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n\n"
        f"💵 <b>قیمت ورود:</b> <code>{entry_price:.5f}</code>\n"
        f"🎯 <b>حد سود (TP):</b> <code>{take_profit:.5f}</code>\n"
        f"🛑 <b>حد ضرر (SL):</b> <code>{stop_loss:.5f}</code>\n"
        f"⚖️ <b>ریسک به ریوارد:</b> <code>1:{rr_ratio:.2f}</code>\n"
        f"📦 <b>حجم پیشنهادی:</b> <code>{position_size:.4f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>تحلیل ایجنت‌ها:</b>\n\n"
        f"📊 <b>تکنیکال:</b> <code>{tech_signal}</code>\n└ <i>{tech_reason}</i>\n\n"
        f"🎭 <b>سنتیمنت:</b> <code>{sentiment}</code>\n└ <i>{sentiment_reason}</i>\n\n"
        f"🏢 <b>فاندامنتال:</b> <code>{fund_signal}</code>\n└ <i>{fund_reason}</i>\n\n"
        f"🌍 <b>اقتصاد کلان:</b> <code>{macro_signal}</code>\n└ <i>{macro_reason}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 <b>جمع‌بندی:</b>\n<i>{reason}</i>"
    )


# ---------------------------------------------------------------------
# پایپ‌لاین اصلی برترین‌های امروز (On-Demand) - نسخه اصلاح شده
# ---------------------------------------------------------------------
def _resolve_screener_file():
    for p in ["/app/data/screener_latest.json", "data/screener_latest.json"]:
        if os.path.exists(p):
            return p
    return "data/screener_latest.json"

async def run_full_top_coins_pipeline(bot_instance, user_id: int):
    """
    1. اجرای اسکرینر برای پیدا کردن 2 لانگ و 2 شورت برتر
    2. تحلیل 4 کوین با هوش مصنوعی (با تاخیر برای ریت لیمیت)
    3. ذخیره و ارسال نتیجه به صورت پیام‌های مجزا برای جلوگیری از خطای طول پیام
    """
    screener_file = _resolve_screener_file()
    
    try:
        # مرحله اول: اسکن بازار
        await bot_instance.send_message(user_id, "🔍 در حال اسکن بازار برای پیدا کردن ۲ لانگ و ۲ شورت برتر...\nاین مرحله حدود ۱ دقیقه زمان می‌برد.")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, run_screener)
        
        if not os.path.exists(screener_file):
            await bot_instance.send_message(user_id, "❌ خطا در اسکن بازار. فایل اسکرینر ساخته نشد.")
            return

        with open(screener_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # استخراج 2 لانگ برتر و 2 شورت برتر
        top_long_syms = [item['symbol'].split('/')[0] + "USDT" for item in data.get('top_long', [])[:2]]
        top_short_syms = [item['symbol'].split('/')[0] + "USDT" for item in data.get('top_short', [])[:2]]
        
        all_syms_to_analyze = top_long_syms + top_short_syms
        await bot_instance.send_message(user_id, f"✅ اسکن تمام شد.\n🏆 کوین‌های انتخاب شده: {' ، '.join(all_syms_to_analyze)}\n\n🤖 شروع تحلیل عمیق هوش مصنوعی در تایم‌فریم 4 ساعته...\n⏳ لطفاً حدود ۱۰ الی ۱۵ دقیقه صبور باشید.")

        analysis_results = []
        
        # مرحله دوم: تحلیل تک تک کوین‌ها
        for i, sym in enumerate(all_syms_to_analyze, 1):
            await bot_instance.send_message(user_id, f"⏳ [{i}/4] در حال تحلیل {sym} ...")
            
            result = await get_signal_with_score(sym, '4h')
            analysis_results.append({
                "symbol": sym,
                "score": result["score"],
                "message": result["message"]
            })
            
            # تاخیر ۳۰ ثانیه‌ای به جز برای آخرین کوین
            if i < len(all_syms_to_analyze):
                await asyncio.sleep(30)

        # مرحله سوم: مرتب‌سازی بر اساس بالاترین اسکور
        top_4_final = sorted(analysis_results, key=lambda x: x["score"], reverse=True)
        
        # ذخیره در فایل - Render Disk را ترجیح بده
        data_dir = "/app/data" if os.path.exists("/app/data") else "data"
        os.makedirs(data_dir, exist_ok=True)
        today_str = datetime.now().strftime("%Y-%m-%d")
        save_data = {
            "date": today_str,
            "generated_at": datetime.now().isoformat(),
            "top_signals": top_4_final
        }
        with open(f"{data_dir}/daily_top_signals.json", "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        # مرحله چهارم: ارسال پیام هدر
        await bot_instance.send_message(
            user_id, 
            f"🏆 <b>نتایج تحلیل ۴ کوین برتر امروز (تایم فریم 4 ساعته)</b>\n📅 تاریخ: {today_str}\nمرتب‌سازی شده بر اساس بالاترین میزان اعتماد به نفس هوش مصنوعی:\n━━━━━━━━━━━━━━━━━━━━━━", 
            parse_mode="HTML"
        )
        
        # مرحله پنجم: ارسال تحلیل هر کوین در یک پیام مجزا (رفع مشکل طولانی بودن متن)
        for idx, sig in enumerate(top_4_final, 1):
            score = sig.get("score", 0)
            coin_message = f"🔹 <b>رتبه {idx} | اسکور اعتماد: {score:.1f}</b>\n\n{sig.get('message')}"
            
            await bot_instance.send_message(user_id, coin_message, parse_mode="HTML")
            await asyncio.sleep(0.5) # نیم ثانیه مکث بین ارسال پیام‌ها برای جلوگیری از اسپم تلگرام
            
        # پیام پایانی
        await bot_instance.send_message(user_id, "✅ فرآیند تحلیل برترین‌های امروز به پایان رسید.", parse_mode="HTML")

    except Exception as e:
        logging.error(f"[Top Pipeline Error] {e}")
        await bot_instance.send_message(user_id, f"❌ خطایی در سیستم رخ داد:\n<code>{str(e)}</code>", parse_mode="HTML")