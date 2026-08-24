#!/usr/bin/env python3
"""Agents Package - Auto-registration and exports"""

from .agent_architecture_core import (
    BaseAgent,
    AgentOutput,
    SignalType,
    MarketContext,
    SharedLLMEngine,
    DiscussingAgent,
    DiscussionContext,
    AgentOpinion,
    DebateMessage,
    MessageType,
    RoundType,
    DiscussionHistory,
    register_agent,
    get_registered_agents,
    get_agents_by_domain,
    AgentCapability,
)

# Import all agent classes
from .technical_agent import TechnicalAgent
from .macro_agent import MacroAgent
from .sentiment_agent import SentimentAgent
from .fundamental_agent import FundamentalAgent
from .risk_agent import RiskAgent
from .llm_supervisor_agent import LLMSupervisorAgent, LLMSupervisorDiscussingAgent



# Auto-register all analysis agents
register_agent(AgentCapability(
    agent_class=TechnicalAgent,
    name="TechnicalAgent",
    domain="technical",
    uses_llm=False,
    critique_domains=["fundamental", "macro", "sentiment"],
    supported_assets=["crypto", "equity", "fx"],
))

register_agent(AgentCapability(
    agent_class=MacroAgent,
    name="MacroAgent",
    domain="macro",
    uses_llm=False,
    critique_domains=["technical", "sentiment", "fundamental"],
    supported_assets=["crypto", "equity", "fx", "rates"],
))

register_agent(AgentCapability(
    agent_class=SentimentAgent,
    name="SentimentAgent",
    domain="sentiment",
    uses_llm=False,
    critique_domains=["technical", "fundamental", "macro"],
    supported_assets=["crypto", "equity"],
))

register_agent(AgentCapability(
    agent_class=FundamentalAgent,
    name="FundamentalAgent",
    domain="fundamental",
    uses_llm=False,
    critique_domains=["technical", "sentiment", "macro"],
    supported_assets=["crypto"],
))

register_agent(AgentCapability(
    agent_class=RiskAgent,
    name="RiskAgent",
    domain="risk",
    uses_llm=False,
    critique_domains=["technical", "fundamental", "sentiment", "macro"],
    supported_assets=["crypto", "equity", "fx"],
))

register_agent(AgentCapability(
    agent_class=LLMSupervisorAgent,
    name="LLMSupervisorAgent",
    domain="supervisor",
    uses_llm=True,
    critique_domains=[],
    supported_assets=["crypto", "equity", "fx"],
))

# Export consensus module
from . import consensus

__all__ = [
    # Core
    "BaseAgent",
    "AgentOutput",
    "SignalType",
    "MarketContext",
    "SharedLLMEngine",
    "DiscussingAgent",
    "DiscussionContext",
    "AgentOpinion",
    "DebateMessage",
    "MessageType",
    "RoundType",
    "DiscussionHistory",
    "register_agent",
    "get_registered_agents",
    "get_agents_by_domain",
    "AgentCapability",
    # Agents
    "TechnicalAgent",
    "MacroAgent",
    "SentimentAgent",
    "FundamentalAgent",
    "RiskAgent",
    "LLMSupervisorAgent",
    "LLMSupervisorDiscussingAgent",
    # Consensus
    "consensus",
]