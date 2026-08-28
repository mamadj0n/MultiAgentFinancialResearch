# Utils Package

Core utilities for data collection, feature engineering, configuration, and infrastructure.

## Modules

| Module | Description |
|--------|-------------|
| `config.py` | Environment-based configuration (coin, timeframe, thresholds, risk params) |
| `DataCollect.py` | Multi-source data collection (Binance, yfinance, FRED, RSS, blockchain.info) |
| `FeatureEngineer.py` | 45+ technical indicators and feature pipeline |
| `database.py` | Async SQLite user settings for Telegram bot |
| `signal_engine.py` | Signal generation and formatting for Telegram output |
| `keyboards.py` | Telegram bot inline/reply keyboards |
| `log_config.py` | Rotating file + stdout logging setup |
| `retry.py` | Exponential backoff retry decorator |
| `tep.py` | English-to-Persian translation helper |

## Data Sources

- **Price Data**: Binance (live) / yfinance (historical)
- **Macro Data**: FRED API (Fed rate, CPI), yfinance (DXY, VIX, Gold, 10Y yield, Brent oil)
- **News**: RSS feeds (CoinTelegraph, Reuters, Reddit)
- **On-Chain**: Blockchain.info (active addresses, hash rate, transaction fees)

## Feature Pipeline

`FeatureEngineering.process_all()` generates:
- Price features (returns, log returns)
- Trend (EMA 9/20/50/200, VWAP)
- Momentum (RSI, MACD, ROC, ADX)
- Volatility (ATR, Bollinger Bands, historical vol)
- Volume (OBV, CMF, MFI, volume ratio)
- Market Structure (BOS, FVG, liquidity sweeps, swing points)
- Ichimoku Cloud (Tenkan, Kijun, Senkou A/B, Chikou)
- Stochastic Oscillator
- Time/Session features
