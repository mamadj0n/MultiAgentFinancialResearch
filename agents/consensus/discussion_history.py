#!/usr/bin/env python3
"""Discussion History Storage for Consensus Room"""

import json
import os
from datetime import datetime
from typing import Optional
from dataclasses import asdict

from ..agent_architecture_core import DiscussionHistory, DebateMessage, AgentOpinion, SignalType, AgentOutput


class DiscussionHistoryStore:
    """
    Persists DiscussionHistory to disk (JSON).
    
    In production, this could be swapped for PostgreSQL, Redis, or a vector DB.
    """
    
    def __init__(self, base_path: str = "./data/consensus_history"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
    
    def _session_file(self, session_id: str) -> str:
        return os.path.join(self.base_path, f"{session_id}.json")
    
    def save(self, history: DiscussionHistory) -> None:
        """Serialize and save DiscussionHistory to JSON."""
        filepath = self._session_file(history.session_id)
        
        # Convert to serializable dict
        data = {
            "session_id": history.session_id,
            "symbol": history.symbol,
            "start_time": history.start_time.isoformat(),
            "end_time": history.end_time.isoformat() if history.end_time else None,
            "rounds": {
                str(k): [self._message_to_dict(m) for m in v]
                for k, v in history.rounds.items()
            },
            "opinions": {
                name: [self._opinion_to_dict(op) for op in ops]
                for name, ops in history.opinions.items()
            },
            "conflict_map": history.conflict_map,
            "final_decision": self._agent_output_to_dict(history.final_decision) if history.final_decision else None,
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load(self, session_id: str) -> Optional[DiscussionHistory]:
        """Load DiscussionHistory from JSON."""
        filepath = self._session_file(session_id)
        if not os.path.exists(filepath):
            return None
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return self._deserialize(data)
    
    def list_sessions(self, limit: int = 50) -> list:
        """List recent session IDs."""
        files = sorted(
            [f for f in os.listdir(self.base_path) if f.endswith('.json')],
            key=lambda f: os.path.getmtime(os.path.join(self.base_path, f)),
            reverse=True
        )
        return [f[:-5] for f in files[:limit]]
    
    def _message_to_dict(self, msg: DebateMessage) -> dict:
        d = asdict(msg)
        d['message_type'] = msg.message_type.value
        d['timestamp'] = msg.timestamp.isoformat()
        return d
    
    def _opinion_to_dict(self, op: AgentOpinion) -> dict:
        d = asdict(op)
        d['signal'] = op.signal.value
        return d
    
    def _agent_output_to_dict(self, out: AgentOutput) -> dict:
        d = asdict(out)
        d['signal'] = out.signal.value
        d['timestamp'] = out.timestamp.isoformat()
        return d
    
    def _deserialize(self, data: dict) -> DiscussionHistory:
        history = DiscussionHistory(
            session_id=data["session_id"],
            symbol=data["symbol"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data["end_time"] else None,
        )
        
        # Deserialize rounds
        for round_str, messages in data.get("rounds", {}).items():
            round_num = int(round_str)
            history.rounds[round_num] = [
                DebateMessage(
                    message_id=m["message_id"],
                    sender=m["sender"],
                    target=m["target"],
                    message_type=MessageType(m["message_type"]),
                    content=m["content"],
                    evidence=m["evidence"],
                    confidence=m["confidence"],
                    round_number=m["round_number"],
                    timestamp=datetime.fromisoformat(m["timestamp"]),
                    in_reply_to=m.get("in_reply_to"),
                    metadata=m.get("metadata", {}),
                )
                for m in messages
            ]
        
        # Deserialize opinions
        for name, opinions in data.get("opinions", {}).items():
            history.opinions[name] = [
                AgentOpinion(
                    agent_name=o["agent_name"],
                    round_number=o["round_number"],
                    signal=SignalType(o["signal"]),
                    confidence=o["confidence"],
                    score=o["score"],
                    reasoning=o["reasoning"],
                    key_evidence=o.get("key_evidence", []),
                    acknowledged_risks=o.get("acknowledged_risks", []),
                    changed_from_previous=o.get("changed_from_previous", False),
                    change_reason=o.get("change_reason"),
                )
                for o in opinions
            ]
        
        history.conflict_map = data.get("conflict_map", [])
        
        # Deserialize final decision
        if data.get("final_decision"):
            fd = data["final_decision"]
            history.final_decision = AgentOutput(
                agent_name=fd["agent_name"],
                signal=SignalType(fd["signal"]),
                confidence=fd["confidence"],
                score=fd["score"],
                reasons=fd["reasons"],
                metadata=fd.get("metadata", {}),
                execution_time_ms=fd.get("execution_time_ms", 0.0),
                timestamp=datetime.fromisoformat(fd["timestamp"]),
            )
        
        return history


# Need to import MessageType for deserialization
from ..agent_architecture_core import MessageType