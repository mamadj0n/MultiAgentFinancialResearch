#!/usr/bin/env python3
"""Consensus Room - Main orchestration for multi-agent debate"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ..agent_architecture_core import (
    MarketContext, AgentOutput, SignalType, DiscussionHistory, 
    DebateMessage, AgentOpinion, RoundType, DiscussingAgent
)
from .round_coordinator import RoundCoordinator, RoundResult
from .conflict_detector import ConflictDetector
from .discussion_history import DiscussionHistoryStore
from typing import Dict, List, Optional, Any


class ConsensusConfig:
    """Configuration for Consensus Room behavior."""
    def __init__(
        self,
        max_rounds: int = 3,
        enable_round_0: bool = True,
        enable_round_1: bool = True,
        enable_round_2: bool = True,
        consensus_threshold: float = 0.6,
        save_history: bool = True,
        history_path: str = "./data/consensus_history",
    ):
        self.max_rounds = max_rounds
        self.enable_round_0 = enable_round_0
        self.enable_round_1 = enable_round_1
        self.enable_round_2 = enable_round_2
        self.consensus_threshold = consensus_threshold
        self.save_history = save_history
        self.history_path = history_path


class ConsensusRoom:
    """
    Main orchestrator for multi-agent consensus building.
    
    Flow:
    1. Round 0: Independent analysis (no peer visibility)
    2. Round 1: Critique exchange (agents challenge each other)
    3. Round 2: Opinion revision (agents may change stance)
    4. Supervisor decision (final aggregation)
    """
    
    def __init__(
        self, 
        agents: Dict[str, 'DiscussingAgent'],
        supervisor: 'SupervisorAgent',
        config: Optional[ConsensusConfig] = None
    ):
        self.agents = agents
        self.supervisor = supervisor
        self.config = config or ConsensusConfig()
        
        self.conflict_detector = ConflictDetector()
        self.round_coordinator = RoundCoordinator(agents, self.conflict_detector)
        self.history_store = DiscussionHistoryStore(self.config.history_path) if self.config.save_history else None
    
    def run_consensus(self, market_context: MarketContext) -> AgentOutput:
        """Execute full consensus process and return final decision."""
        session_id = f"consensus_{market_context.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        history = DiscussionHistory(
            session_id=session_id,
            symbol=market_context.symbol,
            start_time=datetime.now(),
        )
        
        # ===== ROUND 0: Independent Analysis =====
        round_0_result = self.round_coordinator.run_round_0_independent(market_context)
        history.rounds[0] = round_0_result.messages
        for name, opinion in round_0_result.opinions.items():
            if name not in history.opinions:
                history.opinions[name] = []
            history.opinions[name].append(opinion)
        history.conflict_map.extend(round_0_result.conflicts)
        
        # ===== ROUND 1: Critique Exchange =====
        if self.config.enable_round_1:
            round_1_result = self.round_coordinator.run_round_1_critique(
                market_context, round_0_result.opinions
            )
            history.rounds[1] = round_1_result.messages
            history.conflict_map = round_1_result.conflicts  # Updated conflicts
        else:
            round_1_result = RoundResult(
                round_type=RoundType.CRITIQUE_EXCHANGE,
                messages=[],
                opinions=round_0_result.opinions,
                conflicts=round_0_result.conflicts,
            )
        
        # ===== ROUND 2: Opinion Revision =====
        if self.config.enable_round_2:
            round_2_result = self.round_coordinator.run_round_2_revision(
                market_context, round_0_result.opinions, round_1_result.messages
            )
            history.rounds[2] = round_2_result.messages
            for name, opinion in round_2_result.opinions.items():
                history.opinions[name].append(opinion)
            history.conflict_map = round_2_result.conflicts
        else:
            round_2_result = RoundResult(
                round_type=RoundType.OPINION_REVISION,
                messages=[],
                opinions=round_0_result.opinions,
                conflicts=round_0_result.conflicts,
            )
        
        # ===== SUPERVISOR DECISION (Round 3) =====
        final_opinions = self.round_coordinator.get_final_opinions(round_2_result)
        final_decision = self.supervisor.synthesize_and_decide(
            market_context, 
            list(final_opinions.values()),
            conflict_map=history.conflict_map,
            full_history=history
        )
        
        history.final_decision = final_decision
        history.end_time = datetime.now()
        
        if self.config.save_history and self.history_store:
            self.history_store.save(history)
        
        return final_decision


# SupervisorAgent interface expected by ConsensusRoom
class SupervisorAgent:
    """Interface for the final decision-making agent."""
    
    def synthesize_and_decide(
        self,
        market_context: MarketContext,
        agent_opinions: List[AgentOpinion],
        conflict_map: List[Dict[str, Any]],
        full_history: DiscussionHistory,
    ) -> AgentOutput:
        raise NotImplementedError