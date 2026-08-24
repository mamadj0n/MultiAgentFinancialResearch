#!/usr/bin/env python3
"""Discussion Context Builder - Prepares context for each agent per round"""

from typing import Dict, List, Optional
from ..agent_architecture_core import (
    DiscussionContext, MarketContext, AgentOpinion, DebateMessage, RoundType
)


class DiscussionContextBuilder:
    """
    Builds DiscussionContext objects for each agent at each round.
    Ensures agents only see what they should see (information asymmetry).
    """
    
    def __init__(self, token_budget: int = 2000):
        self.token_budget = token_budget
    
    def build_round_0_context(
        self,
        market_context: MarketContext,
        agent_name: str,
    ) -> DiscussionContext:
        """Round 0: Pure independent analysis, no peer information."""
        return DiscussionContext(
            market_context=market_context,
            current_round=RoundType.INDEPENDENT_ANALYSIS,
            my_previous_opinion=None,
            messages_addressed_to_me=[],
            other_agents_latest_opinions={},
            unresolved_conflicts=[],
            token_budget=self.token_budget,
        )
    
    def build_round_1_context(
        self,
        market_context: MarketContext,
        agent_name: str,
        round_0_opinions: Dict[str, AgentOpinion],
        unresolved_conflicts: List[Dict],
        messages_for_agent: List[DebateMessage],
    ) -> DiscussionContext:
        """Round 1: Agent sees all other opinions, receives critiques."""
        my_opinion = round_0_opinions[agent_name]
        other_opinions = {n: o for n, o in round_0_opinions.items() if n != agent_name}
        
        return DiscussionContext(
            market_context=market_context,
            current_round=RoundType.CRITIQUE_EXCHANGE,
            my_previous_opinion=my_opinion,
            messages_addressed_to_me=messages_for_agent,
            other_agents_latest_opinions=other_opinions,
            unresolved_conflicts=unresolved_conflicts,
            token_budget=self.token_budget,
        )
    
    def build_round_2_context(
        self,
        market_context: MarketContext,
        agent_name: str,
        round_0_opinions: Dict[str, AgentOpinion],
        round_1_messages: List[DebateMessage],
        unresolved_conflicts: List[Dict],
    ) -> DiscussionContext:
        """Round 2: Agent sees critiques addressed to them, may revise."""
        my_opinion = round_0_opinions[agent_name]
        other_opinions = {n: o for n, o in round_0_opinions.items() if n != agent_name}
        
        # Filter messages: broadcast (target=None) or addressed to this agent
        my_messages = [
            m for m in round_1_messages 
            if m.target is None or m.target == agent_name
        ]
        
        return DiscussionContext(
            market_context=market_context,
            current_round=RoundType.OPINION_REVISION,
            my_previous_opinion=my_opinion,
            messages_addressed_to_me=my_messages,
            other_agents_latest_opinions=other_opinions,
            unresolved_conflicts=unresolved_conflicts,
            token_budget=self.token_budget,
        )
    
    def build_supervisor_context(
        self,
        market_context: MarketContext,
        final_opinions: Dict[str, AgentOpinion],
        conflict_map: List[Dict],
        full_history, ) -> DiscussionContext:
        
        """Supervisor sees everything."""
        return DiscussionContext(
            market_context=market_context,
            current_round=RoundType.SUPERVISOR_DECISION,
            my_previous_opinion=None,
            messages_addressed_to_me=[],
            other_agents_latest_opinions=final_opinions,
            unresolved_conflicts=conflict_map,
            token_budget=4000,  # Supervisor gets more tokens
        )