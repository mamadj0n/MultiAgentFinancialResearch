#!/usr/bin/env python3


from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union
import logging
import yfinance as yf
import ccxt
from fredapi import Fred
import feedparser
import trafilatura
import pandas as pd
import requests

from utils.config import FRED_API_KEY
from utils.retry import retry_on_exception

logger = logging.getLogger(__name__)

pd.set_option('future.no_silent_downcasting', True)

class DataCollector:
    """
    A robust class to collect cryptocurrency price data, macroeconomic indicators,
    news from various RSS feeds, and on-chain blockchain data. All time indices are in UTC.
    """

    def __init__(
        self,
        coin: str = "ETH-USD",
        live_data: bool = True,
        time_frame: str = "5m",
        start_time: str = "2020-01-01",
        finish_time: str = "2025-01-01",
        fred_api_key: Optional[str] = None,
    ) -> None:
        self.coin = coin
        self.live_data = live_data
        self.time_frame = time_frame
        self.start_time = start_time
        self.finish_time = finish_time
        self.fred_api_key = fred_api_key or FRED_API_KEY
        # منطقه زمانی UTC برای تمام عملیات‌ها
        self.utc_tz = timezone.utc

    # ---------- بخش ۱: جمع‌آوری داده‌های قیمت ارز دیجیتال ----------
    def _collect_price_data(self) -> pd.DataFrame:
        """Fetch price data. Uses Binance/KuCoin API (ccxt) for live, yfinance for historical."""
        
        # ۱. نرمال‌سازی نمادها برای صرافی‌ها و یاهو فایننس
        # تبدیل فرمت‌های مختلف به نماد CCXT (مثلاً ETH/USDT)
        clean_coin = self.coin.upper().replace("-", "").replace("/", "")
        if "USDT" in clean_coin:
            base_symbol = clean_coin.replace("USDT", "")
        elif "USD" in clean_coin:
            base_symbol = clean_coin.replace("USD", "")
        else:
            base_symbol = clean_coin

        symbol_ccxt = f"{base_symbol}/USDT"
        symbol_yf = f"{base_symbol}-USD"

        if self.live_data:
            # روش اصلی: تلاش برای دریافت از Binance با دامنه بدون تحریم
            try:
                logger.info(f"[DataCollector] Fetching LIVE data from Binance via ccxt: {symbol_ccxt} {self.time_frame}")
                
                exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'}
                })
                # تغییر endpoint عمومی بایننس برای دور زدن تحریم IP دیتاسنترهای Render
                exchange.urls['api']['public'] = 'https://data-api.binance.vision/api'
                
                limit = 1000
                ohlcv = exchange.fetch_ohlcv(symbol_ccxt, self.time_frame, limit=limit)
                
                price = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                price['Timestamp'] = pd.to_datetime(price['Timestamp'], unit='ms')
                price.set_index('Timestamp', inplace=True)

                if price.index.tz is None:
                    price.index = price.index.tz_localize(self.utc_tz)
                else:
                    price.index = price.index.tz_convert(self.utc_tz)
                    
                return price

            except Exception as e:
                logger.error(f"[DataCollector] Error fetching Binance data via ccxt: {e}")
                logger.warning("[DataCollector] Falling back to KuCoin via ccxt...")

            # روش دوم (Fallback 1): تلاش برای دریافت از KuCoin در صورت خطای بایننس
            try:
                exchange_kc = ccxt.kucoin({'enableRateLimit': True})
                limit = 1000
                ohlcv = exchange_kc.fetch_ohlcv(symbol_ccxt, self.time_frame, limit=limit)
                
                price = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                price['Timestamp'] = pd.to_datetime(price['Timestamp'], unit='ms')
                price.set_index('Timestamp', inplace=True)

                if price.index.tz is None:
                    price.index = price.index.tz_localize(self.utc_tz)
                else:
                    price.index = price.index.tz_convert(self.utc_tz)
                    
                return price

            except Exception as e_kc:
                logger.error(f"[DataCollector] KuCoin fallback also failed: {e_kc}")
                logger.warning(f"[DataCollector] Falling back to yfinance with symbol: {symbol_yf}...")
                
                # روش سوم (Fallback 2): استفاده از yfinance با نماد اصلاح‌شده (ETH-USD)
                price = yf.download(symbol_yf, period="5d", interval=self.time_frame, auto_adjust=False)

        else:
            # برای بک‌تست تاریخی
            price = yf.download(
                symbol_yf,
                start=self.start_time,
                end=self.finish_time,
                interval=self.time_frame,
                auto_adjust=False,
            )

        # پردازش ستون‌های یاهو فایننس (در صورت استفاده از yfinance)
        if isinstance(price.columns, pd.MultiIndex):
            price.columns = price.columns.get_level_values(0)

        if price.index.tz is None:
            price.index = price.index.tz_localize(self.utc_tz)
        else:
            price.index = price.index.tz_convert(self.utc_tz)

        return price

    # ---------- بخش ۲: جمع‌آوری داده‌های اقتصاد کلان (ماکرو) ----------
    def _collect_macro_data(self) -> pd.DataFrame:
        """
        Fetch macro data including:
          - DXY Index (DX-Y.NYB)
          - Brent Oil (BZ=F)
          - VIX (^VIX)
          - US 10Y Treasury Yield (^TNX)
          - Gold Futures (GC=F)
          - FRED series: Fed Funds Rate, CPI, Inflation YoY
        Returns a DataFrame with UTC index.
        """
        fred = Fred(api_key=self.fred_api_key)

        # بازه زمانی: برای live داده‌های اخیر، از ۳۶۵ روز قبل شروع می‌کنیم
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d") if self.live_data else self.start_time
        start_date = pd.to_datetime(start_date) - pd.DateOffset(months=14)

        # دریافت سری‌های FRED
        try:
            interest_rate = fred.get_series("FEDFUNDS", observation_start=start_date)
            cpi = fred.get_series("CPIAUCSL", observation_start=start_date)
        except Exception as e:
            logger.error(f"Error fetching FRED data: {e}")
            return pd.DataFrame()

        inflation_yoy = cpi.pct_change(12, fill_method=None) * 100

        macro_fred = pd.DataFrame(
            {
                "US_Interest_Rate": interest_rate,
                "US_CPI": cpi,
                "US_Inflation_YoY": inflation_yoy,
            }
        )

        # لیست تیکرهای yfinance برای بخش ماکرو (شامل تیکرهای جدید)
        tickers = ["DX-Y.NYB", "BZ=F", "^VIX", "^TNX", "GC=F"]

        try:
            yf_data = yf.download(tickers, start=start_date, auto_adjust=False)["Close"]
            if isinstance(yf_data.columns, pd.MultiIndex):
                yf_data.columns = yf_data.columns.get_level_values(0)

            # تغییر نام ستون‌ها به نام‌های خوانا
            yf_data = yf_data.rename(columns={
                "DX-Y.NYB": "DXY_Index",
                "BZ=F": "Brent_Oil",
                "^VIX": "VIX",
                "^TNX": "US10Y_Yield",
                "GC=F": "Gold",
            })
        except Exception as e:
            logger.error(f"Error fetching yfinance macro data: {e}")
            yf_data = pd.DataFrame()

        # ترکیب داده‌ها و پر کردن مقادیر گمشده
        macro_data = yf_data.join(macro_fred, how="outer")
        macro_data = macro_data.ffill()
        
        # اطمینان از timezone UTC
        if macro_data.index.tz is None:
            macro_data.index = macro_data.index.tz_localize(self.utc_tz)
        else:
            macro_data.index = macro_data.index.tz_convert(self.utc_tz)

        # اگر live_data=True، فقط ۳۰ روز آخر را نگه می‌داریم
        if self.live_data:
            macro_data = macro_data.tail(30)

        return macro_data

    # ---------- بخش ۳: جمع‌آوری اخبار از RSS ----------
    def _collect_news_data(self) -> pd.DataFrame:
        """Fetch news articles from RSS feeds."""
        RSS_FEEDS = {
            "CoinTelegraph": "https://cointelegraph.com/rss",
            "Reuters_Business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
            "reddit": "https://www.reddit.com/r/CryptoCurrency/hot.rss",
        }

        def fetch_full_article(url: str) -> str:
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
                    return text if text else ""
            except Exception:
                pass
            return ""

        news_list = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url, request_headers=headers)
                entries = feed.entries[:5] if source == "reddit" else feed.entries

                for entry in entries:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    published = entry.get("published", entry.get("updated", ""))
                    full_text = entry.get("summary", "") if source == "reddit" else fetch_full_article(link)

                    news_list.append({
                        "source": source,
                        "title": title,
                        "published_at": published,
                        "full_text": full_text,
                        "link": link,
                    })
            except Exception as e:
                logger.error(f"Error fetching {source}: {e}")

        return pd.DataFrame(news_list)

    # ---------- بخش ۴: جمع‌آوری داده‌های آن‌چین (On-Chain) ----------
    def _collect_onchain_data(self) -> pd.DataFrame:
        """
        Fetch on-chain metrics (Active Addresses, Hash Rate, Transaction Fees)
        from Blockchain.info API. Returns a DataFrame with a UTC DatetimeIndex.
        """
        timespan = '30days' if self.live_data else 'all'
        
        def fetch_chart(chart_name: str) -> list:
            url = f"https://api.blockchain.info/charts/{chart_name}"
            params = {'timespan': timespan, 'format': 'json', 'cors': 'true'}
            try:
                response = requests.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    return response.json().get('values', [])
            except Exception as e:
                logger.error(f"Error fetching on-chain chart {chart_name}: {e}")
            return []

        # دریافت داده‌های خام
        active_addresses_raw = fetch_chart('n-unique-addresses')
        hash_rate_raw = fetch_chart('hash-rate')
        fees_usd_raw = fetch_chart('transaction-fees-usd')

        # پردازش و تبدیل داده‌ها به دیکشنری
        def to_dict(raw_data):
            processed = {}
            for item in raw_data:
                # ایجاد یک Timestamp به ثانیه
                dt_obj = datetime.fromtimestamp(item['x'], tz=timezone.utc)
                processed[dt_obj] = item['y']
            return processed

        dict_addresses = to_dict(active_addresses_raw)
        dict_hash_rate = to_dict(hash_rate_raw)
        dict_fees = to_dict(fees_usd_raw)

        # ادغام کلیدها و مرتب‌سازی بر اساس تاریخ متوجه منطقه زمانی (Timezone-Aware)
        all_dates = sorted(list(set(dict_addresses.keys()) | set(dict_hash_rate.keys()) | set(dict_fees.keys())))

        combined = []
        for dt in all_dates:
            combined.append({
                'Date': dt,
                'Active_Addresses': dict_addresses.get(dt, None),
                'Hash_Rate_TH/s': dict_hash_rate.get(dt, None),
                'Total_Fees_USD': dict_fees.get(dt, None)
            })

        if not combined:
            return pd.DataFrame()

        onchain_df = pd.DataFrame(combined)
        onchain_df.set_index('Date', inplace=True)

        # اعمال فیلتر زمانی در حالت غیر زنده (Historical Mode)
        if not self.live_data:
            start_dt = pd.to_datetime(self.start_time).tz_localize(self.utc_tz)
            finish_dt = pd.to_datetime(self.finish_time).tz_localize(self.utc_tz)
            onchain_df = onchain_df.loc[start_dt:finish_dt]

        return onchain_df

    # ---------- بخش ۵: متدهای اصلی جمع‌آوری ----------
    @retry_on_exception(max_retries=2, delay=3.0, backoff=2.0, exceptions=(Exception,))
    def collect_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Collect all data: price, macro, news, and on-chain metrics.
        :return: Tuple of (price_df, macro_df, news_df, onchain_df)
        """
        price_df = self._collect_price_data()
        macro_df = self._collect_macro_data()
        news_df = self._collect_news_data()
        onchain_df = self._collect_onchain_data()
        return price_df, macro_df, news_df, onchain_df

    # ---------- بخش ۶: توابع کمکی برای زمان و سشن ----------
    @staticmethod
    def get_utc_timezone() -> timezone:
        """Return UTC timezone object."""
        return timezone.utc

    def get_session(self, dt: Union[datetime, pd.Timestamp]) -> str:
        """
        Determine the trading session based on UTC hour.
        Sessions:
          - Tokyo   : 00:00 - 07:59 UTC
          - London  : 08:00 - 13:59 UTC (overlaps with NY)
          - NewYork : 14:00 - 21:59 UTC
          - Other   : 22:00 - 23:59 UTC
        """
        if isinstance(dt, pd.Timestamp):
            dt = dt.to_pydatetime()
        # اطمینان از timezone-aware بودن
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.utc_tz)
        else:
            dt = dt.astimezone(self.utc_tz)

        hour = dt.hour

        if 0 <= hour < 8:
            return "Tokyo"
        elif 8 <= hour < 14:
            return "London"
        elif 14 <= hour < 22:
            return "NewYork"
        else:
            return "Other"

    def add_session_and_hour(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add two columns to a DataFrame with UTC index:
          - 'Hour'   : hour of the day (0-23) in UTC
          - 'Session': one of ['Tokyo','London','NewYork','Other']
        """
        if df.empty or df.index is None:
            return df

        # اطمینان از timezone
        if df.index.tz is None:
            df.index = df.index.tz_localize(self.utc_tz)
        else:
            df.index = df.index.tz_convert(self.utc_tz)

        df = df.copy()
        df['Hour'] = df.index.hour
        df['Session'] = df.index.map(self.get_session)
        return df
