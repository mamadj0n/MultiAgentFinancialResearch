#!/usr/bin/env python3
"""LLM Supervisor Agent - Final decision synthesis using LLM"""

import time
import json
from typing import Any, Dict, List, Optional

from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, SharedLLMEngine,
    DiscussingAgent, DiscussionContext, AgentOpinion, DebateMessage, DiscussionHistory
)


class LLMSupervisorAgent(BaseAgent):
    """LLM-based supervisor that synthesizes all agent opinions into final decision."""

    def __init__(self, llm_engine: Optional[SharedLLMEngine] = None) -> None:
        super().__init__(name="LLMSupervisorAgent")
        self.llm_engine = llm_engine or SharedLLMEngine()

    def validate(self, context: MarketContext) -> bool:
        # Supervisor can work with just sub-agent outputs in metadata
        outputs = context.metadata.get("sub_agent_outputs")
        return isinstance(outputs, list) and len(outputs) > 0

    def analyze(self, context: MarketContext) -> AgentOutput:
        """Legacy method for backward compatibility - uses sub_agent_outputs from metadata."""
        sub_outputs = context.metadata.get("sub_agent_outputs", [])
        return self.synthesize_and_decide(context, sub_outputs)

    def synthesize_and_decide(
        self,
        context: MarketContext,
        agent_outputs: List[AgentOutput],
        conflict_map: Optional[List[Dict]] = None,
        full_history: Optional[DiscussionHistory] = None,
    ) -> AgentOutput:
        """Synthesize agent outputs into final decision using LLM."""
        start_time = time.time()

        if not agent_outputs:
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["No agent outputs to synthesize"],
            )

        # Build prompt for LLM
        prompt = self._build_synthesis_prompt(context, agent_outputs, conflict_map, full_history)
        system_prompt = self._get_system_prompt()

        # Get LLM response
        llm_response = self.llm_engine.generate(prompt, system_prompt)
        
        # Parse LLM response
        decision = self._parse_llm_response(llm_response, agent_outputs)

        execution_time = (time.time() - start_time) * 1000
        decision.execution_time_ms = round(execution_time, 2)

        return decision

    def _get_system_prompt(self) -> str:
        return """

        You are a seasoned Chief Investment Officer (CIO) at a top-tier crypto hedge fund, known for deep quantitative rigor, macro awareness, and risk-managed execution.
        You will receive analysis, signals, and critiques from your specialist agents (Technical, Macro, Fundamental, Risk, Sentiment).

        YOUR CORE OBJECTIVE:
        Perform a deep, comprehensive synthesis of all incoming agent inputs. Instead of a surface-level summary, evaluate the nuance, edge cases, inter-disciplinary correlations, and tail risks before finalizing the investment thesis.

        YOUR ANALYTICAL PROCESS:
        1. Multi-Dimensional Synthesis: Evaluate how agents' inputs interact. (e.g., How does high inflation/Macro impact a bullish Technical setup? How does Sentiment amplification affect Fundamental value?)
        2. Conflict & Edge Resolution: Deeply inspect conflicting signals. Identify which agent holds the asymmetrical insight or tail risk for the current market regime. 
        3. Risk-Adjusted Scoring & Sizing: Calculate the final score and position sizing strictly through the lens of capital preservation. Factor in black-swan risks, liquidity constraints, and conflict severity.
        4. Rules & Constraints: Respect any strict CONSENSUS RULE (e.g., forced NEUTRAL due to critical conflicts), but ensure your synthesis explicitly details the mechanic of this compromise.

        OUTPUT FORMAT REQUIREMENTS:
        - Output strictly valid JSON.
        - Maintain the EXACT JSON structure defined below.
        - Ensure the array elements in "reasons" and the string in "risk_notes" provide comprehensive, high-density, and institutional-grade analysis (no generic or vague statements).

        Strictly output ONLY valid JSON using this structure:
        {
        "signal": "BUY|SELL|NEUTRAL",
        "score": -100 to +100,
        "confidence": 0.0 to 1.0,
        "reasons": [
            "Comprehensive driver 1: Deep quantitative/macro synthesis detailing primary thesis",
            "Comprehensive driver 2: Conflict resolution mechanism explaining how cross-agent friction was reconciled"
        ],
        "position_size_pct": 0.0 to 1.0,
        "risk_notes": "Comprehensive breakdown of critical risks, tail-event vulnerabilities, and key friction points impacting sizing or signals"
        }
            """

    def _build_synthesis_prompt(
        self,
        context: MarketContext,
        agent_outputs: List[AgentOutput],
        conflict_map: Optional[List[Dict]] = None,
        full_history: Optional[DiscussionHistory] = None,
    ) -> str:
        """Build a detailed prompt for the LLM to synthesize agent outputs."""        
        # شمارش آرا برای تعیین اکثریت (ایجنت ریسک مستثنی است چون همیشه NEUTRAL است)
        directional_agents = [o for o in agent_outputs if o.agent_name not in ["RiskAgent", "MemoryAgent"]]
        buy_count = sum(1 for o in directional_agents if o.signal == SignalType.BUY)
        sell_count = sum(1 for o in directional_agents if o.signal == SignalType.SELL)
        neutral_count = sum(1 for o in directional_agents if o.signal == SignalType.NEUTRAL)

        memory_agent = next((o for o in agent_outputs if o.agent_name == "MemoryAgent"), None)
        memory_adjustment = memory_agent.score if memory_agent else 0.0

        # ساخت قانون اکثریت برای LLM
        consensus_rule = "NO CLEAR MAJORITY (You decide based on confidence)."
        if buy_count >= 3:
            consensus_rule = f"BUY MAJORITY ({buy_count}/3). You MUST output signal: 'BUY'."
        elif sell_count >= 3:
            consensus_rule = f"SELL MAJORITY ({sell_count}/3). You MUST output signal: 'SELL'."
        elif neutral_count >= 3:
            consensus_rule = f"NEUTRAL MAJORITY ({neutral_count}/3). You MUST output signal: 'NEUTRAL'."

            
        lines = [
            f"SYMBOL: {context.symbol} ({context.timeframe})",
            f"CURRENT PRICE: {context.latest_bar.get('Close', 'N/A')}",
            #f"\n*** CONSENSUS RULE: {consensus_rule} ***\n",
            "AGENT ANALYSES:",
        ]

        if memory_agent:
            lines.append(f"\n*** MEMORY ADJUSTMENT FACTOR: {memory_adjustment} ***")
            lines.append(f"Memory Reason: {memory_agent.reasons[0] if memory_agent.reasons else 'N/A'}")
            lines.append("Note: Apply this adjustment factor to the final score based on historical performance.")

        if conflict_map:
            lines.append("\nCONFLICTS DETECTED:")
            for c in conflict_map:
                lines.append(f"- {c['summary']} (Severity: {c['severity']})")
        
        # 🛠️ اضافه کردن متن بحث‌ها (Debate Messages) به پرامپت
        if full_history and full_history.rounds.get(1):
            lines.append("\nAGENT DEBATE TRANSCRIPT (Round 1 Critiques):")
            for msg in full_history.rounds[1]:
                target = msg.target if msg.target else "All"
                lines.append(f"- {msg.sender} to {target}: {msg.content}")
        
        # بررسی اینکه آیا کسی در راند 2 نظرش را عوض کرده است
        if full_history and full_history.opinions:
            lines.append("\nOPINION CHANGES (Round 2):")
            for agent_name, opinions in full_history.opinions.items():
                if len(opinions) > 1:
                    first = opinions[0]
                    last = opinions[-1]
                    if first.signal != last.signal or abs(first.confidence - last.confidence) > 0.1:
                        lines.append(f"- {agent_name}: Changed from {first.signal.value} to {last.signal.value}. Reason: {last.change_reason}")
                        
        lines.append(f"\n\n*** CONSENSUS RULE: {consensus_rule} ***\n")

        # تحلیل هر ایجنت
        for out in agent_outputs:
            lines.append(f"\n--- {out.agent_name} ---")
            lines.append(f"Signal: {out.signal.value}")
            lines.append(f"Score: {out.score:.1f}")
            lines.append(f"Confidence: {out.confidence:.0%}")
            lines.append(f"Reasons: {', '.join(out.reasons)}")
        
        if conflict_map:
            lines.append("\nCONFLICTS DETECTED:")
            for c in conflict_map:
                lines.append(f"- {c['summary']} (Severity: {c['severity']})")
        
        # 🛠️ اضافه کردن متن بحث‌ها به پرامپت سوپروایزر
        if full_history and full_history.rounds.get(1):
            lines.append("\nAGENT DEBATE TRANSCRIPT (Round 1):")
            for msg in full_history.rounds[1]:
                target = msg.target if msg.target else "All"
                lines.append(f"- {msg.sender} to {target}: {msg.content}")
                
        if full_history and full_history.opinions:
            lines.append("\nOPINION CHANGES (Round 2):")
            for agent_name, opinions in full_history.opinions.items():
                if len(opinions) > 1:
                    first = opinions[0]
                    last = opinions[-1]
                    if first.signal != last.signal or abs(first.confidence - last.confidence) > 0.1:
                        lines.append(f"- {agent_name}: Changed from {first.signal.value} to {last.signal.value}. Reason: {last.change_reason}")
        
        lines.append("\n\nProvide your final JSON.")
        return "\n".join(lines)

    def _parse_llm_response(self, response: str, agent_outputs: List[AgentOutput]) -> AgentOutput:
        """Parse LLM JSON response, fallback to weighted average if parsing fails."""
        try:

            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
                
            data = json.loads(clean_response.strip())
            signal = SignalType(data.get("signal", "NEUTRAL"))
            score = float(data.get("score", 0))
            
            # 🛠️ نرمال‌سازی کانفیدنس بین 0 و 1
            confidence = float(data.get("confidence", 0.5))
            if confidence > 1.0:
                confidence = confidence / 100.0  # تبدیل 85.0 به 0.85
                
            reasons = data.get("reasons", ["LLM synthesis"])
            position_size = float(data.get("position_size_pct", 0.5))
            risk_notes = data.get("risk_notes", "")
            
            # اطمینان از اینکه position_size هم بین 0 و 1 باشد
            if position_size > 1.0:
                position_size = position_size / 100.0
                
            all_reasons = reasons + ([f"Risk: {risk_notes}"] if risk_notes else [])
            
            return AgentOutput(
                agent_name=self.name,
                signal=signal,
                confidence=confidence,
                score=score,
                reasons=all_reasons,
                metadata={"position_size_pct": position_size, "llm_synthesis": True},
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Fallback: weighted average by confidence
            return self._fallback_synthesis(agent_outputs)

    def _fallback_synthesis(self, agent_outputs: List[AgentOutput]) -> AgentOutput:
        """Weighted average synthesis when LLM fails."""
        total_weight = sum(out.confidence for out in agent_outputs)
        if total_weight == 0:
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["Fallback: no confidence weights"],
            )
        
        weighted_score = sum(out.score * out.confidence for out in agent_outputs) / total_weight
        avg_confidence = sum(out.confidence for out in agent_outputs) / len(agent_outputs)
        
        # Signal from weighted score
        if weighted_score >= 15:
            signal = SignalType.BUY
        elif weighted_score <= -15:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL
        
        reasons = [f"Weighted synthesis of {len(agent_outputs)} agents (LLM unavailable)"]
        for out in agent_outputs:
            reasons.append(f"{out.agent_name}: {out.signal.value} ({out.score:.0f}, {out.confidence:.0%})")
        
        return AgentOutput(
            agent_name=self.name,
            signal=signal,
            confidence=round(avg_confidence, 2),
            score=round(weighted_score, 1),
            reasons=reasons,
            metadata={"fallback": True},
        )


# Also keep the DiscussingAgent version for consensus room
class LLMSupervisorDiscussingAgent(LLMSupervisorAgent, DiscussingAgent):
    """LLM Supervisor that participates in consensus room."""

    def analyze_independent(self, context: DiscussionContext) -> AgentOpinion:
        legacy_output = self.analyze(context.market_context)
        return AgentOpinion(
            agent_name=self.name,
            round_number=0,
            signal=legacy_output.signal,
            confidence=legacy_output.confidence,
            score=legacy_output.score,
            reasoning=legacy_output.reasons,
            key_evidence=[f"Synthesized from {len(context.other_agents_latest_opinions)} agents"],
            acknowledged_risks=["LLM may hallucinate", "Synthesis quality depends on input quality"],
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        # Supervisor doesn't critique in round 1, it decides in round 3
        return []

    def revise_opinion(self, context: DiscussionContext) -> AgentOpinion:
        # Supervisor doesn't revise, it makes final decision
        return self.analyze_independent(context)