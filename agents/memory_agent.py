# agents/memory_agent.py
import time
import json
from typing import Any, Dict, List, Optional
from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, DiscussingAgent,
    DiscussionContext, AgentOpinion, DebateMessage, MessageType, SharedLLMEngine
)
from memory_store import MemoryStore

class MemoryAgent(DiscussingAgent):
    """ایجنت حافظه: تحلیل تریدهای گذشته برای تنظیم اعتمادبه‌نفس"""
    
    def __init__(self, memory_store: MemoryStore, llm_engine: Optional[SharedLLMEngine] = None):
        super().__init__(name="MemoryAgent")
        self.memory_store = memory_store
        self.llm_engine = llm_engine or SharedLLMEngine()

    def validate(self, context: MarketContext) -> bool:
        return True

    def _get_current_fingerprint(self, context: MarketContext) -> Dict[str, str]:
        """استخراج سریع وضعیت فعلی برای جستجو در دیتابیس"""
        latest = context.latest_bar
        # یک تحلیل سریع برای تطبیق با دیتابیس
        tech_sig = "BUY" if latest["Close"] > latest.get("EMA_20", latest["Close"]) else "SELL"
        macro_sig = "SELL" if latest.get("US_Interest_Rate", 0) > 3.0 else "BUY"
        return {"macro_signal": macro_sig, "tech_signal": tech_sig}

    def analyze(self, context: MarketContext) -> AgentOutput:
        start_time = time.time()
        
        fingerprint = self._get_current_fingerprint(context)
        similar_trades = self.memory_store.retrieve_similar_trades(
            macro_signal=fingerprint["macro_signal"],
            tech_signal=fingerprint["tech_signal"],
            limit=3
        )
        
        if not similar_trades:
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.5,
                score=0.0, # ضریب تعدیل صفر
                reasons=["No similar historical trades found yet."],
                metadata={"adjustment_factor": 0.0}
            )

        # ساخت خلاصه برای LLM
        trades_summary = []
        for t in similar_trades:
            trades_summary.append(f"- Past {t['direction']} trade resulted in PnL: ${t['pnl']:.2f} ({t['r_multiple']:.1f}R). Reason: {t['supervisor_reason']}")
        
        prompt = f"""Analyze these past similar trading setups:
        {chr(10).join(trades_summary)}

        Current Market Fingerprint: Macro={fingerprint['macro_signal']}, Tech={fingerprint['tech_signal']}
        Based on past outcomes, provide an adjustment score for the current decision.
        If past trades were profitable, give a positive score. If they lost money, give a negative score to warn the supervisor.
        Output JSON ONLY: {{"score": -50 to +50, "reasoning": "One sentence", "evidence": ["past result 1"]}}"""

        try:
            response = self.llm_engine.generate(prompt, "You are a quantitative trading historian. Output ONLY JSON.")
            data = json.loads(response)
            score = float(data.get("score", 0))
            reasoning = data.get("reasoning", "Historical pattern detected.")
            evidence = data.get("evidence", [])
        except Exception:
            # اگر LLM ارور داد، خودمان سریع محاسبه می‌کنیم
            wins = sum(1 for t in similar_trades if t['win'] == 1)
            losses = len(similar_trades) - wins
            score = (wins - losses) * 10
            reasoning = f"Historical match: {wins} wins, {losses} losses."
            evidence = [f"Past PnL: ${t['pnl']:.2f}" for t in similar_trades]

        return AgentOutput(
            agent_name=self.name,
            signal=SignalType.NEUTRAL,
            confidence=0.8,
            score=round(score, 1),
            reasons=[reasoning],
            metadata={"adjustment_factor": score, "evidence": evidence},
            execution_time_ms=round((time.time() - start_time) * 1000, 2)
        )

    # متدهای Discussion (برای شرکت در اتاق گفتگو)
    def analyze_independent(self, context: DiscussionContext) -> AgentOpinion:
        legacy = self.analyze(context.market_context)
        return AgentOpinion(
            agent_name=self.name, round_number=0, signal=legacy.signal,
            confidence=legacy.confidence, score=legacy.score,
            reasoning=legacy.reasons,
            key_evidence=legacy.metadata.get("evidence", ["N/A"]),
            acknowledged_risks=["Historical performance does not guarantee future results"]
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        messages = []
        my_op = context.my_previous_opinion
        if my_op and my_op.score < -20: # اگر تاریخچه بد است
            for name, op in context.other_agents_latest_opinions.items():
                if op.signal != SignalType.NEUTRAL and op.signal != SignalType.SELL if my_op.score < 0 else SignalType.BUY:
                    messages.append(DebateMessage(
                        message_id="", sender=self.name, target=name,
                        message_type=MessageType.CRITIQUE,
                        content=f"Memory warns: Similar setups in the past resulted in losses ({my_op.key_evidence[0]}). Reduce conviction.",
                        evidence=my_op.key_evidence, confidence=0.85, round_number=1
                    ))
        return messages

    def revise_opinion(self, context: DiscussionContext) -> AgentOpinion:
        return AgentOpinion(
            agent_name=self.name, round_number=2, signal=context.my_previous_opinion.signal,
            confidence=context.my_previous_opinion.confidence, score=context.my_previous_opinion.score,
            reasoning=context.my_previous_opinion.reasoning, key_evidence=context.my_previous_opinion.key_evidence,
            acknowledged_risks=context.my_previous_opinion.acknowledged_risks, changed_from_previous=False
        )