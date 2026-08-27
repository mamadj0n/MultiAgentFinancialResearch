#!/usr/bin/env python3
"""Fundamental Agent - LLM-powered On-chain / fundamental metrics analysis"""

import time
import json
import pandas as pd
from typing import Any, Dict, List, Optional

from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, DiscussingAgent,
    DiscussionContext, AgentOpinion, DebateMessage, MessageType, RoundType, SharedLLMEngine
)
from utils.config import FUNDAMENTAL_BUY_THRESHOLD, FUNDAMENTAL_SELL_THRESHOLD


class FundamentalAgent(DiscussingAgent):
    """LLM-based On-chain / fundamental metrics analysis agent."""

    def __init__(self, llm_engine: Optional[SharedLLMEngine] = None) -> None:
        super().__init__(name="FundamentalAgent")
        self.llm_engine = llm_engine or SharedLLMEngine()

    def validate(self, context: MarketContext) -> bool:
        # برای فاندامنتال نیاز به قیمت داریم. onchain_df اختیاری است اما داشتش بهتر است.
        return context.features_df is not None and len(context.features_df) > 40

    def _build_fundamental_prompt(self, context: MarketContext) -> str:
        """Build prompt for LLM to analyze fundamental and on-chain data."""
        latest_feat = context.latest_bar
        price_df = context.raw_price_df
        
        # 1. محاسبه مومنتوم ۳۰ روزه
        mom_30 = 0
        if len(price_df) >= 30:
            mom_30 = (price_df["Close"].iloc[-1] / price_df["Close"].iloc[-30] - 1) * 100
            
        # 2. استخراج داده‌های زنجیره‌ای (On-chain)
        onchain_str = "No specific on-chain data provided."
        if context.onchain_df is not None and not context.onchain_df.empty:
            latest_onchain = context.onchain_df.iloc[-1]
            onchain_items = []
            for col, val in latest_onchain.items():
                if pd.notna(val):
                    # فرمت بندی اعداد بزرگ
                    if isinstance(val, (int, float)) and val > 1000:
                        onchain_items.append(f"- {col}: {val:,.0f}")
                    else:
                        onchain_items.append(f"- {col}: {val}")
            onchain_str = "\n".join(onchain_items) if onchain_items else "On-chain data empty."
            
        vol_ratio = latest_feat.get("Volume_Ratio", 1.0)
        
        return f"""Analyze the fundamental health and on-chain activity for this cryptocurrency:

                - 30-Day Price Momentum: {mom_30:.2f}%
                - Volume Ratio (vs 20d avg): {vol_ratio:.2f}
                - On-Chain Network Metrics: {onchain_str}

                Based on this data, evaluate if the network is showing accumulation, growth, or distribution.
                Provide your analysis as a JSON object with NO EXTRA TEXT:
                {{
                "score": -100 to +100 (negative for bearish fundamentals, positive for bullish),
                "reasoning": "Complete analysis based on the data you have",
                "key_evidence": ["on-chain metric 1", "on-chain metric 2"]
                }}"""

    def analyze(self, context: MarketContext) -> AgentOutput:
        start_time = time.time()

        if not self.validate(context):
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["Insufficient fundamental data"],
            )

        prompt = self._build_fundamental_prompt(context)
        system_prompt = "You are a Crypto On-Chain Analyst. Output ONLY valid JSON."
        llm_response = self.llm_engine.generate(prompt, system_prompt)
        parsed = self.parse_llm_json(llm_response, "FundamentalAgent")
        
        score = parsed["score"]
        reasoning = parsed["reasoning"]
        evidence = parsed["evidence"]

        # 2. تبدیل اسکور به سیگنال
        if score >= FUNDAMENTAL_BUY_THRESHOLD:
            signal = SignalType.BUY
        elif score <= FUNDAMENTAL_SELL_THRESHOLD:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL

        # 3. محاسبه کانفیدنس
        confidence = min(0.85, max(0.20, 0.40 + abs(score) / 80))
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
                "momentum_30d": round(((context.raw_price_df["Close"].iloc[-1] / context.raw_price_df["Close"].iloc[-30] - 1) * 100), 1) if len(context.raw_price_df) >= 30 else 0,
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
            acknowledged_risks=["On-chain metrics can lag", "Whale manipulation"],
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        messages = []
        my_opinion = context.my_previous_opinion
        
        if not my_opinion:
            return messages
            
        # اگر فاندامنتال قوی است و دیگران فروش می‌دهند
        if my_opinion.score > 25:
            for agent_name, opinion in context.other_agents_latest_opinions.items():
                if opinion.signal == SignalType.SELL:
                    my_evidence = my_opinion.key_evidence[0] if my_opinion.key_evidence else "strong on-chain accumulation"
                    messages.append(DebateMessage(
                        message_id="",
                        sender=self.name,
                        target=agent_name,
                        message_type=MessageType.CRITIQUE,
                        content=f"On-chain metrics show accumulation ({my_evidence}), which contradicts your bearish view.",
                        evidence=my_opinion.key_evidence[:1],
                        confidence=0.65,
                        round_number=1,
                    ))
        # اگر فاندامنتال ضعیف است و دیگران خرید می‌دهند
        elif my_opinion.score < -25:
            for agent_name, opinion in context.other_agents_latest_opinions.items():
                if opinion.signal == SignalType.BUY:
                    my_evidence = my_opinion.key_evidence[0] if my_opinion.key_evidence else "on-chain distribution"
                    messages.append(DebateMessage(
                        message_id="",
                        sender=self.name,
                        target=agent_name,
                        message_type=MessageType.CRITIQUE,
                        content=f"On-chain metrics indicate distribution ({my_evidence}), which contradicts your bullish stance.",
                        evidence=my_opinion.key_evidence[:1],
                        confidence=0.65,
                        round_number=1,
                    ))
        
        return messages

    def get_critique_priorities(self) -> List[str]:
        return ["technical", "sentiment", "macro"]
