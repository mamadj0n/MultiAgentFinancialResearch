#!/usr/bin/env python3
import os
import json
import time
import signal
import logging
import tempfile
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

import sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.config import COIN, TIME_FRAME, TP_MULTIPLIER, INITIAL_CAPITAL
from memory_store import MemoryStore
from utils.DataCollect import DataCollector
from utils.FeatureEngineer import FeatureEngineering
from agents.agent_architecture_core import MarketContext, AgentOutput, SignalType, SharedLLMEngine
from agents.technical_agent import TechnicalAgent
from agents.sentiment_agent import SentimentAgent
from agents.macro_agent import MacroAgent
from agents.fundamental_agent import FundamentalAgent
from agents.risk_agent import RiskAgent
from agents.llm_supervisor_agent import LLMSupervisorAgent
from agents.consensus.round_coordinator import RoundCoordinator
from agents.consensus.conflict_detector import ConflictDetector
from agents.memory_agent import MemoryAgent

# =====================================================================
# 1. تنظیمات لاگ‌گذاری روی دیسک
# =====================================================================
from utils.log_config import setup_logging
setup_logging("signal_bot.log")
logger = logging.getLogger(__name__)

# =====================================================================
# 2. تولیدکننده سیگنال (بدون اجرای ترید واقعی)
# =====================================================================
def _default_signals_file():
    # اولویت Render Disk
    if os.getenv("SIGNALS_FILE"):
        return os.getenv("SIGNALS_FILE")
    if os.path.exists("/app/data"):
        os.makedirs("/app/data", exist_ok=True)
        return "/app/data/signals_history.json"
    os.makedirs("data", exist_ok=True)
    # سازگاری با فایل قدیمی در ریشه
    if os.path.exists("signals_history.json") and not os.path.exists("data/signals_history.json"):
        return "signals_history.json"
    return "data/signals_history.json"

class SignalGenerator:
    def __init__(self, initial_capital: float = 1000.0, signals_file: str = None):
        if signals_file is None:
            signals_file = _default_signals_file()
        self.initial_capital = initial_capital
        self.signals_file = signals_file
        self.signals_history = []
        
        if os.path.exists(signals_file):
            self.load_signals()

    def load_signals(self):
        try:
            with open(self.signals_file, 'r') as f:
                self.signals_history = json.load(f)
            logger.info(f"[SignalGenerator] Loaded {len(self.signals_history)} past signals.")
        except Exception:
            self.signals_history = []

    def save_signals(self):
        dir_name = os.path.dirname(self.signals_file) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.signals_history, f, indent=4)
            os.replace(tmp_path, self.signals_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def generate_and_log_signal(self, final_decision: AgentOutput, outputs: List[AgentOutput], current_price: float, atr: float, timestamp: str) -> dict:
            signal_type = final_decision.signal
            
            # 1. اگر سیگنال HOLD بود، سریعاً خروجی خنثی برمی‌گردانیم
            if signal_type not in (SignalType.BUY, SignalType.SELL):
                logger.info(f"⏸️ [SIGNAL] HOLD. No action required. Reason: {final_decision.reasons[0] if final_decision.reasons else 'N/A'}")
                return {
                    "timestamp": timestamp,
                    "symbol": self.symbol,
                    "direction": "HOLD",
                    "supervisor_reason": final_decision.reasons[0] if final_decision.reasons else "N/A",
                    "supervisor_score": final_decision.score
                }

            # 2. استخراج تنظیمات مدیریت ریسک از ایجنت ریسک
            risk_output = next((o for o in outputs if o.agent_name == "RiskAgent"), None)
            risk_pct = risk_output.metadata.get("risk_pct", 0.02) if risk_output and hasattr(risk_output, 'metadata') else 0.02
            sl_mult = risk_output.metadata.get("sl_multiplier", 1.5) if risk_output and hasattr(risk_output, 'metadata') else 1.5

            # 3. محاسبه دقیق جزئیات سیگنال
            stop_distance = max(atr * sl_mult, current_price * 0.002)
            risk_amount = self.initial_capital * risk_pct
            position_size = risk_amount / stop_distance

            if signal_type == SignalType.BUY:
                entry_price = current_price
                stop_loss = current_price - stop_distance
                take_profit = current_price + (stop_distance * TP_MULTIPLIER)
                direction = "LONG 🟢"
            elif signal_type == SignalType.SELL:
                entry_price = current_price
                stop_loss = current_price + stop_distance
                take_profit = current_price - (stop_distance * TP_MULTIPLIER)
                direction = "SHORT 🔴"
            else:
                return {}

            rr_ratio = abs(take_profit - entry_price) / abs(entry_price - stop_loss)

            # ساخت و ذخیره سیگنال
            signal_data = {
                "timestamp": timestamp,
                "symbol": self.symbol,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "rr_ratio": rr_ratio,
                "position_size": position_size,
                "risk_pct": risk_pct,
                "supervisor_reason": final_decision.reasons[0] if final_decision.reasons else "N/A",
                "supervisor_score": final_decision.score,
                "tech_signal": next((o.signal.value for o in outputs if o.agent_name == "TechnicalAgent"), "N/A"),
                "macro_signal": next((o.signal.value for o in outputs if o.agent_name == "MacroAgent"), "N/A"),
                "sentiment": next((o.signal.value for o in outputs if o.agent_name == "SentimentAgent"), "N/A"),
                "fund_signal": next((o.signal.value for o in outputs if o.agent_name == "FundamentalAgent"), "N/A"),
                "tech_reason": next((o.reasons for o in outputs if o.agent_name == "TechnicalAgent"), "N/A"),
                "macro_reason": next((o.reasons for o in outputs if o.agent_name == "MacroAgent"), "N/A"),
                "sentiment_reason": next((o.reasons for o in outputs if o.agent_name == "SentimentAgent"), "N/A"),
                "fund_reason": next((o.reasons for o in outputs if o.agent_name == "FundamentalAgent"), "N/A"),
            }
            self.signals_history.append(signal_data)
            self.save_signals()
            return signal_data

# =====================================================================
# 3. ربات سیگنال‌دهی زنده (Live Signal Bot)
# =====================================================================
class LiveSignalBot:
    def __init__(self, symbol="BTC-USD", timeframe="15m"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.is_running = True
        
        logger.info("[System] Initializing Live Signal Bot...")
        self.collector = DataCollector(coin=symbol, live_data=True, time_frame=timeframe)
        self.memory_store = MemoryStore()
        
        # تولیدکننده سیگنال جایگزین Portfolio Manager شد
        self.signal_generator = SignalGenerator(initial_capital=INITIAL_CAPITAL)
        self.signal_generator.symbol = symbol 

        self.agents_dict = {
            "TechnicalAgent": TechnicalAgent(),
            "MacroAgent": MacroAgent(),
            "FundamentalAgent": FundamentalAgent(),
            "SentimentAgent": SentimentAgent(),
            "RiskAgent": RiskAgent(),
            "MemoryAgent": MemoryAgent(memory_store=self.memory_store)
        }
        
        self.conflict_detector = ConflictDetector()
        self.round_coordinator = RoundCoordinator(self.agents_dict, self.conflict_detector)
        self.supervisor = LLMSupervisorAgent()
        self.llm = SharedLLMEngine()

    def get_next_candle_delay(self) -> float:
        """محاسبه زمان تا بسته شدن کندل بعدی"""
        now = datetime.now(timezone.utc)
        minute = now.minute
        second = now.second
        
        if self.timeframe == "15m":
            minutes_to_close = 15 - (minute % 15)
            if minutes_to_close == 15 and second == 0:
                return 5  
            return (minutes_to_close * 60) - second + 5
        return 60

    @staticmethod
    def opinion_to_output(op) -> AgentOutput:
        return AgentOutput(
            agent_name=op.agent_name, signal=op.signal, confidence=op.confidence,
            score=op.score, reasons=op.reasoning, metadata={"evidence": op.key_evidence}
        )

    def run_cycle(self):
        timestamp_now = datetime.now(timezone.utc).isoformat()
        logger.info(f"\n{'='*50}\n[System] Fetching live data for {timestamp_now}")
        
        # 1. دریافت دیتا
        price_df, macro_df, news_df, onchain_df = self.collector.collect_data()
        if price_df.empty or len(price_df) < 200:
            logger.warning("Not enough data fetched. Skipping cycle.")
            return

        # 2. مهندسی ویژگی
        fe = FeatureEngineering(price_df=price_df, macro_df=macro_df)
        features_df = fe.process_all()

        features_df = features_df.dropna()
        if len(features_df) < 50: return

        current_bar = features_df.iloc[-1]
        current_price = current_bar["Close"]
        
        # 3. ساخت کانتکست
        context = MarketContext(
            symbol=self.symbol, timeframe=self.timeframe,
            features_df=features_df, raw_price_df=price_df,
            macro_df=macro_df, news_df=news_df, onchain_df=onchain_df,
            timestamp=timestamp_now
        )

        # 4. اجرای اتاق گفتگو (Consensus Room)
        logger.info("🧠 [CONSENSUS ROOM] Starting debate...")
        round_0 = self.round_coordinator.run_round_0_independent(context)
        for name, op in round_0.opinions.items():
            logger.info(f"[R0] {name}: {op.signal.value} (Score: {op.score:.1f}, Conf: {op.confidence:.0%}) \n {'-'*30}")
        
        round_1 = self.round_coordinator.run_round_1_critique(context, round_0.opinions)
        round_2 = self.round_coordinator.run_round_2_revision(context, round_0.opinions, round_1.messages)
        
        final_opinions = self.round_coordinator.get_final_opinions(round_2)
        outputs = [self.opinion_to_output(op) for op in final_opinions.values()]
        
        # 5. تصمیم نهایی سوپروایزر
        try:
            final_decision = self.supervisor.synthesize_and_decide(
                context=context, agent_outputs=outputs, 
                conflict_map=round_2.conflicts, full_history=None
            )
        except Exception as e:
            final_decision = self.supervisor._fallback_synthesis(outputs)
            
        logger.info(f"🧠 [SUPERVISOR] Final Decision: {final_decision.signal.value} | Score: {final_decision.score:.1f}")

        # 6. تولید و چاپ سیگنال (جایگزین بخش اجرای ترید)
        atr_value = current_bar.get("ATR_14", current_price * 0.02)
        return self.signal_generator.generate_and_log_signal(
            final_decision=final_decision,
            outputs=outputs,
            current_price=current_price,
            atr=atr_value,
            timestamp=timestamp_now
        )

    def generate_llm_summary(self):
        """تولید خلاصه هوشمند با LLM در زمان خروج"""
        prompt = f"""Summarize the performance of this crypto signal bot session in 3 bullet points:
        - Total Signals Generated: {len(self.signal_generator.signals_history)}
        - Last Signal Direction: {self.signal_generator.signals_history[-1]['direction'] if self.signal_generator.signals_history else 'N/A'}
        Provide a brief, encouraging, and analytical summary in Persian."""
        try:
            response = self.llm.generate(prompt, "You are a helpful trading assistant.")
            print("\n" + "="*50)
            print("🤖 LLM SESSION SUMMARY:")
            print("="*50)
            print(response)
        except Exception:
            pass

    def shutdown(self):
        self.is_running = False
        logger.info("\n[Shutdown] Stopping signal bot gracefully...")
        self.generate_llm_summary()
        logger.info(f"[Shutdown] Total signals generated this session: {len(self.signal_generator.signals_history)}")

    def run(self):
        logger.info(f"🚀 Signal Bot started. Waiting for next {self.timeframe} candle...")
        
        while self.is_running:
            try:
                delay = self.get_next_candle_delay()
                if delay > 10:
                    logger.info(f"[Sleep] Waiting {delay:.0f} seconds for next candle close...")
                
                for _ in range(int(delay)):
                    if not self.is_running: break
                    time.sleep(1)
                
                if self.is_running:
                    self.run_cycle()
                    
            except Exception as e:
                logger.error(f"[Error] Cycle failed: {e}")
                time.sleep(15)

if __name__ == "__main__":
    bot = LiveSignalBot(symbol=COIN, timeframe=TIME_FRAME)
    signal.signal(signal.SIGINT, lambda sig, frame: bot.shutdown())
    bot.run()