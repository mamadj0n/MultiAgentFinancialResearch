#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Screener Agent v4.7 (Unified Table + Volume Sorting + RS vs BTC + Compact JSON Exporter)
--------------------------------------------------------------------------------------
ویژگی‌های این نسخه:
۱. مرتب‌سازی کلیه آلت‌کوین‌ها بر اساس حجم معاملات ۲۴ ساعته (USDT Volume)
۲. سنجش قدرت نسبی در برابر بیت‌کوین (ALT/BTC RS) از بازار Spot بایننس
۳. نمایش جدول یکپارچه و تکی در ترمینال بر اساس اولویت سیگنال
۴. ذخیره‌سازی خروجی در فایل JSON (حاوی متاداده، Top 20 Long و Top 20 Short - بدون all_symbols)
"""

import os
import json
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime

# ==============================================================================
# تنظیمات پایه و لیست سیاه
# ==============================================================================
TIMEFRAME_PRIMARY = '4h'
TIMEFRAME_DAILY = '1d'
TOP_N_DISPLAY = 15     # تعداد کوین‌های نمایشی در جدول ترمینال
SCAN_LIMIT = 50        # تعداد کوین‌های پرحجم اول برای اسکن عمیق

IGNORED_KEYWORDS = [
    'USDC', 'FDUSD', 'BTCDOM', 'MSTR', 'CRCL', 'UP/', 'DOWN/', 
    'BEAR/', 'BULL/', 'XAU', 'XAG', 'PAXG', 'SOXL', 'MRVL', 'SKHY', 'SNXX', 'NVDA'
]

def create_exchange():
    """اتصال به بازار Futures بایننس"""
    return ccxt.binance({
        'rateLimit': 1200,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

def create_spot_exchange():
    """اتصال مجزا به بازار Spot برای دریافت پیرهای ALT/BTC"""
    return ccxt.binance({
        'rateLimit': 1200,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

# ==============================================================================
# توابع دریافت داده و محاسبات فنی
# ==============================================================================
def fetch_qualified_symbols(exchange):
    """دریافت نمادها، اعمال فیلتر لیست سیاه و مرتب‌سازی نزولی بر اساس حجم ۲۴ ساعته"""
    markets = exchange.load_markets()
    qualified = []
    
    for symbol, market in markets.items():
        if not market.get('swap', False) or not market.get('active', True):
            continue
        if market.get('quote') != 'USDT':
            continue
        
        base = market.get('base', '')
        if any(kw in symbol or kw == base for kw in IGNORED_KEYWORDS):
            continue
            
        qualified.append(symbol)
        
    sorted_symbols = sorted(
        qualified, 
        key=lambda s: float(markets[s]['info'].get('quoteVolume', 0) or 0), 
        reverse=True
    )
    
    return sorted_symbols, markets

def fetch_btc_relative_strength(spot_exchange, symbol, timeframe='4h', limit=30):
    """بررسی قدرت نسبی آلت‌کوین در برابر بیت‌کوین مستقیماً از بازار Spot"""
    base_asset = symbol.split('/')[0].split(':')[0]
    btc_pair = f"{base_asset}/BTC"
    
    try:
        ohlcv = spot_exchange.fetch_ohlcv(btc_pair, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 10:
            return {'has_btc_pair': False, 'rs_24h': 0.0, 'bullish_vs_btc': False}
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        lookback = min(6, len(df) - 1)
        change_24h_btc = ((df['close'].iloc[-1] - df['close'].iloc[-lookback - 1]) / df['close'].iloc[-lookback - 1]) * 100
        
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        is_above_ema20 = df['close'].iloc[-1] > ema20
        
        return {
            'has_btc_pair': True,
            'rs_24h': round(change_24h_btc, 2),
            'bullish_vs_btc': is_above_ema20 and change_24h_btc > 0
        }
    except Exception:
        return {'has_btc_pair': False, 'rs_24h': 0.0, 'bullish_vs_btc': False}

def calculate_metrics(df_4h, df_1d):
    """محاسبه حجم غیرعادی، ATR و وضعیت Squeeze"""
    vol_24h_mean = df_1d['volume'].tail(20).mean()
    vol_24h_current = df_1d['volume'].iloc[-1]
    vol_24h_ratio = vol_24h_current / vol_24h_mean if vol_24h_mean > 0 else 1.0
    
    vol_4h_mean = df_4h['volume'].tail(20).mean()
    vol_4h_current = df_4h['volume'].iloc[-1]
    vol_4h_ratio = vol_4h_current / vol_4h_mean if vol_4h_mean > 0 else 1.0

    high_low = df_4h['high'] - df_4h['low']
    high_close = np.abs(df_4h['high'] - df_4h['close'].shift())
    low_close = np.abs(df_4h['low'] - df_4h['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    atr_current = atr.iloc[-1]
    atr_mean = atr.tail(50).mean()
    atr_ratio = atr_current / atr_mean if atr_mean > 0 else 1.0

    sma20 = df_4h['close'].rolling(20).mean()
    std20 = df_4h['close'].rolling(20).std()
    upper_bb = sma20 + (2 * std20)
    lower_bb = sma20 - (2 * std20)
    bb_width = (upper_bb - lower_bb) / sma20
    
    is_squeeze = bb_width.iloc[-1] < bb_width.tail(50).quantile(0.20)
    change_24h = ((df_1d['close'].iloc[-1] - df_1d['open'].iloc[-1]) / df_1d['open'].iloc[-1]) * 100
    last_price = df_4h['close'].iloc[-1]

    return {
        'vol_24h_ratio': round(vol_24h_ratio, 2),
        'vol_4h_ratio': round(vol_4h_ratio, 2),
        'atr_ratio': round(atr_ratio, 2),
        'squeeze': "YES ⚡" if is_squeeze else "NO",
        'change_24h': round(change_24h, 2),
        'last_price': float(last_price)
    }

def calculate_scores(metrics, btc_rs, btc_regime):
    """محاسبه امتیازهای دوجهته با ضریب قدرت نسبی"""
    v24 = metrics['vol_24h_ratio']
    v4 = metrics['vol_4h_ratio']
    atr = metrics['atr_ratio']
    change = metrics['change_24h']
    sq = 1.2 if metrics['squeeze'] == "YES ⚡" else 1.0

    raw_bull = (v24 * 15) + (v4 * 20) + (atr * 15) + (max(0, change) * 1.5)
    raw_bull *= sq

    raw_bear = (v24 * 15) + (v4 * 15) + (atr * 15) + (abs(min(0, change)) * 2.0)
    raw_bear *= sq

    if btc_rs['has_btc_pair']:
        rs = btc_rs['rs_24h']
        if btc_rs['bullish_vs_btc']:
            raw_bull *= 1.30 if rs > 5.0 else 1.15
        else:
            raw_bull *= 0.80
            
        if rs < -5.0:
            raw_bear *= 1.25

    if btc_regime == 'BULLISH':
        raw_bull *= 1.20
        raw_bear *= 0.65
    elif btc_regime == 'BEARISH':
        raw_bull *= 0.65
        raw_bear *= 1.20

    bull_score = min(99.9, round(raw_bull, 1))
    bear_score = min(99.9, round(raw_bear, 1))

    return bull_score, bear_score

# ==============================================================================
# تابع ذخیره‌سازی داده‌ها در JSON
# ==============================================================================
def save_to_json_db(results, btc_regime, btc_change, total_scanned, output_dir="data"):
    """ذخیره‌سازی ۲۰ برتر Long و ۲۰ برتر Short در فایل JSON (بدون all_symbols)"""
    os.makedirs(output_dir, exist_ok=True)
    
    # تفکیک ۲۰ تای برتر Long و Short
    top_long = sorted(results, key=lambda x: x['bull_score'], reverse=True)[:20]
    
    long_syms = {c['symbol'] for c in top_long}
    filtered_short = [c for c in results if c['symbol'] not in long_syms]
    top_short = sorted(filtered_short, key=lambda x: x['bear_score'], reverse=True)[:20]

    payload = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "btc_regime": btc_regime,
            "btc_24h_change_pct": round(btc_change, 2),
            "total_scanned_symbols": total_scanned,
            "timeframe_primary": TIMEFRAME_PRIMARY,
            "timeframe_daily": TIMEFRAME_DAILY
        },
        "top_long": [
            {
                "rank": idx + 1,
                "symbol": c['symbol'],
                "bull_score": c['bull_score'],
                "bear_score": c['bear_score'],
                "rs_vs_btc_24h_pct": c['rs_raw'],
                "vol_24h_ratio": c['metrics']['vol_24h_ratio'],
                "vol_4h_ratio": c['metrics']['vol_4h_ratio'],
                "atr_ratio": c['metrics']['atr_ratio'],
                "squeeze": c['metrics']['squeeze'] == "YES ⚡",
                "change_24h_pct": c['metrics']['change_24h'],
                "last_price": c['metrics']['last_price'],
                "volume_usd_24h": c['volume_usd']
            }
            for idx, c in enumerate(top_long)
        ],
        "top_short": [
            {
                "rank": idx + 1,
                "symbol": c['symbol'],
                "bull_score": c['bull_score'],
                "bear_score": c['bear_score'],
                "rs_vs_btc_24h_pct": c['rs_raw'],
                "vol_24h_ratio": c['metrics']['vol_24h_ratio'],
                "vol_4h_ratio": c['metrics']['vol_4h_ratio'],
                "atr_ratio": c['metrics']['atr_ratio'],
                "squeeze": c['metrics']['squeeze'] == "YES ⚡",
                "change_24h_pct": c['metrics']['change_24h'],
                "last_price": c['metrics']['last_price'],
                "volume_usd_24h": c['volume_usd']
            }
            for idx, c in enumerate(top_short)
        ]
    }

    # ۱. فایل همیشه به روز برای دسترسی مستقیم ایجنت‌ها
    latest_file = os.path.join(output_dir, "screener_latest.json")
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # ۲. فایل تاریخچه‌دار جهت آرشیو
    history_filename = f"screener_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    history_file = os.path.join(output_dir, history_filename)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n💾 نتایج با موفقیت ذخیره شدند:")
    print(f" └─ فایل زنده: {latest_file}")
    print(f" └─ فایل آرشیو: {history_file}")

# ==============================================================================
# اجرای اصلی اسکرینر
# ==============================================================================
def run_screener():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 اجرای Screener Agent نسخه ۴.۷...")
    
    exchange = create_exchange()
    spot_exchange = create_spot_exchange()
    
    symbols, markets = fetch_qualified_symbols(exchange)
    
    # تحلیل وضعیت بیت‌کوین
    btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT:USDT', timeframe=TIMEFRAME_DAILY, limit=2)
    btc_change = ((btc_ohlcv[-1][4] - btc_ohlcv[-1][1]) / btc_ohlcv[-1][1]) * 100
    btc_regime = 'BULLISH' if btc_change > 0 else 'BEARISH'
    
    print(f"📊 وضعیت بازار (BTC): {btc_regime} ({btc_change:.2f}%)")
    print(f"🎯 تعداد {len(symbols)} آلت‌کوین بر اساس حجم مرتب شدند. اسکن {SCAN_LIMIT} کوین پرحجم اول در حال انجام است...\n")

    results = []

    for sym in symbols[:SCAN_LIMIT]:
        try:
            ohlcv_4h = exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_PRIMARY, limit=60)
            ohlcv_1d = exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_DAILY, limit=30)
            
            if len(ohlcv_4h) < 50 or len(ohlcv_1d) < 20:
                continue

            df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            metrics = calculate_metrics(df_4h, df_1d)
            btc_rs = fetch_btc_relative_strength(spot_exchange, sym, timeframe=TIMEFRAME_PRIMARY)
            
            bull_score, bear_score = calculate_scores(metrics, btc_rs, btc_regime)

            if bull_score >= bear_score and bull_score >= 45.0:
                signal_type = "LONG 🟢"
                priority_score = bull_score
            elif bear_score > bull_score and bear_score >= 35.0:
                signal_type = "SHORT 🔴"
                priority_score = bear_score
            else:
                signal_type = "NEUTRAL ⚪"
                priority_score = max(bull_score, bear_score)

            volume_usd = float(markets[sym]['info'].get('quoteVolume', 0) or 0)

            results.append({
                'symbol': sym,
                'signal': signal_type,
                'bull_score': bull_score,
                'bear_score': bear_score,
                'priority_score': priority_score,
                'rs_raw': btc_rs['rs_24h'] if btc_rs['has_btc_pair'] else 0.0,
                'rs_24h': f"{btc_rs['rs_24h']:+.1f}%" if btc_rs['has_btc_pair'] else "N/A",
                'metrics': metrics,
                'volume_usd': round(volume_usd, 2)
            })
        except Exception:
            continue

    # مرتب‌سازی بر اساس بالاترین امتیاز برای خروجی ترمینال
    sorted_results = sorted(results, key=lambda x: x['priority_score'], reverse=True)[:TOP_N_DISPLAY]

    # چاپ جدول تکی و یکپارچه در ترمینال
    print("📊 **جدول یکپارچه واچ‌لیست بازار (رتبه‌بندی شده بر اساس حجم + اولویت سیگنال):**")
    print("=" * 118)
    print(f"{'رمزارز':<18} | {'پوزیشن':<10} | {'Bull':<6} | {'Bear':<6} | {'RS vs BTC':<10} | {'Vol 24h':<8} | {'Vol 4h':<8} | {'ATR':<7} | {'Squeeze':<8} | {'24h Change'}")
    print("=" * 118)
    for c in sorted_results:
        m = c['metrics']
        print(f"{c['symbol']:<18} | {c['signal']:<10} | {c['bull_score']:<6} | {c['bear_score']:<6} | {c['rs_24h']:<10} | {m['vol_24h_ratio']}x{'':<3} | {m['vol_4h_ratio']}x{'':<3} | {m['atr_ratio']}x{'':<2} | {m['squeeze']:<8} | {m['change_24h']}%")
    print("=" * 118)

    # ذخیره در فایل JSON
    save_to_json_db(results, btc_regime, btc_change, len(symbols))

if __name__ == "__main__":
    run_screener()