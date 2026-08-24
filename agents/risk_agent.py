#!/usr/bin/env python3
"""Risk Agent - Risk management and position sizing"""

import time
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional

from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, DiscussingAgent,
    DiscussionContext, AgentOpinion, DebateMessage, MessageType, RoundType
)


class RiskAgent(DiscussingAgent):
    """Risk management agent - evaluates risk and sets position limits."""

    def __init__(self, max_drawdown: float = 0.2) -> None:
        super().__init__(name="RiskAgent")
        self.max_drawdown = max_drawdown

    def validate(self, context: MarketContext) -> bool:
        required = ["Close", "ATR_14", "volatility_20"]
        return all(col in context.features_df.columns for col in required)

    def analyze(self, context: MarketContext) -> AgentOutput:
        start_time = time.time()

        if not self.validate(context):
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["Insufficient risk data"],
            )

        latest = context.latest_bar
        price_df = context.raw_price_df
        
        score = 0.0
        reasons = []

        # Volatility assessment
        vol = latest.get("volatility_20", 0)
        atr_pct = latest.get("ATR_14", 0) / latest["Close"] if latest["Close"] > 0 else 0
        
        if vol < 0.02 and atr_pct < 0.015:
            score += 10
            reasons.append(f"Low volatility (vol={vol:.3f}, ATR%={atr_pct:.3f}) — favorable risk")
        elif vol > 0.05 or atr_pct > 0.03:
            score -= 15
            reasons.append(f"High volatility (vol={vol:.3f}, ATR%={atr_pct:.3f}) — elevated risk")

        # Drawdown from recent high
        drawdown = 0
        if len(price_df) >= 20:
            recent_high = price_df["Close"].tail(20).max()
            current = price_df["Close"].iloc[-1]
            drawdown = (recent_high - current) / recent_high
            if drawdown > self.max_drawdown:
                score -= 20
                reasons.append(f"Drawdown {drawdown:.1%} exceeds limit {self.max_drawdown:.0%}")
            elif drawdown < 0.05:
                score += 5
                reasons.append(f"Near highs (drawdown {drawdown:.1%})")

        # Risk-reward from technical levels (simplified)
        bb_pos = latest.get("BB_Position", 0.5)
        if bb_pos < 0.2:
            score += 10
            reasons.append("Price near BB lower band — good risk/reward for long")
        elif bb_pos > 0.8:
            score -= 10
            reasons.append("Price near BB upper band — poor risk/reward for long")

        # Risk agent doesn't produce directional signal, but NEUTRAL with risk info
        signal = SignalType.NEUTRAL
        confidence = 0.9  # High confidence in risk assessment

        execution_time = (time.time() - start_time) * 1000
        
        vix = latest.get("VIX", 20)  # Default to 20 if not present

        # در ایجنت ریسک، پس از تحلیل وولاتیلیتی و VIX
        # تعیین پارامترهای ریسک به صورت داینامیک
        if vol > 0.05 or vix > 30:  # بازار به شدت پرخطر است
            risk_pct = 0.01  # فقط 1% ریسک
            sl_multiplier = 2.5  # حد ضرر گسترده‌تر
            risk_level = "HIGH"
        elif vol < 0.02 and vix < 15:  # بازار آرام و روند دار
            risk_pct = 0.025  # 2.5% ریسک
            sl_multiplier = 1.0  # حد ضررtight
            risk_level = "LOW"
        else:  # شرایط عادی
            risk_pct = 0.02  # 2% ریسک
            sl_multiplier = 1.5
            risk_level = "MEDIUM"
                
        return AgentOutput(
            agent_name=self.name,
            signal=SignalType.NEUTRAL,
            confidence=confidence,
            score=round(score, 1),
            reasons=reasons,
            metadata={
                "risk_level": risk_level,
                "risk_pct": risk_pct,           
                "sl_multiplier": sl_multiplier,
                "volatility": round(vol, 4),
                "atr_pct": round(atr_pct, 4),
                "drawdown": round(drawdown, 4) if 'drawdown' in locals() else 0,
                "bb_position": round(bb_pos, 2),
            },
            execution_time_ms=round(execution_time, 2),
        )

    # ===== DiscussingAgent Interface =====

    def analyze_independent(self, context: DiscussionContext) -> AgentOpinion:
        legacy_output = self.analyze(context.market_context)
        return AgentOpinion(
            agent_name=self.name,
            round_number=0,
            signal=legacy_output.signal,
            confidence=legacy_output.confidence,
            score=legacy_output.score,
            reasoning=legacy_output.reasons,
            key_evidence=[
                f"Risk level: {legacy_output.metadata.get('risk_level', 'N/A')}",
                f"Volatility: {legacy_output.metadata.get('volatility', 'N/A')}",
                f"ATR%: {legacy_output.metadata.get('atr_pct', 'N/A')}",
                f"Drawdown: {legacy_output.metadata.get('drawdown', 'N/A')}",
            ],
            acknowledged_risks=["Risk metrics are backward-looking", "Black swan events not captured"],
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        messages = []
        
        for agent_name, opinion in context.other_agents_latest_opinions.items():
            # Risk agent critiques high-confidence directional bets when risk is high
            if opinion.confidence > 0.8 and abs(opinion.score) > 30:
                latest = context.market_context.latest_bar
                vol = latest.get("volatility_20", 0)
                atr_pct = latest.get("ATR_14", 0) / latest["Close"] if latest["Close"] > 0 else 0
                
                if vol > 0.04 or atr_pct > 0.025:
                    messages.append(DebateMessage(
                        message_id="",
                        sender=self.name,
                        target=agent_name,
                        message_type=MessageType.CRITIQUE,
                        content=f"High conviction ({opinion.confidence:.0%}) with high volatility (vol={vol:.3f}) — consider reducing position size",
                        evidence=[f"Volatility: {vol:.3f}", f"ATR%: {atr_pct:.3f}"],
                        confidence=0.8,
                        round_number=1,
                    ))
            
            # Critique leverage/margin risk
            if opinion.score > 50:  # Very bullish
                price_df = context.market_context.raw_price_df
                if len(price_df) >= 20:
                    recent_high = price_df["Close"].tail(20).max()
                    current = price_df["Close"].iloc[-1]
                    drawdown = (recent_high - current) / recent_high
                    if drawdown > 0.15:
                        messages.append(DebateMessage(
                            message_id="",
                            sender=self.name,
                            target=agent_name,
                            message_type=MessageType.CRITIQUE,
                            content=f"Significant drawdown ({drawdown:.1%}) from recent highs — caution on aggressive long",
                            evidence=[f"Drawdown: {drawdown:.1%}"],
                            confidence=0.75,
                            round_number=1,
                        ))
        
        return messages

    def revise_opinion(self, context: DiscussionContext) -> AgentOpinion:
        my_prev = context.my_previous_opinion
        if not my_prev:
            return self.analyze_independent(context)
        
        # Risk agent rarely changes risk assessment, but may adjust confidence
        should_revise = False
        change_reason = None
        
        for msg in context.messages_addressed_to_me:
            if msg.message_type == MessageType.CRITIQUE and msg.confidence > 0.7:
                if "risk" in msg.content.lower() or "volatility" in msg.content.lower() or "drawdown" in msg.content.lower():
                    should_revise = True
                    change_reason = f"Peer critique: {msg.content}"
                    break
        
        if should_revise:
            new_confidence = max(0.7, my_prev.confidence - 0.1)
            
            return AgentOpinion(
                agent_name=self.name,
                round_number=2,
                signal=my_prev.signal,
                confidence=new_confidence,
                score=my_prev.score,
                reasoning=my_prev.reasoning + [f"REVISED: {change_reason}"],
                key_evidence=my_prev.key_evidence,
                acknowledged_risks=my_prev.acknowledged_risks + ["Peer risk concern noted"],
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
        return ["technical", "fundamental", "sentiment", "macro"]