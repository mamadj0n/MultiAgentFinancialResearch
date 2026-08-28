# Consensus Room

Multi-agent debate framework for building trading consensus through structured discussion.

## Debate Flow

```
Round 0: Independent Analysis  →  Each agent analyzes market data alone
Round 1: Critique Exchange     →  Agents challenge each other's opinions
Round 2: Opinion Revision      →  Agents may change stance based on critiques
Round 3: Supervisor Decision   →  LLM synthesizes final decision
```

## Components

| Module | Description |
|--------|-------------|
| `consensus_room.py` | Main orchestrator (`ConsensusRoom`) - runs the full debate flow |
| `round_coordinator.py` | Manages each round's execution and message passing |
| `conflict_detector.py` | Detects and classifies disagreements between agents |
| `discussion_context.py` | Builds per-agent context for each round (information asymmetry) |
| `discussion_history.py` | Persists debate history to JSON files |

## Conflict Detection

The `ConflictDetector` identifies conflicts based on:
- **Signal disagreement** (BUY vs SELL)
- **Score difference** (confidence-weighted)
- **Reasoning similarity** (text overlap)
- **Evidence contradiction** (opposing keywords)

Severity levels: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`

## Configuration

```python
ConsensusConfig(
    max_rounds=3,
    enable_round_1=True,  # Critique exchange
    enable_round_2=True,  # Opinion revision
    consensus_threshold=0.6,
    save_history=True,
)
```

## Message Types

- `CLAIM` - Initial independent analysis
- `CRITIQUE` - Disagreement with evidence
- `DEFENSE` - Rebuttal to critique
- `QUESTION` - Clarification request
- `CONCESSION` - Agreement with counter-argument
- `SUPPORT` - Agreement with reasoning
- `CORRECTION` - Factual correction
- `FINAL_STATEMENT` - Revised opinion
