#!/usr/bin/env python3

import requests
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd

from utils.config import PROVIDER, online_api_key
from utils.retry import retry_on_exception

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1. Standardized Agent Output
# ------------------------------------------------------------------
class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"

@dataclass
class AgentOutput:
    agent_name: str
    signal: SignalType
    confidence: float          # Number between 0.0 to 1.0
    score: float               # Numeric score between -100 to +100
    reasons: List[str]         # Reasons for agent decision
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# ------------------------------------------------------------------
# 2. MarketContext
# ------------------------------------------------------------------
@dataclass
class MarketContext:
    symbol: str
    timeframe: str
    features_df: pd.DataFrame
    raw_price_df: pd.DataFrame
    macro_df: Optional[pd.DataFrame] = None
    news_df: Optional[pd.DataFrame] = None
    onchain_df: Optional[pd.DataFrame] = None
    vector_store: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def latest_bar(self) -> pd.Series:
        """Quick access to latest processed candle with all 45+ features"""
        return self.features_df.iloc[-1]


# ------------------------------------------------------------------
# 3. BaseAgent Abstract Class
# ------------------------------------------------------------------
class BaseAgent(ABC):
    """
    Abstract Base Class that all Analysis, Risk, and Supervisor agents must inherit from.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def validate(self, context: MarketContext) -> bool:
        """Check validity and sufficiency of input data for this agent"""
        pass

    @abstractmethod
    def analyze(self, context: MarketContext) -> AgentOutput:
        """Main analysis logic producing standardized AgentOutput"""
        pass


# ==================================================================
# 4. SharedLLMEngine
# ==================================================================

class SharedLLMEngine:
    def __init__(
        self,
        model_name: str = "qwen2.5:3b",
        mode: str = PROVIDER, # "local" or "online"
    ):
        self.mode = mode.lower()

        # =========================
        # Local / Ollama
        # =========================
        self.local_model_name = model_name
        self.local_api_url = "http://localhost:11434/api/generate"

        # =========================
        # Online / 9router
        # =========================
        self.online_model_name = "MODSO"
        self.online_api_url = "http://localhost:20128/v1/chat/completions"

        self.online_api_key = online_api_key

    # ==========================================================
    # PUBLIC INTERFACE
    # ==========================================================

    def generate(
        self,
        prompt: str,
        system_prompt: str = ""
    ) -> str:

        try:

            if self.mode == "local":
                result = self._generate_local(
                    prompt,
                    system_prompt
                )

            elif self.mode == "online":
                result = self._generate_online(
                    prompt,
                    system_prompt
                )

            else:
                raise ValueError(
                    f"Unknown LLM mode: {self.mode}"
                )

            # ==================================================
            # VERY IMPORTANT:
            # generate() ALWAYS returns str
            # ==================================================

            return self._normalize_response(result)

        except Exception as e:
            logger.error(f"[SharedLLMEngine] Error: {e}")
            return ""

    # ==========================================================
    # LOCAL
    # ==========================================================

    @retry_on_exception(max_retries=3, delay=1.0, backoff=2.0, exceptions=(requests.RequestException,))
    def _generate_local(
        self,
        prompt: str,
        system_prompt: str = ""
    ):
        payload = {
            "model": self.local_model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 512,
                "num_thread": 4,
            }
        }

        response = requests.post(
            self.local_api_url,
            json=payload,
            timeout=300
        )

        response.raise_for_status()

        data = response.json()

        # Ollama normally returns:
        #
        # {
        #     "response": "..."
        # }

        return data.get("response", "")

    # ==========================================================
    # ONLINE / 9ROUTER
    # ==========================================================

    @retry_on_exception(max_retries=3, delay=1.0, backoff=2.0, exceptions=(requests.RequestException,))
    def _generate_online(
        self,
        prompt: str,
        system_prompt: str = ""
    ):
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        payload = {
            "model": self.online_model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 512,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.online_api_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            self.online_api_url,
            headers=headers,
            json=payload,
            timeout=300
        )

        response.raise_for_status()

        data = response.json()

        # OpenAI-compatible response
        #
        # {
        #     "choices": [
        #         {
        #             "message": {
        #                 "content": "..."
        #             }
        #         }
        #     ]
        # }

        try:
            return data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError):
            # اگر ساختار API متفاوت بود،
            # خود response را برمی‌گردانیم تا
            # _normalize_response آن را تبدیل کند.
            return data

    # ==========================================================
    # RESPONSE NORMALIZER
    # ==========================================================

    def _normalize_response(self, response) -> str:
        """
        GUARANTEE:
            This method ALWAYS returns str.
        """

        # ------------------------------------------
        # None
        # ------------------------------------------

        if response is None:
            return ""

        # ------------------------------------------
        # Already string
        # ------------------------------------------

        if isinstance(response, str):
            return response.strip()

        # ------------------------------------------
        # Dict
        # ------------------------------------------

        if isinstance(response, dict):

            # OpenAI-compatible structure
            if "choices" in response:

                try:
                    content = (
                        response["choices"][0]
                        ["message"]
                        ["content"]
                    )

                    return self._normalize_response(content)

                except (KeyError, IndexError, TypeError):
                    pass

            # Ollama structure
            if "response" in response:
                return self._normalize_response(
                    response["response"]
                )

            # اگر خود dict پاسخ مدل باشد
            # آن را JSON string می‌کنیم
            try:
                return json.dumps(
                    response,
                    ensure_ascii=False
                )
            except Exception:
                return str(response)

        # ------------------------------------------
        # List / Tuple
        # ------------------------------------------

        if isinstance(response, (list, tuple)):

            try:
                return json.dumps(
                    response,
                    ensure_ascii=False
                )
            except Exception:
                return str(response)

        # ------------------------------------------
        # Numbers / bool / other objects
        # ------------------------------------------

        return str(response)

        
# ==================================================================
# CONSENSUS ROOM CORE CONTRACTS (Discussion Protocol)
# ==================================================================

class MessageType(str, Enum):
    CLAIM = "CLAIM"                 # Initial independent analysis
    CRITIQUE = "CRITIQUE"           # Disagreement with evidence
    DEFENSE = "DEFENSE"             # Rebuttal to critique
    QUESTION = "QUESTION"           # Clarification request
    CONCESSION = "CONCESSION"       # Explicit agreement with counter-argument
    SUPPORT = "SUPPORT"             # Agreement with reasoning
    CORRECTION = "CORRECTION"       # Factual correction
    FINAL_STATEMENT = "FINAL_STATEMENT"  # Round 2 revised opinion

class RoundType(str, Enum):
    INDEPENDENT_ANALYSIS = "ROUND_0"
    CRITIQUE_EXCHANGE = "ROUND_1"
    OPINION_REVISION = "ROUND_2"
    SUPERVISOR_DECISION = "ROUND_3"

@dataclass
class DebateMessage:
    """Structured message exchanged in Consensus Room."""
    message_id: str
    sender: str
    target: Optional[str]           # None = broadcast to all
    message_type: MessageType
    content: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    round_number: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    in_reply_to: Optional[str] = None  # message_id being responded to
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentOpinion:
    """Single source of truth for an agent's position at a given round."""
    agent_name: str
    round_number: int
    signal: SignalType
    confidence: float
    score: float
    reasoning: List[str]
    key_evidence: List[str] = field(default_factory=list)
    acknowledged_risks: List[str] = field(default_factory=list)
    changed_from_previous: bool = False
    change_reason: Optional[str] = None

@dataclass
class DiscussionContext:
    """Minimal context passed to each agent per round."""
    market_context: MarketContext
    current_round: RoundType
    my_previous_opinion: Optional[AgentOpinion]
    messages_addressed_to_me: List[DebateMessage]
    other_agents_latest_opinions: Dict[str, AgentOpinion]  # name -> opinion
    unresolved_conflicts: List[Dict[str, Any]]  # Pre-computed conflict summary
    supervisor_guidance: Optional[str] = None
    token_budget: int = 2000  # Max tokens for this agent's response

@dataclass
class DiscussionHistory:
    """Complete structured debate record."""
    session_id: str
    symbol: str
    start_time: datetime
    end_time: Optional[datetime] = None
    rounds: Dict[int, List[DebateMessage]] = field(default_factory=dict)
    opinions: Dict[str, List[AgentOpinion]] = field(default_factory=dict)  # agent_name -> [opinions]
    conflict_map: List[Dict[str, Any]] = field(default_factory=list)
    final_decision: Optional[AgentOutput] = None

# ------------------------------------------------------------------
# 5. Extended BaseAgent with Discussion Capabilities
# ------------------------------------------------------------------
class DiscussingAgent(BaseAgent):
    """Mixin for agents participating in Consensus Room."""

    @abstractmethod
    def analyze_independent(self, context: DiscussionContext) -> AgentOpinion:
        """Round 0: Independent analysis without seeing others."""
        pass

    @abstractmethod
    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        """Round 1: Read all opinions, emit critiques/questions/support."""
        pass

    def revise_opinion(self, context: DiscussionContext) -> AgentOpinion:
        """Round 2: Default revision — reduce score by 30% if high-confidence critique received."""
        my_prev = context.my_previous_opinion
        if not my_prev:
            return self.analyze_independent(context)

        should_revise = False
        change_reason = None
        for msg in context.messages_addressed_to_me:
            if msg.message_type == MessageType.CRITIQUE and msg.confidence > 0.7:
                should_revise = True
                change_reason = f"Peer critique: {msg.content}"
                break

        if should_revise:
            new_confidence = max(0.25, my_prev.confidence - 0.15)
            new_score = my_prev.score * 0.7
            return AgentOpinion(
                agent_name=self.name, round_number=2,
                signal=my_prev.signal, confidence=new_confidence, score=new_score,
                reasoning=my_prev.reasoning + [f"REVISED: {change_reason}"],
                key_evidence=my_prev.key_evidence,
                acknowledged_risks=my_prev.acknowledged_risks + ["Peer concern noted"],
                changed_from_previous=True, change_reason=change_reason,
            )

        return AgentOpinion(
            agent_name=self.name, round_number=2,
            signal=my_prev.signal, confidence=my_prev.confidence, score=my_prev.score,
            reasoning=my_prev.reasoning, key_evidence=my_prev.key_evidence,
            acknowledged_risks=my_prev.acknowledged_risks, changed_from_previous=False,
        )

    def get_critique_priorities(self) -> List[str]:
        """Which agent types this agent most often critiques. Override to customize."""
        return []

    @staticmethod
    def parse_llm_json(response: str, agent_label: str = "LLM") -> Dict[str, Any]:
        """Shared JSON parser for LLM responses with safe fallback."""
        try:
            data = json.loads(response)
            return {
                "score": float(data.get("score", 0)),
                "reasoning": data.get("reasoning", f"{agent_label} analysis"),
                "evidence": data.get("key_evidence", []),
            }
        except (json.JSONDecodeError, KeyError, ValueError):
            return {"score": 0, "reasoning": f"Failed to parse {agent_label}", "evidence": []}


# ------------------------------------------------------------------
# 6. Agent Capability Registry for Auto-Discovery
# ------------------------------------------------------------------
class AgentCapability:
    """Metadata for agent auto-registration."""
    def __init__(
        self,
        agent_class: type,
        name: str,
        domain: str,           # "technical", "macro", "sentiment", "fundamental", "risk"
        uses_llm: bool,
        critique_domains: List[str] = None,  # Domains this agent typically critiques
        supported_assets: List[str] = None,  # e.g., ["crypto", "equity", "fx"]
    ):
        self.agent_class = agent_class
        self.name = name
        self.domain = domain
        self.uses_llm = uses_llm
        self.critique_domains = critique_domains or []
        self.supported_assets = supported_assets or ["crypto"]

_agent_registry: List[AgentCapability] = []

def register_agent(capability: AgentCapability) -> None:
    _agent_registry.append(capability)

def get_registered_agents() -> List[AgentCapability]:
    return _agent_registry.copy()

def get_agents_by_domain(domain: str) -> List[AgentCapability]:
    return [c for c in _agent_registry if c.domain == domain]
