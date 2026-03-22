"""
Trend Continuation Strategy (EMA Pullback)
------------------------------------------
Classic EMA-stack trend following. Enter on pullbacks to EMA20
in the direction of the higher-timeframe trend.

Entry logic (LONG):
  1. H4: EMA50 > EMA200 (macro uptrend).
  2. H1: price above EMA50 (intermediate uptrend).
  3. M15: price pulls back to touch EMA20, RSI dips below 45
     then closes back above it (momentum returning).
  4. Entry = next bar open.
  5. SL = below EMA50 on M15, minimum 0.8 × ATR below entry.
  6. TP = 2× SL distance (2R).
"""

from typing import Optional
import pandas as pd
import pandas_ta_classic as ta

from app.strategies.base import BaseStrategy, CandidateSignal


EMA_FAST = 20
EMA_MID = 50
EMA_SLOW = 200
RSI_PERIOD = 14
ATR_PERIOD = 14
MIN_RR = 2.0


class TrendContinuationStrategy(BaseStrategy):
    name = "trend_continuation"

    def generate(self, candles: dict[str, pd.DataFrame]) -> Optional[CandidateSignal]:
        m15 = candles.get("M15")
        h1 = candles.get("H1")
        h4 = candles.get("H4")

        if m15 is None or h1 is None or h4 is None:
            return None
        if len(m15) < EMA_SLOW + 5 or len(h1) < EMA_MID + 5 or len(h4) < EMA_SLOW + 5:
            return None

        m15 = m15.copy().reset_index(drop=True)
        h1 = h1.copy().reset_index(drop=True)
        h4 = h4.copy().reset_index(drop=True)

        # H4 macro trend
        h4["ema50"] = ta.ema(h4["close"], length=EMA_MID)
        h4["ema200"] = ta.ema(h4["close"], length=EMA_SLOW)
        h4_last = h4.iloc[-1]
        if pd.isna(h4_last["ema50"]) or pd.isna(h4_last["ema200"]):
            return None

        h4_bullish = float(h4_last["ema50"]) > float(h4_last["ema200"])
        h4_bearish = float(h4_last["ema50"]) < float(h4_last["ema200"])

        # H1 intermediate trend
        h1["ema50"] = ta.ema(h1["close"], length=EMA_MID)
        h1_last = h1.iloc[-1]
        if pd.isna(h1_last["ema50"]):
            return None
        h1_above_ema = float(h1_last["close"]) > float(h1_last["ema50"])
        h1_below_ema = float(h1_last["close"]) < float(h1_last["ema50"])

        # M15 entry signals
        m15["ema20"] = ta.ema(m15["close"], length=EMA_FAST)
        m15["ema50"] = ta.ema(m15["close"], length=EMA_MID)
        m15["rsi"] = ta.rsi(m15["close"], length=RSI_PERIOD)
        m15["atr"] = ta.atr(m15["high"], m15["low"], m15["close"], length=ATR_PERIOD)

        last = m15.iloc[-1]
        prev = m15.iloc[-2]

        if any(pd.isna(last[c]) for c in ["ema20", "ema50", "rsi", "atr"]):
            return None

        close = float(last["close"])
        ema20 = float(last["ema20"])
        ema50_m15 = float(last["ema50"])
        rsi = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi
        atr = float(last["atr"])
        bar_index = len(m15) - 1

        # LONG: macro bull + H1 above EMA + M15 touching EMA20 with RSI in bullish zone
        if h4_bullish and h1_above_ema:
            touching_ema20 = abs(close - ema20) <= 1.0 * atr
            rsi_recovering = 45 <= rsi <= 65
            if touching_ema20 and rsi_recovering and close > ema20:
                sl = min(ema50_m15, close - 0.8 * atr)
                sl_dist = close - sl
                if sl_dist <= 0:
                    return None
                tp = close + MIN_RR * sl_dist
                rr = (tp - close) / sl_dist
                return CandidateSignal(
                    strategy_name=self.name,
                    symbol="BTCUSDT",
                    timeframe="M15",
                    direction="LONG",
                    entry_price=round(close, 2),
                    stop_loss=round(sl, 2),
                    take_profit=round(tp, 2),
                    confidence_score=round(min(85.0, 65.0 + rr * 5), 2),
                    reasoning=(
                        f"Trend continuation LONG. H4 EMA50>{float(h4_last['ema50']):.0f} > EMA200. "
                        f"M15 pullback to EMA20={ema20:.2f}, RSI {prev_rsi:.0f}→{rsi:.0f}. "
                        f"R:R={rr:.2f}."
                    ),
                    bar_index=bar_index,
                )

        # SHORT: macro bear + H1 below EMA + M15 touching EMA20 with RSI in bearish zone
        if h4_bearish and h1_below_ema:
            touching_ema20 = abs(close - ema20) <= 1.0 * atr
            rsi_fading = 35 <= rsi <= 55
            if touching_ema20 and rsi_fading and close < ema20:
                sl = max(ema50_m15, close + 0.8 * atr)
                sl_dist = sl - close
                if sl_dist <= 0:
                    return None
                tp = close - MIN_RR * sl_dist
                rr = (close - tp) / sl_dist
                return CandidateSignal(
                    strategy_name=self.name,
                    symbol="BTCUSDT",
                    timeframe="M15",
                    direction="SHORT",
                    entry_price=round(close, 2),
                    stop_loss=round(sl, 2),
                    take_profit=round(tp, 2),
                    confidence_score=round(min(85.0, 65.0 + rr * 5), 2),
                    reasoning=(
                        f"Trend continuation SHORT. H4 EMA50 < EMA200. "
                        f"M15 pullback to EMA20={ema20:.2f}, RSI {prev_rsi:.0f}→{rsi:.0f}. "
                        f"R:R={rr:.2f}."
                    ),
                    bar_index=bar_index,
                )

        return None
