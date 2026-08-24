import pandas as pd
import numpy as np
import pandas_ta as ta  # Technical Analysis library


class FeatureEngineering:
    """
    Comprehensive Feature Engineering Module for Quantitative Trading Systems.
    Processes price, macro, technical indicators, Smart Money Concepts (SMC),
    and temporal features.
    """

    def __init__(
        self, price_df: pd.DataFrame, macro_df: pd.DataFrame = None, news_score: float = 0.0
    ) -> None:
        """
        :param price_df: DataFrame with OHLCV data and UTC DatetimeIndex.
        :param macro_df: DataFrame containing Macro indicators from DataCollector.
        :param news_score: Sentiment score output from News/LLM agent (-1.0 to 1.0).
        """
        self.df = price_df.copy()
        self.macro_df = macro_df.copy() if macro_df is not None else None
        self.news_score = news_score

        # Flatten MultiIndex columns if present
        if isinstance(self.df.columns, pd.MultiIndex):
            self.df.columns = self.df.columns.get_level_values(0)

    # 1. Price Features
    def add_price_features(self) -> None:
        self.df["Returns"] = self.df["Close"].pct_change()
        self.df["Log_Returns"] = np.log(self.df["Close"] / self.df["Close"].shift(1))

    # 2. Trend Features
    def add_trend_features(self) -> None:
        self.df["EMA_20"] = ta.ema(self.df["Close"], length=20)
        self.df["EMA_50"] = ta.ema(self.df["Close"], length=50)
        self.df["EMA_200"] = ta.ema(self.df["Close"], length=200)
        self.df["EMA_9"] = ta.ema(self.df["Close"], length=9)     
        self.df["VWAP"] = ta.vwap(self.df["High"], self.df["Low"], self.df["Close"], self.df["Volume"])

    # 3. Momentum Features
    def add_momentum_features(self) -> None:
        self.df["RSI_14"] = ta.rsi(self.df["Close"], length=14)

        macd = ta.macd(self.df["Close"], fast=12, slow=26, signal=9)
        if macd is not None:
            self.df["MACD"] = macd["MACD_12_26_9"]
            self.df["MACD_Signal"] = macd["MACDs_12_26_9"]
            self.df["MACD_Hist"] = macd["MACDh_12_26_9"]

        self.df["ROC_10"] = ta.roc(self.df["Close"], length=10)

        adx_df = ta.adx(self.df["High"], self.df["Low"], self.df["Close"], length=14)
        self.df["ADX_14"] = adx_df.iloc[:, 0]       

    # 4. Volatility Features
    def add_volatility_features(self) -> None:
        """Calculates ATR, Historical Volatility, and Bollinger Bands."""
        self.df["ATR_14"] = ta.atr(self.df["High"], self.df["Low"], self.df["Close"], length=14)
        self.df["Hist_Vol_20"] = self.df["Log_Returns"].rolling(window=20).std() * np.sqrt(365)

        bb = ta.bbands(self.df["Close"], length=20, std=2.0)
        if bb is not None and not bb.empty:
            # ستون 0: Lower Band، ستون 1: Middle Band، ستون 2: Upper Band
            self.df["BB_Lower"] = bb.iloc[:, 0]
            self.df["BB_Middle"] = bb.iloc[:, 1]
            self.df["BB_Upper"] = bb.iloc[:, 2]

            self.df["BB_Width"] = (self.df["BB_Upper"] - self.df["BB_Lower"]) / self.df["BB_Middle"]

            self.df["BB_Position"] = (self.df["Close"] - self.df["BB_Lower"]) / (self.df["BB_Upper"] - self.df["BB_Lower"])
            self.df["volatility_20"] = self.df["Log_Returns"].rolling(window=20).std()
                
    # 5. Volume Features
    def add_volume_features(self) -> None:
        self.df["OBV"] = ta.obv(self.df["Close"], self.df["Volume"])
        self.df["CMF"] = ta.cmf(self.df["High"], self.df["Low"], self.df["Close"], self.df["Volume"], length=20)
        self.df["MFI"] = ta.mfi(self.df["High"], self.df["Low"], self.df["Close"], self.df["Volume"], length=14)

        # 🛠️ ایمن‌سازی محاسبه SMA برای جلوگیری از ارور NoneType
        vol_sma = ta.sma(self.df["Volume"], length=20)
        if vol_sma is not None:
            # جایگزینی صفرها با NaN برای جلوگیری از خطای تقسیم بر صفر
            vol_sma = vol_sma.replace(0, np.nan)
            self.df["Volume_Ratio"] = self.df["Volume"] / vol_sma
        else:
            # اگر محاسبه SMA ناموفق بود، مقدار پیش‌فرض 1.0 قرار بده
            self.df["Volume_Ratio"] = 1.0
            
        # پر کردن مقادیر NaN ایجاد شده
        self.df["Volume_Ratio"] = self.df["Volume_Ratio"].fillna(1.0)

    # 6. Market Structure & Liquidity (SMC / ICT)
    def add_market_structure_and_liquidity(self, swing_window: int = 5) -> None:
        highs = self.df["High"]
        lows = self.df["Low"]
        closes = self.df["Close"]

        # Swing High & Swing Low
        self.df["Swing_High"] = highs[(highs == highs.rolling(swing_window * 2 + 1, center=True).max())]
        self.df["Swing_Low"] = lows[(lows == lows.rolling(swing_window * 2 + 1, center=True).min())]

        last_swing_high = self.df["Swing_High"].ffill()
        last_swing_low = self.df["Swing_Low"].ffill()

        # Trend Direction based on Swings
        self.df["Trend_Direction"] = np.where(
            closes > last_swing_high, 1, np.where(closes < last_swing_low, -1, 0)
        )

        # Break of Structure (BOS) & Change of Character (CHOCH)
        self.df["BOS"] = np.where(
            (closes > last_swing_high) & (closes.shift(1) <= last_swing_high),
            1,
            np.where((closes < last_swing_low) & (closes.shift(1) >= last_swing_low), -1, 0),
        )

        # Fair Value Gap (FVG)
        bullish_fvg = (lows > highs.shift(2))
        bearish_fvg = (highs < lows.shift(2))
        self.df["FVG_Signal"] = 0
        self.df.loc[bullish_fvg, "FVG_Signal"] = 1
        self.df.loc[bearish_fvg, "FVG_Signal"] = -1

        # Liquidity Sweep
        self.df["Liquidity_Sweep"] = 0
        self.df.loc[(highs > last_swing_high) & (closes < last_swing_high), "Liquidity_Sweep"] = 1  # Bearish Sweep
        self.df.loc[(lows < last_swing_low) & (closes > last_swing_low), "Liquidity_Sweep"] = -1  # Bullish Sweep

    # 7. Time & Session Features
    def add_time_features(self) -> None:
        if not isinstance(self.df.index, pd.DatetimeIndex):
            self.df.index = pd.to_datetime(self.df.index)

        self.df["Hour"] = self.df.index.hour
        self.df["Day_Of_Week"] = self.df.index.dayofweek

        def assign_session(hour):
            if 0 <= hour < 8:
                return "Tokyo"
            elif 8 <= hour < 14:
                return "London"
            elif 14 <= hour < 22:
                return "NewYork"
            else:
                return "Other"

        self.df["Session"] = self.df["Hour"].apply(assign_session)

    # 8. Macro & Sentiment Integration
    def add_macro_and_sentiment(self) -> None:
        if self.macro_df is not None and not self.macro_df.empty:
            # 🛠️ حذف ستون‌های تکراری قبل از join
            cols_to_add = [c for c in self.macro_df.columns if c not in self.df.columns]
            if cols_to_add:
                self.df = self.df.join(self.macro_df[cols_to_add], how="left").ffill()

        self.df["News_Score"] = self.news_score

    # 9. Ichimoku Cloud
    def add_ichimoku_cloud(self) -> None:
        """Calculates Ichimoku Cloud components:
        Tenkan-sen, Kijun-sen, Senkou Span A & B, and Chikou Span.
        """
        high = self.df["High"]
        low = self.df["Low"]
        close = self.df["Close"]

        # Tenkan-sen (Conversion Line)
        self.df["Tenkan_sen"] = (high.rolling(window=9).max() + low.rolling(window=9).min()) / 2

        # Kijun-sen (Base Line)
        self.df["Kijun_sen"] = (high.rolling(window=26).max() + low.rolling(window=26).min()) / 2

        # Senkou Span A (Leading Span A)
        self.df["Senkou_Span_A"] = ((self.df["Tenkan_sen"] + self.df["Kijun_sen"]) / 2).shift(26)

        # Senkou Span B (Leading Span B)
        self.df["Senkou_Span_B"] = (
            (high.rolling(window=52).max() + low.rolling(window=52).min()) / 2
        ).shift(26)

        # Chikou Span (Lagging Span)
        self.df["Chikou_Span"] = close.shift(-26)

    # 10. Stochastic Oscillator
    def add_stochastic_oscillator(self, k_period: int = 14, d_period: int = 3) -> None:
        """Calculates the Stochastic Oscillator (%K and %D).

        :param k_period: Look-back period for %K calculation.
        :param d_period: Smoothing period for %D calculation.
        """
        low_min = self.df["Low"].rolling(window=k_period).min()
        high_max = self.df["High"].rolling(window=k_period).max()

        # Avoid division by zero when High == Low
        denom = high_max - low_min
        denom = denom.replace(0, float("nan"))

        self.df["%K"] = 100 * ((self.df["Close"] - low_min) / denom)
        self.df["%D"] = self.df["%K"].rolling(window=d_period).mean()

    # Pipeline Executor
    def process_all(self) -> pd.DataFrame:
        self.add_price_features()
        self.add_trend_features()
        self.add_momentum_features()
        self.add_volatility_features()
        self.add_volume_features()
        self.add_market_structure_and_liquidity()
        self.add_time_features()
        self.add_macro_and_sentiment()
        self.add_ichimoku_cloud()
        self.add_stochastic_oscillator()
        return self.df