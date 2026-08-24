#!/usr/bin/env python3
"""Consensus Room Module - Multi-Agent Discussion Framework"""

from .consensus_room import ConsensusRoom, ConsensusConfig
from .discussion_history import DiscussionHistoryStore
from .conflict_detector import ConflictDetector
from .round_coordinator import RoundCoordinator, RoundResult
from .discussion_context import DiscussionContextBuilder

__all__ = [
    "ConsensusRoom",
    "ConsensusConfig", 
    "DiscussionHistoryStore",
    "ConflictDetector",
    "RoundCoordinator",
    "RoundResult",
    "DiscussionContextBuilder",
]