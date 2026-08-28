# Scripts Package

Main entry points and engines for the trading system.

## Scripts

| Script | Description |
|--------|-------------|
| `bot.py` | Telegram bot with onboarding, on-demand analysis, top coins, and scheduled signals |
| `LiveTradeSignalBot.py` | Live signal generation engine using consensus room |
| `BackTestEngine.py` | Historical backtesting with portfolio management |
| `watch_list.py` | Market screener for top long/short altcoins |

## Usage

```bash
# Run Telegram bot
python scripts/bot.py

# Run live signal bot standalone
python scripts/LiveTradeSignalBot.py

# Run backtester
python scripts/BackTestEngine.py

# Run market screener
python scripts/watch_list.py
```

## LiveSignalBot

Orchestrates the full analysis pipeline:
1. Fetch live data from Binance
2. Engineer 45+ features
3. Run consensus room debate (3 rounds)
4. Get LLM supervisor decision
5. Generate signal with entry/SL/TP

## ConsensusBacktester

Historical backtesting with:
- `PortfolioManager` - Position sizing, PnL tracking
- `ConsensusLogger` - Colorized terminal output
- Equity curve generation and performance report

## Watch List Screener

Scans top 50 high-volume altcoins on Binance Futures:
- Volume ratio analysis
- BTC relative strength (ALT/BTC pairs)
- Bollinger Band squeeze detection
- Bull/Bear scoring with BTC regime adjustment
