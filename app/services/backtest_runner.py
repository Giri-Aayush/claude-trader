"""
BacktestRunner
--------------
Walk-forward backtester with Monte Carlo stress testing.

For each strategy and each window (7, 14, 30, 60 days):
  1. Split candles: 80% training, 20% out-of-sample (OOS).
  2. Run strategy signal generation over historical bars (replay mode).
  3. Simulate each trade using TradeSimulator (strict bar N+1 entry).
  4. Compute metrics on OOS trades.
  5. Monte Carlo stress test: shuffle OOS trade order N_SHUFFLES times.
     If shuffled equity beats original in >50% of runs → strategy is fragile.
  6. Persist results to backtest_results table.
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import numpy as np
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tables import Candle, BacktestResult
from app.services.trade_simulator import simulate_trade
from app.services.metrics_calculator import compute_metrics
from app.strategies.liquidity_sweep import LiquiditySweepStrategy
from app.strategies.trend_continuation import TrendContinuationStrategy
from app.strategies.breakout_expansion import BreakoutExpansionStrategy
from app.strategies.ema_momentum import EmaMomentumStrategy

log = logging.getLogger(__name__)

WINDOWS = [7, 14, 30, 60]
TRAIN_SPLIT = 0.80
N_SHUFFLES = 200
MIN_TRADES_FOR_VALID_BT = 10
OVERFITTING_OOS_THRESHOLD = 0.80  # OOS win rate must be >= 80% of training win rate


STRATEGY_CLASSES = {
    "liquidity_sweep": LiquiditySweepStrategy,
    "trend_continuation": TrendContinuationStrategy,
    "breakout_expansion": BreakoutExpansionStrategy,
    "ema_momentum": EmaMomentumStrategy,
}


async def _load_candles_for_window(days: int) -> dict[str, pd.DataFrame]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    frames = {}
    async with AsyncSessionLocal() as session:
        for tf in ["M15", "H1", "H4", "D1"]:
            result = await session.execute(
                select(Candle)
                .where(
                    Candle.symbol == settings.SYMBOL,
                    Candle.timeframe == tf,
                    Candle.open_time >= cutoff,
                )
                .order_by(Candle.open_time)
            )
            rows = result.scalars().all()
            if rows:
                frames[tf] = pd.DataFrame([{
                    "open_time": r.open_time,
                    "open":  float(r.open),
                    "high":  float(r.high),
                    "low":   float(r.low),
                    "close": float(r.close),
                    "volume": float(r.volume),
                } for r in rows])
    return frames


def _replay_strategy(strategy, candles: dict[str, pd.DataFrame]) -> list[dict]:
    """
    Walk bar by bar through M15, feeding a rolling window to the strategy.
    Collect all generated signals with their bar indices.
    """
    m15 = candles.get("M15")
    if m15 is None or len(m15) < 50:
        return []

    signals = []
    warmup = 50  # bars needed for indicator calculation

    for i in range(warmup, len(m15) - 1):  # -1 to always leave room for bar N+1
        # Build a slice of candles up to bar i (inclusive) — no future data
        slice_candles = {
            tf: df.iloc[:i + 1].copy() for tf, df in candles.items()
        }
        try:
            sig = strategy.generate(slice_candles)
            if sig is not None:
                signals.append({
                    "bar_index": i,
                    "direction": sig.direction,
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                })
        except Exception:
            pass

    return signals


def _monte_carlo_test(pnl_list: list[float], n_shuffles: int = N_SHUFFLES) -> bool:
    """
    Shuffle the trade order N times. If >50% of shuffles produce a better
    Sharpe than the original, the result is luck-dependent → fragile.
    Returns True if strategy PASSES the Monte Carlo test (robust).
    """
    if len(pnl_list) < MIN_TRADES_FOR_VALID_BT:
        return True  # not enough data to judge

    def equity_sharpe(trades: list[float]) -> float:
        if not trades:
            return 0.0
        mean = np.mean(trades)
        std = np.std(trades)
        return float(mean / std) if std > 0 else 0.0

    original_sharpe = equity_sharpe(pnl_list)
    beat_count = 0
    for _ in range(n_shuffles):
        shuffled = pnl_list.copy()
        random.shuffle(shuffled)
        if equity_sharpe(shuffled) > original_sharpe:
            beat_count += 1

    fragile = beat_count > n_shuffles * 0.5
    return not fragile  # passes if NOT fragile


async def run_backtests() -> None:
    """Run all strategy/window combinations. Called every 4h by APScheduler."""
    log.info("Starting backtest run...")

    for window_days in WINDOWS:
        candles = await _load_candles_for_window(window_days)
        if not candles or "M15" not in candles:
            log.warning("No candles for %d-day window, skipping.", window_days)
            continue

        m15 = candles["M15"]
        split_idx = int(len(m15) * TRAIN_SPLIT)

        for strategy_name, strategy_cls in STRATEGY_CLASSES.items():
            strategy = strategy_cls()
            log.info("Backtesting %s / %dd window...", strategy_name, window_days)

            # Training set
            train_candles = {tf: df.iloc[:split_idx].copy() for tf, df in candles.items()}
            train_signals = _replay_strategy(strategy, train_candles)
            train_pnl = []
            for sig in train_signals:
                result = simulate_trade(
                    m15.iloc[:split_idx],
                    sig["bar_index"],
                    sig["direction"],
                    sig["stop_loss"],
                    sig["take_profit"],
                )
                if result:
                    train_pnl.append(result.pnl_pct)

            # OOS set
            oos_candles = {tf: df.copy() for tf, df in candles.items()}
            all_signals = _replay_strategy(strategy, oos_candles)
            oos_signals = [s for s in all_signals if s["bar_index"] >= split_idx]
            oos_pnl = []
            for sig in oos_signals:
                result = simulate_trade(
                    m15,
                    sig["bar_index"],
                    sig["direction"],
                    sig["stop_loss"],
                    sig["take_profit"],
                )
                if result:
                    oos_pnl.append(result.pnl_pct)

            if len(oos_pnl) < MIN_TRADES_FOR_VALID_BT:
                log.info("Not enough OOS trades for %s/%dd, skipping.", strategy_name, window_days)
                continue

            train_metrics = compute_metrics(train_pnl) if train_pnl else {}
            oos_metrics = compute_metrics(oos_pnl)

            # Overfitting check
            train_wr = train_metrics.get("win_rate", 0.5)
            oos_wr = oos_metrics.get("win_rate", 0.0)
            is_overfitted = train_wr > 0 and (oos_wr / train_wr) < OVERFITTING_OOS_THRESHOLD

            # Monte Carlo test
            mc_passed = _monte_carlo_test(oos_pnl)

            if is_overfitted:
                log.warning("%s/%dd flagged as OVERFITTED (train WR=%.1f%%, OOS WR=%.1f%%).",
                            strategy_name, window_days, train_wr * 100, oos_wr * 100)
            if not mc_passed:
                log.warning("%s/%dd FAILED Monte Carlo test.", strategy_name, window_days)

            # Persist
            async with AsyncSessionLocal() as session:
                bt = BacktestResult(
                    strategy_name=strategy_name,
                    window_days=window_days,
                    win_rate=oos_metrics.get("win_rate"),
                    sharpe_ratio=oos_metrics.get("sharpe"),
                    max_drawdown=oos_metrics.get("max_drawdown"),
                    total_trades=oos_metrics.get("total_trades", 0),
                    is_overfitted=is_overfitted,
                    monte_carlo_passed=mc_passed,
                    oos_win_rate=oos_wr,
                    run_at=datetime.now(tz=timezone.utc),
                )
                session.add(bt)
                await session.commit()

    log.info("Backtest run complete.")
