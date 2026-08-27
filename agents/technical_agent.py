import time
import json
import pandas as pd
from typing import Any, Dict, List, Optional

from .agent_architecture_core import (
    BaseAgent, AgentOutput, SignalType, MarketContext, DiscussingAgent,
    DiscussionContext, AgentOpinion, DebateMessage, MessageType, RoundType, SharedLLMEngine
)
from utils.config import TECH_BUY_THRESHOLD, TECH_SELL_THRESHOLD


class TechnicalAgent(DiscussingAgent):
    """
    Advanced Strict Trend-Following Technical Analysis Agent.
    ABSOLUTE PRIORITY: Market Macro Trend (EMA200 + Ichimoku).
    Counter-trend signals are strictly prohibited at both Prompt and Code levels.
    """

    def __init__(self, llm_engine: Optional[SharedLLMEngine] = None) -> None:
        super().__init__(name="TechnicalAgent")
        self.llm_engine = llm_engine or SharedLLMEngine()

    def validate(self, context: MarketContext) -> bool:
        required_cols = [
            "Close", "High", "Low", "EMA_200", "ADX_14", "RSI_14",
            "BOS", "Volume_Ratio", "ATR_14"
        ]
        return all(col in context.features_df.columns for col in required_cols)

    def _extract_cascading_technical_state(self, latest: pd.Series) -> str:
        """Extracts technical metrics structured into 5 Cascading Layers."""
        state_lines = []

        close = latest["Close"]
        high = latest.get("High", close)
        low = latest.get("Low", close)
        ema200 = latest.get("EMA_200", close)
        senkou_a = latest.get("Senkou_Span_A", close)
        senkou_b = latest.get("Senkou_Span_B", close)
        adx = latest.get("ADX_14", 15)

        # --- LAYER 1: Macro Trend & Ichimoku Regime Filter ---
        cloud_top = max(senkou_a, senkou_b) if pd.notna(senkou_a) and pd.notna(senkou_b) else close
        cloud_bottom = min(senkou_a, senkou_b) if pd.notna(senkou_a) and pd.notna(senkou_b) else close

        if close > ema200 and close > cloud_top:
            macro_regime = "STRONG BULLISH (Above EMA200 & Above Ichimoku Cloud)"
        elif close < ema200 and close < cloud_bottom:
            macro_regime = "STRONG BEARISH (Below EMA200 & Below Ichimoku Cloud)"
        elif adx < 20:
            macro_regime = "RANGING / SIDEWAYS (ADX < 20)"
        else:
            macro_regime = "TRANSITIONAL / MIXED (Conflicting Cloud & EMA200 signals)"

        state_lines.append(f"1. MACRO & ICHIMOKU REGIME: {macro_regime} (ADX: {adx:.1f})")

        # --- LAYER 2: Market Structure & SMC / ICT Setup ---
        bos = latest.get("BOS", 0)
        sweep = latest.get("Liquidity_Sweep", 0)
        fvg = latest.get("FVG_Signal", 0)
        trend_dir = latest.get("Trend_Direction", 0)

        smc_triggers = []
        if sweep == -1:
            smc_triggers.append("Bullish Liquidity Sweep (Low-hunt Fakeout)")
        elif sweep == 1:
            smc_triggers.append("Bearish Liquidity Sweep (High-hunt Fakeout)")

        if bos == 1:
            smc_triggers.append("Bullish BOS (Break of Structure)")
        elif bos == -1:
            smc_triggers.append("Bearish BOS (Break of Structure)")

        if fvg == 1:
            smc_triggers.append("Price inside Bullish Fair Value Gap (FVG)")
        elif fvg == -1:
            smc_triggers.append("Price inside Bearish Fair Value Gap (FVG)")

        smc_str = " | ".join(smc_triggers) if smc_triggers else "No major SMC trigger"
        state_lines.append(f"2. SMC STRUCTURE & LIQUIDITY: {smc_str} (Trend Direction: {trend_dir})")

        # --- LAYER 3: Volume & Money Flow Confirmation ---
        vol_ratio = latest.get("Volume_Ratio", 1.0)
        cmf = latest.get("CMF", 0.0)
        macd_hist = latest.get("MACD_Hist", 0.0)
        rsi = latest.get("RSI_14", 50)

        volume_status = "High Volume" if vol_ratio >= 1.3 else ("Extreme Volume" if vol_ratio >= 1.8 else "Low Volume")
        cmf_status = "Institutional Accumulation" if cmf > 0.05 else ("Institutional Distribution" if cmf < -0.05 else "Neutral Money Flow")

        state_lines.append(
            f"3. VOLUME & MONEY FLOW: Vol Ratio: {vol_ratio:.2f}x ({volume_status}) | "
            f"CMF: {cmf:.3f} ({cmf_status}) | RSI: {rsi:.1f} | MACD Hist: {macd_hist:.4f}"
        )

        # --- LAYER 4: Session & Volatility Compression ---
        session = latest.get("Session", "Unknown")
        bb_width = latest.get("BB_Width", 0.05)
        bb_pos = latest.get("BB_Position", 0.5)

        squeeze_str = "BB SQUEEZE DETECTED (Prepare for Expansion)" if bb_width < 0.04 else "Normal Volatility"
        state_lines.append(f"4. SESSION & VOLATILITY: Session: {session} | BB Position: {bb_pos:.2f} | {squeeze_str}")

        # --- LAYER 5: Risk & ATR Context ---
        atr = latest.get("ATR_14", close * 0.01)
        atr_pct = (atr / close) * 100 if close > 0 else 0.0
        state_lines.append(f"5. RISK ENGINE METRICS: ATR(14): {atr:.2f} ({atr_pct:.2f}% of Price)")

        return "\n".join(state_lines)

    def _build_technical_prompt(self, latest: pd.Series) -> str:
        tech_state = self._extract_cascading_technical_state(latest)
        return f"""You are a strict Trend-Following & SMC Technical Trading Agent. Your ABSOLUTE HIGHEST PRIORITY is the Macro Trend (Layer 1). 

Technical Market State:
{tech_state}

STRATEGY EXECUTION RULES (ZERO TOLERANCE FOR COUNTER-TREND):
1. MANDATORY TREND ALIGNMENT (ABSOLUTE LAW):
   - If Macro Regime contains "BEARISH", you are STRICTLY PROHIBITED from issuing a BUY signal. You can only issue SELL or NEUTRAL/HOLD.
   - If Macro Regime contains "BULLISH", you are STRICTLY PROHIBITED from issuing a SELL signal. You can only issue BUY or NEUTRAL/HOLD.
   - If "RANGING", ONLY issue NEUTRAL. Do not guess the breakout direction.

2. SMC & VOLUME WEIGHTING (SECONDARY TO TREND):
   - Valid setups require SMC confluence (Sweep + BOS/FVG + CMF/Volume) BUT they MUST align with the Macro Regime defined in Rule 1. A bullish SMC setup in a Bearish Macro Regime is INVALID.

3. SCORING MATRIX (-100 to +100):
   - Strong BUY (+60 to +100): STRICTLY IF Macro Regime is BULLISH + Bullish SMC + CMF > 0.05.
   - Strong SELL (-60 to -100): STRICTLY IF Macro Regime is BEARISH + Bearish SMC + CMF < -0.05.
   - If you detect a counter-trend setup, you MUST force the score to 0 and reason that "Trend alignment takes priority over local SMC setup".

Return Output ONLY as a valid JSON object:
{{
  "score": integer between -100 and +100 (MUST be 0 if counter-trend),
  "reasoning": "Complete analysis based on the data you have.",
  "key_evidence": ["Evidence 1", "Evidence 2"]
}}"""

    def analyze(self, context: MarketContext) -> AgentOutput:
        start_time = time.time()

        if not self.validate(context):
            return AgentOutput(
                agent_name=self.name,
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                score=0.0,
                reasons=["Missing required technical/SMC feature columns"],
            )

        latest = context.latest_bar
        prompt = self._build_technical_prompt(latest)

        system_prompt = (
            "You are an uncompromising Trend-Following Technical Trader. You NEVER issue counter-trend signals. "
            "If the trend is Bearish, your maximum action is NEUTRAL. If the trend is Bullish, your maximum action is NEUTRAL for shorts. "
            "Trend is your absolute master."
        )

        llm_response = self.llm_engine.generate(prompt, system_prompt)
        parsed = self.parse_llm_json(llm_response, "TechnicalAgent")

        score = parsed["score"]
        reasoning = parsed["reasoning"]
        evidence = parsed["evidence"]

        if score >= TECH_BUY_THRESHOLD:
            signal = SignalType.BUY
        elif score <= TECH_SELL_THRESHOLD:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL

        confidence = min(0.95, max(0.20, 0.35 + abs(score) / 110))
        if "Failed to parse" in reasoning:
            confidence = 0.15

        execution_time = (time.time() - start_time) * 1000

        # Calculate Dynamic Stop Loss & Take Profit suggestions
        close = latest["Close"]
        atr = latest.get("ATR_14", close * 0.01)
        suggested_sl = round(close - (1.5 * atr) if signal == SignalType.BUY else close + (1.5 * atr), 2)
        suggested_tp = round(close + (2.5 * atr) if signal == SignalType.BUY else close - (2.5 * atr), 2)

        # ==========================================================
        # 🛑 HARD CODE GUARDRAIL: Absolute Trend Lock (Double Security)
        # این بخش حتی اگر هوش مصنوعی در پرامپت اشتباه کرد، جلوی سیگنال خلاف روند را می‌گیرد
        # ==========================================================
        close_price = latest["Close"]
        ema200 = latest.get("EMA_200", close_price)
        senkou_a = latest.get("Senkou_Span_A", close_price)
        senkou_b = latest.get("Senkou_Span_B", close_price)
        
        cloud_top = max(senkou_a, senkou_b) if pd.notna(senkou_a) and pd.notna(senkou_b) else close_price
        cloud_bottom = min(senkou_a, senkou_b) if pd.notna(senkou_a) and pd.notna(senkou_b) else close_price

        # اگر قیمت زیر EMA200 و زیر ابر کومو است (روند نزولی قطعی)، سیگنال BUY مطلقاً ممنوع است
        if signal == SignalType.BUY and (close_price < ema200 or close_price < cloud_bottom):  
            signal = SignalType.NEUTRAL
            score = 0.0
            reasoning = f"HARD GUARDRAIL TRIGGERED: BUY blocked. Price ({close_price}) is respecting the Bearish Macro Trend (Below EMA200: {ema200:.2f} / Below Cloud: {cloud_bottom:.2f}). Trend is the absolute priority."
            
        # اگر قیمت بالای EMA200 و بالای ابر کومو است (روند صعودی قطعی)، سیگنال SELL مطلقاً ممنوع است
        elif signal == SignalType.SELL and (close_price > ema200 or close_price > cloud_top):
            signal = SignalType.NEUTRAL
            score = 0.0
            reasoning = f"HARD GUARDRAIL TRIGGERED: SELL blocked. Price ({close_price}) is respecting the Bullish Macro Trend (Above EMA200: {ema200:.2f} / Above Cloud: {cloud_top:.2f}). Trend is the absolute priority."

        # تعیین وضعیت نهایی برای متادیتا
        if close_price > ema200 and close_price > cloud_top:
            current_macro = "Bullish"
        elif close_price < ema200 and close_price < cloud_bottom:
            current_macro = "Bearish"
        else:
            current_macro = "Transitional"

        return AgentOutput(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            score=round(score, 1),
            reasons=[reasoning],
            metadata={
                "evidence": evidence[:2],
                "macro_regime": current_macro,
                "smc_event": latest.get("BOS", 0),
                "cmf": round(latest.get("CMF", 0.0), 3),
                "vol_ratio": round(latest.get("Volume_Ratio", 1.0), 2),
                "session": latest.get("Session", "Unknown"),
                "suggested_sl": suggested_sl,
                "suggested_tp": suggested_tp,
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
            acknowledged_risks=[
                "Trend reversal scenarios (regime changes)",
                "False liquidity sweep before true trend continuation"
            ],
        )

    def critique_others(self, context: DiscussionContext) -> List[DebateMessage]:
        messages = []
        my_opinion = context.my_previous_opinion
        if not my_opinion:
            return messages

        latest = context.market_context.latest_bar
        close = latest["Close"]
        ema200 = latest.get("EMA_200", close)
        cmf = latest.get("CMF", 0.0)
        
        senkou_a = latest.get("Senkou_Span_A", close)
        senkou_b = latest.get("Senkou_Span_B", close)
        cloud_top = max(senkou_a, senkou_b) if pd.notna(senkou_a) and pd.notna(senkou_b) else close
        cloud_bottom = min(senkou_a, senkou_b) if pd.notna(senkou_a) and pd.notna(senkou_b) else close

        for agent_name, opinion in context.other_agents_latest_opinions.items():
            
            # حمله به ایجنت‌هایی که سیگنال خلاف روند صادر می‌کنند
            if opinion.signal == SignalType.BUY and (close < ema200 or close < cloud_bottom):
                messages.append(DebateMessage(
                    message_id="",
                    sender=self.name,
                    target=agent_name,
                    message_type=MessageType.CRITIQUE,
                    content=f"Your BUY signal is REJECTED. It strictly violates the Macro Bearish Trend (Price < EMA200 / Cloud). We do not catch falling knives.",
                    evidence=["Price < EMA200 & Cloud (Macro Bearish)", "Trend Alignment Rule Violation"],
                    confidence=0.95, # اعتماد به نفس بالا برای رد سیگنال خلاف روند
                    round_number=1,
                ))
            elif opinion.signal == SignalType.SELL and (close > ema200 or close > cloud_top):
                messages.append(DebateMessage(
                    message_id="",
                    sender=self.name,
                    target=agent_name,
                    message_type=MessageType.CRITIQUE,
                    content=f"Your SELL signal is REJECTED. It strictly violates the Macro Bullish Trend (Price > EMA200 / Cloud). Shorting in a strong uptrend is prohibited.",
                    evidence=["Price > EMA200 & Cloud (Macro Bullish)", "Trend Alignment Rule Violation"],
                    confidence=0.95,
                    round_number=1,
                ))

            # حمله به سیگنال‌هایی که حجم و پول هوشمند تایید نمی‌کند
            if opinion.signal != SignalType.NEUTRAL and cmf < -0.05 and opinion.signal == SignalType.BUY:
                messages.append(DebateMessage(
                    message_id="",
                    sender=self.name,
                    target=agent_name,
                    message_type=MessageType.CRITIQUE,
                    content=f"BUY signal lacks institutional support: Chaikin Money Flow (CMF={cmf:.3f}) indicates active distribution.",
                    evidence=[f"CMF = {cmf:.3f} (Institutional Outflow)"],
                    confidence=0.85,
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
            if msg.message_type == MessageType.CRITIQUE and msg.confidence > 0.75:
                # اگر کسی به تحلیل ما ایراد روندی گرفت، سریعاً تسلیم شویم چون روند اولویت مطلق است
                if "trend" in msg.content.lower() or "violation" in msg.content.lower():
                    should_revise = True
                    change_reason = f"Trend alignment critique validated. Yielding to Macro structure: {msg.content}"
                    break

        if should_revise:
            return AgentOpinion(
                agent_name=self.name,
                round_number=2,
                signal=SignalType.NEUTRAL,
                confidence=0.40,
                score=0.0,
                reasoning=my_prev.reasoning + [f"REVISED TO NEUTRAL: {change_reason}"],
                key_evidence=my_prev.key_evidence,
                acknowledged_risks=my_prev.acknowledged_risks + ["Signal downgraded to respect absolute trend priority"],
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
        return ["fundamental", "sentiment", "macro", "risk"]