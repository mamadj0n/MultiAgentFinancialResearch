# Multi-Agent Financial Research

A multi-agent crypto trading system with structured consensus debate for signal generation.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Telegram Bot (bot.py)               │
├─────────────────────────────────────────────────────┤
│              LiveSignalBot / BackTestEngine          │
├─────────────────────────────────────────────────────┤
│              Consensus Room (3-Round Debate)         │
│  ┌──────────┬──────────┬──────────┬──────────┬─────┐ │
│  │Technical │  Macro   │Sentiment │Fundament.│Risk │ │
│  │  Agent   │  Agent   │  Agent   │  Agent   │Agent│ │
│  └──────────┴──────────┴──────────┴──────────┴─────┘ │
│              LLM Supervisor (Final Decision)         │
├─────────────────────────────────────────────────────┤
│  DataCollect │ FeatureEngineering │ MemoryStore      │
└─────────────────────────────────────────────────────┘
```

## Project Structure

```
MultiAgentFinancialResearch/
├── agents/                 # AI analysis agents
│   ├── consensus/          # Multi-agent debate framework
│   ├── technical_agent.py  # Trend-following with SMC/ICT
│   ├── macro_agent.py      # Macroeconomic analysis
│   ├── sentiment_agent.py  # News sentiment
│   ├── fundamental_agent.py # On-chain metrics
│   ├── risk_agent.py       # Risk management
│   ├── memory_agent.py     # Historical pattern matching
│   └── llm_supervisor_agent.py # Final decision synthesis
├── utils/                  # Core utilities
│   ├── DataCollect.py      # Multi-source data collection
│   ├── FeatureEngineer.py  # 45+ technical indicators
│   ├── config.py           # Environment configuration
│   └── ...
├── scripts/                # Entry points
│   ├── bot.py              # Telegram bot
│   ├── LiveTradeSignalBot.py # Live signal engine
│   ├── BackTestEngine.py   # Historical backtesting
│   └── watch_list.py       # Market screener
├── memory_store.py         # Trade history SQLite
└── Dockerfile              # Container deployment
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_TOKEN="your-bot-token"
export FRED_TOKEN="your-fred-api-key"
export API_KEY="your-llm-api-key"

# Run the bot
python scripts/bot.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COIN` | `ETH-USD` | Default trading pair |
| `TIME_FRAME` | `1m` | Default timeframe |
| `LLM_MODEL_NAME` | `qwen2.5:3b` | Local LLM model |
| `PROVIDER` | `online` | LLM provider (local/online) |
| `TELEGRAM_TOKEN` | - | Telegram bot token |
| `FRED_TOKEN` | - | FRED API key |
| `API_KEY` | - | Online LLM API key |
| `ADMIN_ID` | `0` | Telegram admin user ID |

## Consensus Debate

The system uses a 3-round structured debate:

1. **Round 0**: Each agent analyzes independently
2. **Round 1**: Agents critique each other's opinions
3. **Round 2**: Agents revise based on peer feedback
4. **Supervisor**: LLM synthesizes final decision

## Docker

```bash
docker build -t multi-agent-trading .
docker run -e TELEGRAM_TOKEN=... multi-agent-trading
```
