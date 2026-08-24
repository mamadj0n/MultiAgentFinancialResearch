#!/usr/bin/env python3
"""Conflict Detector - Automated disagreement analysis between agents"""

from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

from ..agent_architecture_core import AgentOpinion, SignalType


class ConflictDetector:
    """
    Automatically detects and structures disagreements between agents.
    
    Produces conflict_map for Supervisor and DiscussionContext.
    """
    
    def __init__(self, similarity_threshold: float = 0.3):
        self.similarity_threshold = similarity_threshold
    
    def detect_conflicts(self, opinions: Dict[str, AgentOpinion]) -> List[Dict[str, Any]]:
        conflicts = []
        agents = list(opinions.items())
        
        for i, (name_a, op_a) in enumerate(agents):
            for name_b, op_b in agents[i+1:]:
                conflict = self._analyze_pair(name_a, op_a, name_b, op_b)
                if conflict:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _analyze_pair(
        self, name_a: str, op_a: AgentOpinion, name_b: str, op_b: AgentOpinion
    ) -> Optional[Dict[str, Any]]:
        """Analyze disagreement between two agents."""
        
        # Signal conflict
        signal_conflict = self._signal_disagreement(op_a.signal, op_b.signal)
        
        # Confidence-weighted score difference
        score_diff = abs(op_a.score - op_b.score)
        weighted_diff = score_diff * ((op_a.confidence + op_b.confidence) / 2)
        
        # Reasoning overlap (semantic similarity)
        reason_similarity = self._reasoning_similarity(op_a.reasoning, op_b.reasoning)
        
        # Evidence contradiction
        evidence_conflict = self._evidence_contradiction(op_a.key_evidence, op_b.key_evidence)
        
        # Only report if meaningful disagreement exists
        if not signal_conflict and weighted_diff < 15 and reason_similarity > 0.7:
            return None
        
        severity = self._calculate_severity(signal_conflict, weighted_diff, reason_similarity)
        
        return {
            "agent_a": name_a,
            "agent_b": name_b,
            "signal_a": op_a.signal.value,
            "signal_b": op_b.signal.value,
            "score_a": op_a.score,
            "score_b": op_b.score,
            "confidence_a": op_a.confidence,
            "confidence_b": op_b.confidence,
            "signal_conflict": signal_conflict,
            "score_difference": round(score_diff, 1),
            "weighted_difference": round(weighted_diff, 1),
            "reasoning_similarity": round(reason_similarity, 2),
            "evidence_conflict": evidence_conflict,
            "severity": severity,
            "summary": self._generate_summary(name_a, op_a, name_b, op_b, severity),
        }
    
    def _signal_disagreement(self, s1: SignalType, s2: SignalType) -> bool:
        if s1 == s2:
            return False
        if s1 == SignalType.NEUTRAL or s2 == SignalType.NEUTRAL:
            return True
        return s1 != s2  # BUY vs SELL
    
    def _reasoning_similarity(self, reasons_a: List[str], reasons_b: List[str]) -> float:
        if not reasons_a or not reasons_b:
            return 0.0
        max_sim = 0.0
        for ra in reasons_a:
            for rb in reasons_b:
                sim = SequenceMatcher(None, ra.lower(), rb.lower()).ratio()
                max_sim = max(max_sim, sim)
        return max_sim
    
    def _evidence_contradiction(self, ev_a: List[str], ev_b: List[str]) -> bool:
        # Simple heuristic: check for opposing keywords
        opposing = [
            ("bullish", "bearish"), ("buy", "sell"), ("long", "short"),
            ("oversold", "overbought"), ("support", "resistance"),
            ("low", "high"), ("weak", "strong"), ("dovish", "hawkish"),
        ]
        text_a = " ".join(ev_a).lower()
        text_b = " ".join(ev_b).lower()
        for pos, neg in opposing:
            if pos in text_a and neg in text_b:
                return True
            if neg in text_a and pos in text_b:
                return True
        return False
    
    def _calculate_severity(self, signal_conflict: bool, weighted_diff: float, reason_sim: float) -> str:
        if signal_conflict and weighted_diff > 40:
            return "CRITICAL"
        if signal_conflict or weighted_diff > 25:
            return "HIGH"
        if weighted_diff > 15 or reason_sim < 0.3:
            return "MEDIUM"
        return "LOW"
    
    def _generate_summary(self, name_a, op_a, name_b, op_b, severity) -> str:
        return (
            f"{name_a} ({op_a.signal.value}, {op_a.score:.0f}) vs "
            f"{name_b} ({op_b.signal.value}, {op_b.score:.0f}) — {severity}"
        )