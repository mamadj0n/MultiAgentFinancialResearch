"""Scripts package for MultiAgentFinancialResearch.
Provides convenient imports for primary script entry points.
"""

# Export main script classes/functions for easy access
try:
    from .LiveTradeSignalBot import LiveSignalBot
except Exception:
    LiveTradeSignalBot = None

try:
    from .BackTestEngine import ConsensusBacktester
except Exception:
    BackTestEngine = None

from .watch_list import run_screener

__all__ = [
    "LiveSignalBot",
    "ConsensusBacktester",
    "run_screener"
]
