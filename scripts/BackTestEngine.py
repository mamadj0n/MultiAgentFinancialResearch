#!/usr/bin/env python3
import pandas as pd
import numpy as np
import time
from typing import List, Optional, Dict
import matplotlib.pyplot as plt
import pandas_ta as ta  # برای اضافه کردن اندیکاتورهای گمشده

# وارد کردن کلاس‌های اصلی
from utils.DataCollect import DataCollector
from utils.FeatureEngineer import FeatureEngineering
from agents.agent_architecture_core import (
    MarketContext, AgentOutput, SignalType, AgentOpinion, DiscussionHistory
)

# وارد کردن ایجنت‌ها
from agents.technical_agent import TechnicalAgent
from agents.macro_agent import MacroAgent
from agents.fundamental_agent import FundamentalAgent
from agents.sentiment_agent import SentimentAgent
from agents.llm_supervisor_agent import LLMSupervisorAgent
from agents.risk_agent import RiskAgent

# وارد کردن ماژول‌های اتاق گفتگو
from agents.consensus.round_coordinator import RoundCoordinator
from agents.consensus.conflict_detector import ConflictDetector


# ------------------------------------------------------------------
# 1. لاگ‌گر زیبا
# ------------------------------------------------------------------
class ConsensusLogger:
    COLORS = {
        "HEADER": "\033[95m", "BLUE": "\033[94m", "CYAN": "\033[96m",
        "GREEN": "\033[92m", "YELLOW": "\033[93m", "RED": "\033[91m",
        "RESET": "\033[0m", "BOLD": "\033[1m",
    }

    @staticmethod
    def log_separator(title: str):
        line = "=" * 60
        print(f"\n{ConsensusLogger.COLORS['HEADER']}{ConsensusLogger.COLORS['BOLD']}{line}")
        print(f" {title} ".center(60, '='))
        print(f"{line}{ConsensusLogger.COLORS['RESET']}\n")

    @staticmethod
    def log_round(round_num: int, title: str):
        print(f"\n{ConsensusLogger.COLORS['CYAN']}{ConsensusLogger.COLORS['BOLD']}--- ROUND {round_num}: {title} ---{ConsensusLogger.COLORS['RESET']}")

    @staticmethod
    def log_opinion(agent_name: str, opinion: AgentOpinion):
        color = ConsensusLogger.COLORS["GREEN"] if opinion.signal == SignalType.BUY else (
                ConsensusLogger.COLORS["RED"] if opinion.signal == SignalType.SELL else ConsensusLogger.COLORS["YELLOW"])
        print(f"{ConsensusLogger.COLORS['BOLD']}[{agent_name}]{ConsensusLogger.COLORS['RESET']} -> "
              f"Signal: {color}{opinion.signal.value}{ConsensusLogger.COLORS['RESET']} | "
              f"Score: {opinion.score:.1f} | Conf: {opinion.confidence:.0%}")
        if opinion.reasoning:
            print(f"  Reasons: {' | '.join(opinion.reasoning[:2])}")
        
    @staticmethod
    def log_critique(sender: str, target: str, content: str, confidence: float):
        print(f"  {ConsensusLogger.COLORS['YELLOW']}💬 [{sender} ➡ {target}] (Conf: {confidence:.0%}){ConsensusLogger.COLORS['RESET']}")
        print(f"     \"{content}\"")

    @staticmethod
    def log_revision(agent_name: str, prev: AgentOpinion, new: AgentOpinion):
        if new.changed_from_previous:
            print(f"  {ConsensusLogger.COLORS['BLUE']}🔄 [{agent_name}] Changed Opinion!{ConsensusLogger.COLORS['RESET']}")
            print(f"     Old: {prev.signal.value} ({prev.score:.1f}) --> New: {new.signal.value} ({new.score:.1f})")
            print(f"     Reason: {new.change_reason}")
        else:
            print(f"  {ConsensusLogger.COLORS['GREEN']}✅ [{agent_name}] Maintains position: {new.signal.value}{ConsensusLogger.COLORS['RESET']}")

    @staticmethod
    def log_conflicts(conflicts: List[Dict]):
        if not conflicts: return
        print(f"\n{ConsensusLogger.COLORS['RED']}⚔️ CONFLICTS DETECTED:{ConsensusLogger.COLORS['RESET']}")
        for c in conflicts:
            print(f"  - {c['summary']}")

# ------------------------------------------------------------------
# 2. مدیریت سرمایه
# ------------------------------------------------------------------
class PortfolioManager:
    def __init__(self, initial_capital: float = 10000.0, risk_per_trade: float = 0.02):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.risk_per_trade = risk_per_trade
        self.position = 0.0
        self.entry_price = 0.0
        self.position_size = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.trade_history = []
        self.equity_curve = []

    def open_position(self, signal: SignalType, current_price: float, atr: float):
        if self.position != 0: return
        risk_amount = self.balance * self.risk_per_trade
        stop_distance = max(atr * 1.5, current_price * 0.01)
        self.position_size = risk_amount / stop_distance
        if signal == SignalType.BUY:
            self.position = 1
            self.entry_price = current_price
            self.stop_loss = current_price - stop_distance
            self.take_profit = current_price + (stop_distance * 2)
        elif signal == SignalType.SELL:
            self.position = -1
            self.entry_price = current_price
            self.stop_loss = current_price + stop_distance
            self.take_profit = current_price - (stop_distance * 2)

    def close_position(self, current_price: float, reason: str = "Signal Reversal"):
        if self.position == 0: return
        pnl = (current_price - self.entry_price) * self.position_size if self.position == 1 else (self.entry_price - current_price) * self.position_size
        self.balance += pnl
        self.trade_history.append({"PnL": pnl, "Reason": reason, "Balance": self.balance})
        self.position = 0
        self.entry_price = 0.0
        self.position_size = 0.0

    def update_equity(self, current_price: float, timestamp: pd.Timestamp):
        unrealized = 0
        if self.position == 1: unrealized = (current_price - self.entry_price) * self.position_size
        elif self.position == -1: unrealized = (self.entry_price - current_price) * self.position_size
        self.equity_curve.append({"timestamp": timestamp, "equity": self.balance + unrealized})

# ------------------------------------------------------------------
# 3. موتور بک‌تست
# ------------------------------------------------------------------
class ConsensusBacktester:
    def __init__(self, symbol: str = "BTC-USD", timeframe: str = "1d", start_time: str = "2023-06-01", end_time: str = "2024-01-01" , STEP: int = 7):
        self.symbol = symbol
        self.timeframe = timeframe
        self.STEP = STEP

        self.collector = DataCollector(coin=symbol, live_data=False, time_frame=timeframe)
        self.agents_dict = {
            "TechnicalAgent": TechnicalAgent(),
            "MacroAgent": MacroAgent(),
            "FundamentalAgent": FundamentalAgent(),
            "RiskAgent": RiskAgent(),
            #"SentimentAgent": SentimentAgent()
        }
        self.conflict_detector = ConflictDetector()
        self.round_coordinator = RoundCoordinator(self.agents_dict, self.conflict_detector)
        self.supervisor = LLMSupervisorAgent()
        self.portfolio = PortfolioManager(initial_capital=10000)

    @staticmethod
    def opinion_to_output(op: AgentOpinion) -> AgentOutput:
        return AgentOutput(
            agent_name=op.agent_name, signal=op.signal, confidence=op.confidence,
            score=op.score, reasons=op.reasoning, metadata={"evidence": op.key_evidence}
        )

    def run(self):
        print("\n[System] Fetching Data...")
        price_df, macro_df, news_df , onchain_df = self.collector.collect_data()
        
        print("[System] Engineering Features...")
        fe = FeatureEngineering(price_df=price_df, macro_df=macro_df)

        features_df = fe.process_all()
            
        features_df = features_df.loc[:, features_df.isna().mean() < 0.5]
        features_df = features_df.dropna(axis=1, how='all')
        features_df = features_df.dropna()
        
        step = self.STEP 
        print(f"[System] Starting Backtest. Total periods: {len(features_df)} (Step: {step})")
        
        if len(features_df) < 50:
            print("❌ Error: Not enough data.")
            return
            
        for i in range(50, len(features_df), step):
            current_features = features_df.iloc[:i+1]
            current_bar = current_features.iloc[-1]
            current_time = current_features.index[-1]
            current_price = current_bar["Close"]
            
            if self.portfolio.position == 1 and current_bar["Low"] <= self.portfolio.stop_loss:
                self.portfolio.close_position(self.portfolio.stop_loss, "Stop Loss")
            elif self.portfolio.position == -1 and current_bar["High"] >= self.portfolio.stop_loss:
                self.portfolio.close_position(self.portfolio.stop_loss, "Stop Loss")
                
            self.portfolio.update_equity(current_price, current_time)
            
            context = MarketContext(
                symbol=self.symbol, timeframe=self.timeframe,
                features_df=current_features, raw_price_df=price_df.loc[:current_time],
                macro_df=macro_df.loc[:current_time] if macro_df is not None else None,
                onchain_df=onchain_df.loc[:current_time] if onchain_df is not None else None,   
                news_df=news_df, timestamp=current_time
            )
            
            ConsensusLogger.log_separator(f"CONSENSUS ROOM | {current_time} | Price: ${current_price:.2f}")
            
            ConsensusLogger.log_round(0, "Independent Analysis")
            round_0 = self.round_coordinator.run_round_0_independent(context)
            for name, op in round_0.opinions.items():
                ConsensusLogger.log_opinion(name, op)
            ConsensusLogger.log_conflicts(round_0.conflicts)
            
            ConsensusLogger.log_round(1, "Critique Exchange")
            round_1 = self.round_coordinator.run_round_1_critique(context, round_0.opinions)
            for msg in round_1.messages:
                ConsensusLogger.log_critique(msg.sender, msg.target or "All", msg.content, msg.confidence)
                
            ConsensusLogger.log_round(2, "Opinion Revision")
            round_2 = self.round_coordinator.run_round_2_revision(context, round_0.opinions, round_1.messages)
            for name, new_op in round_2.opinions.items():
                ConsensusLogger.log_revision(name, round_0.opinions[name], new_op)
            
            ConsensusLogger.log_round(3, "Supervisor Decision")
            final_opinions = self.round_coordinator.get_final_opinions(round_2)
            outputs = [self.opinion_to_output(op) for op in final_opinions.values()]
            
            try:
                final_decision = self.supervisor.synthesize_and_decide(
                    context=context, agent_outputs=outputs, 
                    conflict_map=round_2.conflicts, full_history=None
                )
            except Exception:
                final_decision = self.supervisor._fallback_synthesis(outputs)
                
            color = ConsensusLogger.COLORS["GREEN"] if final_decision.signal == SignalType.BUY else ConsensusLogger.COLORS["RED"]
            print(f"\n{ConsensusLogger.COLORS['BOLD']}🧠 SUPERVISOR FINAL DECISION:{ConsensusLogger.COLORS['RESET']}")
            print(f"   Signal: {color}{final_decision.signal.value}{ConsensusLogger.COLORS['RESET']} | Score: {final_decision.score:.1f} | Conf: {final_decision.confidence:.0%}")
            print(f"   Reason: {final_decision.reasons[0] if final_decision.reasons else 'N/A'}")
            
            if final_decision.signal == SignalType.BUY and self.portfolio.position <= 0:
                if self.portfolio.position == -1: self.portfolio.close_position(current_price, "Reverse to Long")
                self.portfolio.open_position(SignalType.BUY, current_price, current_bar.get("ATR_14", current_price*0.02))
            elif final_decision.signal == SignalType.SELL and self.portfolio.position >= 0:
                if self.portfolio.position == 1: self.portfolio.close_position(current_price, "Reverse to Short")
                self.portfolio.open_position(SignalType.SELL, current_price, current_bar.get("ATR_14", current_price*0.02))

        if self.portfolio.position != 0:
            self.portfolio.close_position(features_df.iloc[-1]["Close"], "Backtest Ended")
            
        self._generate_report()

    def _generate_report(self):
        if not self.portfolio.trade_history:
            print("\nNo trades executed.")
            return
            
        df_trades = pd.DataFrame(self.portfolio.trade_history)
        df_equity = pd.DataFrame(self.portfolio.equity_curve).set_index("timestamp")
        
        total_pnl = df_trades["PnL"].sum()
        win_rate = (df_trades["PnL"] > 0).mean() * 100
        max_dd = ((df_equity["equity"].cummax() - df_equity["equity"]) / df_equity["equity"].cummax()).max() * 100
        
        print("\n" + "="*50)
        print("📊 BACKTEST PERFORMANCE REPORT")
        print("="*50)
        print(f"Initial Capital:   ${self.portfolio.initial_capital:,.2f}")
        print(f"Final Balance:     ${self.portfolio.balance:,.2f}")
        print(f"Total Net PnL:     ${total_pnl:,.2f}")
        print(f"Total Trades:      {len(df_trades)}")
        print(f"Win Rate:          {win_rate:.2f}%")
        print(f"Max Drawdown:      {max_dd:.2f}%")
        print("="*50 + "\n")
        
        plt.figure(figsize=(12, 6))
        plt.plot(df_equity.index, df_equity["equity"], label="Equity Curve", color="blue")
        plt.title("Portfolio Equity Curve")
        plt.xlabel("Time")
        plt.ylabel("Balance ($)")
        plt.grid(True)
        plt.show()

if __name__ == "__main__":
    backtester = ConsensusBacktester(
        symbol="BTC-USD",
        timeframe="1d",
        start_time="2021-06-01",  # <--- از ۲.۵ سال قبل شروع کن
        end_time="2024-01-01"
    )
    backtester.run()