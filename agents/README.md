# Agents Package

AI-powered analysis agents for the multi-agent financial trading system.

## Architecture

All agents inherit from `BaseAgent` or `DiscussingAgent` (for consensus room participation) and implement:
- `validate()` - Check input data sufficiency
- `analyze()` - Produce standardized `AgentOutput`
- `analyze_independent()` - Round 0 independent analysis
- `critique_others()` - Round 1 peer critique
- `revise_opinion()` - Round 2 opinion revision

## Agents

| Agent | Domain | LLM | Description |
|-------|--------|-----|-------------|
| `TechnicalAgent` | Technical | Yes | Trend-following analysis with SMC/ICT, EMA200, Ichimoku Cloud. Hard guardrail blocks counter-trend signals. |
| `MacroAgent` | Macro | Yes | Macroeconomic analysis (interest rates, DXY, VIX, gold, CPI). |
| `SentimentAgent` | Sentiment | Yes | News and social sentiment from RSS feeds (CoinTelegraph, Reuters, Reddit). |
| `FundamentalAgent` | Fundamental | Yes | On-chain metrics and 30-day momentum analysis. |
| `RiskAgent` | Risk | No | Volatility, drawdown, and position sizing. Always NEUTRAL signal. |
| `MemoryAgent` | Memory | Yes | Historical trade pattern matching for confidence adjustment. |
| `LLMSupervisorAgent` | Supervisor | Yes | Final decision synthesis from all agent outputs. |

## Agent Registration

Agents are auto-registered via `AgentCapability` in `__init__.py` for domain-based discovery.

## Key Files

- `agent_architecture_core.py` - Core data structures (`AgentOutput`, `MarketContext`, `SharedLLMEngine`, debate protocols)
- `technical_agent.py` - Technical analysis with trend-lock guardrails
- `macro_agent.py` - Macroeconomic indicator analysis
- `sentiment_agent.py` - News sentiment analysis
- `fundamental_agent.py` - On-chain and fundamental metrics
- `risk_agent.py` - Risk management and position sizing
- `memory_agent.py` - Historical trade pattern matching
- `llm_supervisor_agent.py` - LLM-based final decision synthesis
