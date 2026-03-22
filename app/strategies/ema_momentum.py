"""
EMA Momentum Strategy
---------------------
Captures strong directional moves. Enter when a fast EMA crosses a slow EMA
with high ADX confirming genuine trend strength (not chop).

Entry logic:
  1. H4: ADX > 28 (strong trend regime).
  2. M15: EMA9 crosses above EMA21 (LONG) or below (SHORT).
  3. The cross must happen with price above/below EMA50 (trend alignment).
  4. Entry = next bar open.
  5. SL = 1.5 × ATR below/above entry.
  6. TP = 2.5R (higher R:R compensates for lower win rate in momentum trades).
"""

from typing import Optional
import pandas as pd
import pandas_ta_classic as ta

from app.strategies.base import BaseStrategy, CandidateSignal


EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50
ADX_PERIOD = 14
ADX_THRESHOLD = 28
ATR_PERIOD = 14
SL_ATR_MULT = 1.5
MIN_RR = 2.5


class EmaMomentumStrategy(BaseStrategy):
    name = "ema_momentum"

    def generate(self, candles: dict[str, pd.DataFrame]) -> Optional[CandidateSignal]:
        m15 = candles.get("M15")
        h4 = candles.get("H4")

        if m15 is None or h4 is None:
            return None
        if len(m15) < EMA_TREND + 5 or len(h4) < ADX_PERIOD + 5:
            return None

        h4 = h4.copy().reset_index(drop=True)
        m15 = m15.copy().reset_index(drop=True)

        # H4 ADX regime filter
        h4_adx = ta.adx(h4["high"], h4["low"], h4["close"], length=ADX_PERIOD)
        if h4_adx is None or h4_adx.empty:
            return None
        h4_adx_val = float(h4_adx[f"ADX_{ADX_PERIOD}"].iloc[-1])
        if pd.isna(h4_adx_val) or h4_adx_val < ADX_THRESHOLD:
            return None  # market is choppy, skip

        # M15 indicators
        m15["ema_fast"] = ta.ema(m15["close"], length=EMA_FAST)
        m15["ema_slow"] = ta.ema(m15["close"], length=EMA_SLOW)
        m15["ema_trend"] = ta.ema(m15["close"], length=EMA_TREND)
        m15["atr"] = ta.atr(m15["high"], m15["low"], m15["close"], length=ATR_PERIOD)

        last = m15.iloc[-1]
        prev = m15.iloc[-2]
        bar_index = len(m15) - 1

        if any(pd.isna(last[c]) for c in ["ema_fast", "ema_slow", "ema_trend", "atr"]):
            return None
        if any(pd.isna(prev[c]) for c in ["ema_fast", "ema_slow"]):
            return None

        close = float(last["close"])
        ema_fast = float(last["ema_fast"])
        ema_slow = float(last["ema_slow"])
        ema_trend = float(last["ema_trend"])
        atr = float(last["atr"])

        prev_fast = float(prev["ema_fast"])
        prev_slow = float(prev["ema_slow"])

        # Detect fresh crossover
        bullish_cross = prev_fast <= prev_slow and ema_fast > ema_slow
        bearish_cross = prev_fast >= prev_slow and ema_fast < ema_slow

        if atr == 0:
            return None

        # LONG: bull cross + price above EMA50
        if bullish_cross and close > ema_trend:
            entry = close
            sl = entry - SL_ATR_MULT * atr
            sl_dist = entry - sl
            tp = entry + MIN_RR * sl_dist
            rr = (tp - entry) / sl_dist
            return CandidateSignal(
                strategy_name=self.name,
                symbol="BTCUSDT",
                timeframe="M15",
                direction="LONG",
                entry_price=round(entry, 2),
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                confidence_score=round(min(88.0, 60.0 + h4_adx_val), 2),
                reasoning=(
                    f"EMA momentum LONG. H4 ADX={h4_adx_val:.1f} (strong trend). "
                    f"M15 EMA9 {prev_fast:.0f}→{ema_fast:.0f} crossed above EMA21 {ema_slow:.0f}. "
                    f"Price {close:.2f} > EMA50 {ema_trend:.2f}. R:R={rr:.2f}."
                ),
                bar_index=bar_index,
            )

        # SHORT: bear cross + price below EMA50
        if bearish_cross and close < ema_trend:
            entry = close
            sl = entry + SL_ATR_MULT * atr
            sl_dist = sl - entry
            tp = entry - MIN_RR * sl_dist
            rr = (entry - tp) / sl_dist
            return CandidateSignal(
                strategy_name=self.name,
                symbol="BTCUSDT",
                timeframe="M15",
                direction="SHORT",
                entry_price=round(entry, 2),
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                confidence_score=round(min(88.0, 60.0 + h4_adx_val), 2),
                reasoning=(
                    f"EMA momentum SHORT. H4 ADX={h4_adx_val:.1f} (strong trend). "
                    f"M15 EMA9 {prev_fast:.0f}→{ema_fast:.0f} crossed below EMA21 {ema_slow:.0f}. "
                    f"Price {close:.2f} < EMA50 {ema_trend:.2f}. R:R={rr:.2f}."
                ),
                bar_index=bar_index,
            )

        return None
