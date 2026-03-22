"""
Liquidity Sweep Strategy
------------------------
Price wicks above a recent swing high (or below a swing low), grabbing stop
losses, then reverses sharply back into range. We enter on the reversal.

Entry logic (LONG example — sweep of lows):
  1. On the H1 chart, identify the lowest swing low in the last 20 bars.
  2. On the current M15 bar, the low must pierce that swing low by at least
     0.15 × ATR (the "sweep").
  3. The M15 candle must close ABOVE the swing low (pin bar / wick rejection).
  4. Entry = next bar open.
  5. SL = sweep low - 0.5 × ATR.
  6. TP = nearest swing high within 20 bars, minimum 1.8R.
"""

from typing import Optional
import pandas as pd
import pandas_ta_classic as ta

from app.strategies.base import BaseStrategy, CandidateSignal


SWING_LOOKBACK = 20
MIN_SWEEP_MULT = 0.15   # wick must pierce swing by at least this × ATR
MIN_RR = 1.8
ATR_PERIOD = 14


class LiquiditySweepStrategy(BaseStrategy):
    name = "liquidity_sweep"

    def generate(self, candles: dict[str, pd.DataFrame]) -> Optional[CandidateSignal]:
        m15 = candles.get("M15")
        h1 = candles.get("H1")
        if m15 is None or h1 is None or len(m15) < SWING_LOOKBACK + 5 or len(h1) < SWING_LOOKBACK + 5:
            return None

        m15 = m15.copy().reset_index(drop=True)
        h1 = h1.copy().reset_index(drop=True)

        # ATR on M15 for distance calculations
        m15["atr"] = ta.atr(m15["high"], m15["low"], m15["close"], length=ATR_PERIOD)
        if m15["atr"].isna().all():
            return None

        last = m15.iloc[-1]
        atr = float(m15["atr"].iloc[-1])
        if pd.isna(atr) or atr == 0:
            return None

        bar_index = len(m15) - 1
        close = float(last["close"])
        low = float(last["low"])
        high = float(last["high"])

        # --- Swing levels from H1 ---
        swing_low = float(h1["low"].iloc[-SWING_LOOKBACK:].min())
        swing_high = float(h1["high"].iloc[-SWING_LOOKBACK:].max())

        # --- Check LONG setup (sweep of lows) ---
        swept_low = low < swing_low and (swing_low - low) >= MIN_SWEEP_MULT * atr
        rejected_low = close > swing_low  # closed back above the level

        if swept_low and rejected_low:
            entry = close
            sl = low - 0.5 * atr
            sl_dist = entry - sl
            if sl_dist <= 0:
                return None
            tp = entry + MIN_RR * sl_dist
            rr = (tp - entry) / sl_dist
            if rr < MIN_RR:
                return None

            confidence = min(90.0, 60.0 + (rr - MIN_RR) * 10)
            return CandidateSignal(
                strategy_name=self.name,
                symbol="BTCUSDT",
                timeframe="M15",
                direction="LONG",
                entry_price=round(entry, 2),
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                confidence_score=round(confidence, 2),
                reasoning=(
                    f"Liquidity sweep below swing low {swing_low:.2f}. "
                    f"M15 wick to {low:.2f}, closed at {close:.2f}. "
                    f"ATR={atr:.2f}, R:R={rr:.2f}."
                ),
                bar_index=bar_index,
            )

        # --- Check SHORT setup (sweep of highs) ---
        swept_high = high > swing_high and (high - swing_high) >= MIN_SWEEP_MULT * atr
        rejected_high = close < swing_high

        if swept_high and rejected_high:
            entry = close
            sl = high + 0.5 * atr
            sl_dist = sl - entry
            if sl_dist <= 0:
                return None
            tp = entry - MIN_RR * sl_dist
            rr = (entry - tp) / sl_dist
            if rr < MIN_RR:
                return None

            confidence = min(90.0, 60.0 + (rr - MIN_RR) * 10)
            return CandidateSignal(
                strategy_name=self.name,
                symbol="BTCUSDT",
                timeframe="M15",
                direction="SHORT",
                entry_price=round(entry, 2),
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                confidence_score=round(confidence, 2),
                reasoning=(
                    f"Liquidity sweep above swing high {swing_high:.2f}. "
                    f"M15 wick to {high:.2f}, closed at {close:.2f}. "
                    f"ATR={atr:.2f}, R:R={rr:.2f}."
                ),
                bar_index=bar_index,
            )

        return None
