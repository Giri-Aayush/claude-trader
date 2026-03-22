"""
Breakout Expansion Strategy (Volatility Squeeze)
-------------------------------------------------
Wait for a Bollinger Band squeeze (low volatility compression), then enter
on the first bar that breaks cleanly outside the bands.

A squeeze is confirmed when Bollinger Bands are inside the Keltner Channel
(TTM Squeeze method). When bands re-expand and price breaks out, momentum
is expected to follow.

Entry logic:
  1. Detect squeeze on H1: BB(20,2) width < KC(20,1.5) width for 3+ bars.
  2. Squeeze fires (bands expand past KC).
  3. M15: current bar closes outside BB upper (LONG) or lower (SHORT).
  4. ADX > 20 confirms directional momentum.
  5. Entry = next bar open.
  6. SL = opposite BB band (at signal bar).
  7. TP = entry ± 2 × (entry - SL).
"""

from typing import Optional
import pandas as pd
import pandas_ta_classic as ta

from app.strategies.base import BaseStrategy, CandidateSignal


BB_LENGTH = 20
BB_STD = 2.0
KC_LENGTH = 20
KC_MULT = 1.5
ADX_PERIOD = 14
SQUEEZE_BARS = 3
MIN_RR = 2.0


class BreakoutExpansionStrategy(BaseStrategy):
    name = "breakout_expansion"

    def __init__(self, params: dict | None = None):
        p = params or {}
        self.bb_length = int(p.get("bb_length", BB_LENGTH))
        self.squeeze_bars = int(p.get("squeeze_bars", SQUEEZE_BARS))
        self.adx_threshold = float(p.get("adx_threshold", 20.0))

    def generate(self, candles: dict[str, pd.DataFrame]) -> Optional[CandidateSignal]:
        m15 = candles.get("M15")
        h1 = candles.get("H1")

        if m15 is None or h1 is None:
            return None
        if len(h1) < self.bb_length + self.squeeze_bars + 5 or len(m15) < self.bb_length + 5:
            return None

        h1 = h1.copy().reset_index(drop=True)
        m15 = m15.copy().reset_index(drop=True)

        # Calculate BB and KC on H1 to detect squeeze
        bbands = ta.bbands(h1["close"], length=self.bb_length, std=BB_STD)
        if bbands is None or bbands.empty:
            return None

        h1["bb_upper"] = bbands.get(f"BBU_{self.bb_length}_{BB_STD}", bbands.iloc[:, 0])
        h1["bb_lower"] = bbands.get(f"BBL_{self.bb_length}_{BB_STD}", bbands.iloc[:, 2])
        h1["bb_mid"] = bbands.get(f"BBM_{self.bb_length}_{BB_STD}", bbands.iloc[:, 1])

        kc = ta.kc(h1["high"], h1["low"], h1["close"], length=KC_LENGTH, scalar=KC_MULT)
        if kc is None or kc.empty:
            return None

        h1["kc_upper"] = kc.iloc[:, 0]
        h1["kc_lower"] = kc.iloc[:, 2]

        h1["squeezed"] = (h1["bb_upper"] < h1["kc_upper"]) & (h1["bb_lower"] > h1["kc_lower"])

        # Check squeeze fired: last bar not squeezed, previous N bars were
        recent = h1.iloc[-(self.squeeze_bars + 1):]
        if recent.iloc[-1]["squeezed"]:
            return None  # still in squeeze, no signal
        if not recent.iloc[:-1]["squeezed"].all():
            return None  # squeeze wasn't sustained

        # Squeeze has just fired — now check M15 for breakout direction
        m15_bbands = ta.bbands(m15["close"], length=self.bb_length, std=BB_STD)
        if m15_bbands is None or m15_bbands.empty:
            return None

        m15["bb_upper"] = m15_bbands.get(f"BBU_{self.bb_length}_{BB_STD}", m15_bbands.iloc[:, 0])
        m15["bb_lower"] = m15_bbands.get(f"BBL_{self.bb_length}_{BB_STD}", m15_bbands.iloc[:, 2])
        m15["adx"] = ta.adx(m15["high"], m15["low"], m15["close"], length=ADX_PERIOD).get(
            f"ADX_{ADX_PERIOD}", pd.Series(dtype=float)
        )
        m15["atr"] = ta.atr(m15["high"], m15["low"], m15["close"], length=14)

        last = m15.iloc[-1]
        bar_index = len(m15) - 1

        if any(pd.isna(last[c]) for c in ["bb_upper", "bb_lower", "adx", "atr"]):
            return None

        close = float(last["close"])
        bb_upper = float(last["bb_upper"])
        bb_lower = float(last["bb_lower"])
        adx = float(last["adx"])
        atr = float(last["atr"])

        if adx < self.adx_threshold:
            return None  # no directional momentum

        # LONG breakout
        if close > bb_upper:
            entry = close
            sl = bb_lower
            sl_dist = entry - sl
            if sl_dist <= 0:
                return None
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
                confidence_score=round(min(85.0, 55.0 + adx), 2),
                reasoning=(
                    f"Squeeze breakout LONG. H1 BB squeeze fired after {self.squeeze_bars} bars. "
                    f"M15 close {close:.2f} > BB upper {bb_upper:.2f}. ADX={adx:.1f}. R:R={rr:.2f}."
                ),
                bar_index=bar_index,
            )

        # SHORT breakout
        if close < bb_lower:
            entry = close
            sl = bb_upper
            sl_dist = sl - entry
            if sl_dist <= 0:
                return None
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
                confidence_score=round(min(85.0, 55.0 + adx), 2),
                reasoning=(
                    f"Squeeze breakout SHORT. H1 BB squeeze fired after {self.squeeze_bars} bars. "
                    f"M15 close {close:.2f} < BB lower {bb_lower:.2f}. ADX={adx:.1f}. R:R={rr:.2f}."
                ),
                bar_index=bar_index,
            )

        return None
