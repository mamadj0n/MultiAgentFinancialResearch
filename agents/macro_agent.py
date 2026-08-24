#!/usr/bin/env python3
"""Macro Agent - LLM-powered Macroeconomic analysis"""

import time
import json
from typing import Any, Dict, List, Optional
import pandas as pd

from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, DiscussingAgent,
    DiscussionContext, AgentOpinion, DebateMessage, MessageType, RoundType, SharedLLMEngine
)


class MacroAgent(DiscussingAgent):
    """LLM-based macroeconomic analysis agent."""

    def __init__(self, llm_engine: Optional[SharedLLMEngine] = None) -> None:
        super().__init__(name="MacroAgent")
        self.llm_engine = llm_engine or SharedLLMEngine()

    def validate(self, context: MarketContext) -> bool:
        return context.macro_df is not None and len(context.macro_df) >= 13

    def _build_macro_prompt(self, latest_macro: pd.Series) -> str:
        """Build prompt for LLM to analyze macro data."""
        interest_rate = latest_macro.get("US_Interest_Rate", 4.5)
        cpi_yoy = latest_macro.get("US_Inflation_YoY", 2.5)
        dxy = latest_macro.get("DXY_Index", 100)
        vix = latest_macro.get("VIX", 20)
        us10y = latest_macro.get("US10Y_Yield", 4.0)
        gold = latest_macro.get("Gold", 2000)
        
        if interest_rate > 3.0:
            policy_stance = "Restrictive (High rates - Bearish for crypto)"
        elif interest_rate < 1.0:
            policy_stance = "Accommodative (Low rates - Bullish for crypto)"
        else:
            policy_stance = "Neutral"
            
        return f"""Analyze the current macroeconomic environment for cryptocurrency (Bitcoin) trading:
        
                - US Interest Rate: {interest_rate:.2f}% ({policy_stance})
                - CPI YoY (Inflation): {cpi_yoy:.2f}%
                - DXY (Dollar Index): {dxy:.2f}
                - VIX (Volatility Index): {vix:.2f}
                - US 10Y Yield: {us10y:.2f}%
                - Gold Price: ${gold:.2f}

                Provide your macro analysis as a JSON object with NO EXTRA TEXT:
                {{
                "score": -100 to +100 (negative for bearish crypto, positive for bullish),
                "reasoning": "Complete analysis based on the data you have",
                "key_evidence": ["macro factor 1", "macro factor 2"]
                }}"""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        try:
            data = json.loads(response)
            score = float(data.get("score", 0))
            reasoning = data.get("reasoning", "LLM macro analysis")
            evidence = data.get("key_evidence", [])
            return {"score": score, "reasoning": reasoning, "evidence": evidence}
        except (json.JSONDecodeError, KeyError, ValueError):
            return {"score": 0, "reasoning": "Failed to parse LLM macro", "evidence": []}

    def analyze(self, context: MarketContext) -> AgentOutput:
        start_time = time.time()

        if not self.validate(context) or context.macro_df is None:
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["Insufficient macro data"],
            )

        latest_macro = context.macro_df.iloc[-1]
        
        # 1. گرفتن تحلیل از LLM
        prompt = self._build_macro_prompt(latest_macro)
        system_prompt = "You are a Chief Macro Economist. Output ONLY valid JSON."
        llm_response = self.llm_engine.generate(prompt, system_prompt)
        parsed = self._parse_llm_response(llm_response)
        
        score = parsed["score"]
        reasoning = parsed["reasoning"]
        evidence = parsed["evidence"]

        # 2. تبدیل اسکور به سیگنال
        if score >= 35:
            signal = SignalType.BUY
        elif score <= -35:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL

        # 3. محاسبه کانفیدنس
        confidence = min(0.90, max(0.20, 0.40 + abs(score) / 100))
        if "Failed to parse" in reasoning:
            confidence = 0.15

        execution_time = (time.time() - start_time) * 1000

        return AgentOutput(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            score=round(score, 1),
            reasons=[reasoning],
            metadata={
                "evidence": evidence[:2],
                "interest_rate": latest_macro.get("US_Interest_Rate", 0),
                "dxy": latest_macro.get("DXY_Index", 0),
                "vix": latest_macro.get("VIX", 0)
            },
            execution_time_ms=round(execution_time, 2),
        )

    # ===== DiscussingAgent Interface =====

    def analyze_independent(self, context: DiscussionContext) -> AgentOpinion:
        legacy_output = self.analyze(context.market_context)
        evidence = legacy_output.metadata.get("evidence", [])
        if not evidence:
            evidence = [legacy_output.reasons[0] if legacy_output.reasons else "N/A"]
            
        return AgentOpinion(
            agent_name=self.name,
            round_number=0,
            signal=legacy_output.signal,
            confidence=legacy_output.confidence,
            score=legacy_output.score,
            reasoning=legacy_output.reasons,
            key_evidence=evidence,
            acknowledged_risks=["Macro data is lagging", "Policy changes can be sudden"],
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        messages = []
        my_opinion = context.my_previous_opinion
        
        if not my_opinion:
            return messages
            
        # اگر اقتصاد کلان منفی است و دیگران به شدت خرید می‌خواهند، انتقاد می‌کنیم
        if my_opinion.score < -20:
            for agent_name, opinion in context.other_agents_latest_opinions.items():
                if opinion.signal == SignalType.BUY and opinion.score > 20:
                    my_evidence = my_opinion.key_evidence[0] if my_opinion.key_evidence else "macro headwinds"
                    messages.append(DebateMessage(
                        message_id="",
                        sender=self.name,
                        target=agent_name,
                        message_type=MessageType.CRITIQUE,
                        content=f"Macro environment is hostile ({my_evidence}). Your bullish stance ignores macro risks.",
                        evidence=my_opinion.key_evidence[:1],
                        confidence=0.75,
                        round_number=1,
                    ))
        # اگر اقتصاد کلان مثبت است و دیگران به شدت فروش می‌خواهند
        elif my_opinion.score > 20:
            for agent_name, opinion in context.other_agents_latest_opinions.items():
                if opinion.signal == SignalType.SELL and opinion.score < -20:
                    my_evidence = my_opinion.key_evidence[0] if my_opinion.key_evidence else "macro tailwinds"
                    messages.append(DebateMessage(
                        message_id="",
                        sender=self.name,
                        target=agent_name,
                        message_type=MessageType.CRITIQUE,
                        content=f"Macro environment is supportive ({my_evidence}). Your bearish stance contradicts macro trends.",
                        evidence=my_opinion.key_evidence[:1],
                        confidence=0.75,
                        round_number=1,
                    ))
        
        return messages

    def revise_opinion(self, context: DiscussionContext) -> AgentOpinion:
        my_prev = context.my_previous_opinion
        if not my_prev:
            return self.analyze_independent(context)
        
        should_revise = False
        change_reason = None
        
        for msg in context.messages_addressed_to_me:
            if msg.message_type == MessageType.CRITIQUE and msg.confidence > 0.7:
                if "macro" in msg.content.lower() or "fundamental" in msg.content.lower():
                    should_revise = True
                    change_reason = f"Peer critique: {msg.content}"
                    break
        
        if should_revise:
            new_confidence = max(0.3, my_prev.confidence - 0.15)
            new_score = my_prev.score * 0.7  # کاهش قدرت سیگنال
            
            return AgentOpinion(
                agent_name=self.name,
                round_number=2,
                signal=my_prev.signal,
                confidence=new_confidence,
                score=new_score,
                reasoning=my_prev.reasoning + [f"REVISED: {change_reason}"],
                key_evidence=my_prev.key_evidence,
                acknowledged_risks=my_prev.acknowledged_risks + ["Peer macro concern noted"],
                changed_from_previous=True,
                change_reason=change_reason,
            )
        
        return AgentOpinion(
            agent_name=self.name,
            round_number=2,
            signal=my_prev.signal,
            confidence=my_prev.confidence,
            score=my_prev.score,
            reasoning=my_prev.reasoning,
            key_evidence=my_prev.key_evidence,
            acknowledged_risks=my_prev.acknowledged_risks,
            changed_from_previous=False,
        )

    def get_critique_priorities(self) -> List[str]:
        return ["technical", "sentiment", "fundamental"]