#!/usr/bin/env python3
"""Sentiment Agent - LLM-powered News and social sentiment analysis"""

import time
import json
import pandas as pd
from typing import Any, Dict, List, Optional

from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, DiscussingAgent,
    DiscussionContext, AgentOpinion, DebateMessage, MessageType, RoundType, SharedLLMEngine
)


class SentimentAgent(DiscussingAgent):
    """LLM-based news and social sentiment analysis agent."""

    def __init__(self, llm_engine: Optional[SharedLLMEngine] = None) -> None:
        super().__init__(name="SentimentAgent")
        self.llm_engine = llm_engine or SharedLLMEngine()

    def validate(self, context: MarketContext) -> bool:
        # فقط نیاز به دیتافریم خبر داریم، ستون sentiment دیگر لازم نیست
        return context.news_df is not None and len(context.news_df) > 0

    def _build_sentiment_prompt(self, news_df: pd.DataFrame) -> str:
        """Build prompt for LLM to analyze news sentiment."""
        # گرفتن 15 خبر اخیر
        recent_news = news_df.tail(15)
        
        news_text = []
        for idx, row in recent_news.iterrows():
            title = row.get("title", "No Title")
            source = row.get("source", "Unknown")
            news_text.append(f"- [{source}]: {title}")
            
        news_str = "\n".join(news_text)
        
        return f"""Analyze the sentiment of the following recent cryptocurrency news headlines:
        
        {news_str}

        Based on these headlines, determine the overall market sentiment for crypto assets.
        Consider the impact of macro news (Fed, inflation) and crypto-specific news.
        Provide your analysis as a JSON object with NO EXTRA TEXT:
        {{
        "score": -100 to +100 (negative for bearish, positive for bullish),
        "reasoning": "Complete analysis based on the data you have",
        "key_evidence": ["headline 1", "headline 2"]
        }}"""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM JSON response."""
        try:
            data = json.loads(response)
            score = float(data.get("score", 0))
            reasoning = data.get("reasoning", "LLM sentiment analysis")
            evidence = data.get("key_evidence", [])
            return {"score": score, "reasoning": reasoning, "evidence": evidence}
        except (json.JSONDecodeError, KeyError, ValueError):
            # در صورت خطا در پارسینگ، خنثی برمی‌گردانیم
            return {"score": 0, "reasoning": "Failed to parse LLM sentiment", "evidence": []}

    def analyze(self, context: MarketContext) -> AgentOutput:
        start_time = time.time()

        if not self.validate(context) or context.news_df is None:
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["Insufficient news data"],
            )

        # 1. ساخت پرامپت و گرفتن پاسخ از LLM
        prompt = self._build_sentiment_prompt(context.news_df)
        system_prompt = "You are a financial news sentiment analyzer. Output ONLY valid JSON."
        
        llm_response = self.llm_engine.generate(prompt, system_prompt)
        parsed = self._parse_llm_response(llm_response)
        
        score = parsed["score"]
        reasoning = parsed["reasoning"]
        evidence = parsed["evidence"]

        # 2. تبدیل اسکور به سیگنال
        if score >= 20:
            signal = SignalType.BUY
        elif score <= -20:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL

        # 3. محاسبه کانفیدنس بر اساس قدرت اسکور
        confidence = min(0.90, max(0.20, 0.40 + abs(score) / 100))
        
        # اگر LLM پاسخ غلط داد (مثلا متن برگرداند)، کانفیدنس را پایین می‌آوریم
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
                "evidence": evidence[:2],  # فقط 2 مدرک
                "article_count": len(context.news_df.tail(15))
            },
            execution_time_ms=round(execution_time, 2),
        )

    # ===== DiscussingAgent Interface =====

    def analyze_independent(self, context: DiscussionContext) -> AgentOpinion:
        legacy_output = self.analyze(context.market_context)
        
        # استخراج مدارک از متادیتا
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
            acknowledged_risks=["News sentiment can be noisy", "LLM may hallucinate", "Sentiment often lags price"],
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        messages = []
        my_opinion = context.my_previous_opinion
        
        # اگر خودمان سیگنال قوی داریم و کسی خلاف آن گفته، انتقاد می‌کنیم
        if not my_opinion:
            return messages
            
        for agent_name, opinion in context.other_agents_latest_opinions.items():
            if my_opinion.score > 25 and opinion.signal == SignalType.SELL:
                # ما مثبتیم، او منفی گفته
                my_evidence = my_opinion.key_evidence[0] if my_opinion.key_evidence else "positive news"
                messages.append(DebateMessage(
                    message_id="",
                    sender=self.name,
                    target=agent_name,
                    message_type=MessageType.CRITIQUE,
                    content=f"Recent news sentiment is positive ({my_evidence}), which contradicts your bearish stance",
                    evidence=my_opinion.key_evidence[:1],
                    confidence=0.70,
                    round_number=1,
                ))
            elif my_opinion.score < -25 and opinion.signal == SignalType.BUY:
                # ما منفی‌ایم، او مثبت گفته
                my_evidence = my_opinion.key_evidence[0] if my_opinion.key_evidence else "negative news"
                messages.append(DebateMessage(
                    message_id="",
                    sender=self.name,
                    target=agent_name,
                    message_type=MessageType.CRITIQUE,
                    content=f"Recent news sentiment is negative ({my_evidence}), which contradicts your bullish stance",
                    evidence=my_opinion.key_evidence[:1],
                    confidence=0.70,
                    round_number=1,
                ))
        
        return messages

    def revise_opinion(self, context: DiscussionContext) -> AgentOpinion:
        my_prev = context.my_previous_opinion
        if not my_prev:
            return self.analyze_independent(context)
        
        should_revise = False
        change_reason = None
        
        # اگر ایجنت‌های فاندامنتال یا تکنیکال با اعتمادبه‌نفس بالا مخالفت کردند
        for msg in context.messages_addressed_to_me:
            if msg.message_type == MessageType.CRITIQUE and msg.confidence > 0.65:
                if "sentiment" in msg.content.lower() or "news" in msg.content.lower():
                    should_revise = True
                    change_reason = f"Peer critique: {msg.content}"
                    break
        
        if should_revise:
            new_confidence = max(0.25, my_prev.confidence - 0.20)
            new_score = my_prev.score * 0.6  # کاهش قدرت سیگنال
            
            return AgentOpinion(
                agent_name=self.name,
                round_number=2,
                signal=my_prev.signal,
                confidence=new_confidence,
                score=new_score,
                reasoning=my_prev.reasoning + [f"REVISED: {change_reason}"],
                key_evidence=my_prev.key_evidence,
                acknowledged_risks=my_prev.acknowledged_risks + ["Peer contradiction noted"],
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
        return ["technical", "fundamental", "macro"]