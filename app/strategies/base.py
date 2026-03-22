from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd


@dataclass
class CandidateSignal:
    strategy_name: str
    symbol: str
    timeframe: str
    direction: str          # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float # 0-100
    reasoning: str
    bar_index: int          # Index of the last closed bar that triggered the signal.
                            # TradeSimulator MUST start evaluation from bar_index + 1.
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def risk_reward(self) -> float:
        sl_dist = abs(self.entry_price - self.stop_loss)
        tp_dist = abs(self.take_profit - self.entry_price)
        if sl_dist == 0:
            return 0.0
        return tp_dist / sl_dist


class BaseStrategy:
    name: str = "base"

    def generate(self, candles: dict[str, pd.DataFrame]) -> Optional[CandidateSignal]:
        """
        Receive a dict of closed-bar DataFrames keyed by timeframe string.
        Return a CandidateSignal or None.

        DataFrames have columns: open_time, open, high, low, close, volume
        All bars are confirmed closed — no partial/live bars.
        """
        raise NotImplementedError
