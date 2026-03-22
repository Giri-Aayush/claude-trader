from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime,
    Integer, Numeric, String, Text, ForeignKey, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "open_time"),)

    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    open_time = Column(DateTime(timezone=True), nullable=False)
    open = Column(Numeric(18, 2), nullable=False)
    high = Column(Numeric(18, 2), nullable=False)
    low = Column(Numeric(18, 2), nullable=False)
    close = Column(Numeric(18, 2), nullable=False)
    volume = Column(Numeric(24, 4), nullable=False)
    close_time = Column(DateTime(timezone=True), nullable=False)


class FundingRate(Base):
    __tablename__ = "funding_rates"
    __table_args__ = (UniqueConstraint("symbol", "funding_time"),)

    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False)
    funding_rate = Column(Numeric(12, 8), nullable=False)
    funding_time = Column(DateTime(timezone=True), nullable=False)


class OpenInterest(Base):
    __tablename__ = "open_interest"
    __table_args__ = (UniqueConstraint("symbol", "timestamp"),)

    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False)
    open_interest = Column(Numeric(24, 4), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(BigInteger, primary_key=True)
    strategy_name = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False, default="BTCUSDT")
    timeframe = Column(String(10), nullable=False)
    direction = Column(String(5), nullable=False)
    entry_price = Column(Numeric(18, 2), nullable=False)
    stop_loss = Column(Numeric(18, 2), nullable=False)
    take_profit = Column(Numeric(18, 2), nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=False)
    reasoning = Column(Text)
    position_size_pct = Column(Numeric(10, 6))
    kelly_fraction = Column(Numeric(10, 6))
    bar_index = Column(BigInteger, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True))
    status = Column(String(20), default="PENDING")


class Outcome(Base):
    __tablename__ = "outcomes"

    id = Column(BigInteger, primary_key=True)
    signal_id = Column(BigInteger, ForeignKey("signals.id", ondelete="CASCADE"))
    result = Column(String(4), nullable=False)
    exit_price = Column(Numeric(18, 2), nullable=False)
    pnl_pct = Column(Numeric(10, 6), nullable=False)
    duration_minutes = Column(Integer)
    resolved_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(BigInteger, primary_key=True)
    strategy_name = Column(String(50), nullable=False)
    window_days = Column(Integer, nullable=False)
    win_rate = Column(Numeric(8, 4))
    sharpe_ratio = Column(Numeric(10, 4))
    max_drawdown = Column(Numeric(8, 4))
    total_trades = Column(Integer, default=0)
    is_overfitted = Column(Boolean, default=False)
    monte_carlo_passed = Column(Boolean, default=False)
    oos_win_rate = Column(Numeric(8, 4))
    run_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), unique=True, nullable=False)
    win_rate = Column(Numeric(8, 4), default=0.5)
    total_trades = Column(Integer, default=0)
    consecutive_losses = Column(Integer, default=0)
    sharpe_ratio = Column(Numeric(10, 4), default=0)
    avg_rr = Column(Numeric(10, 4), default=2.0)
    performance_score = Column(Numeric(10, 4), default=50.0)
    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow)


class OptimizedParams(Base):
    __tablename__ = "optimized_params"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), nullable=False)
    params = Column(JSONB, nullable=False)
    performance_score = Column(Numeric(10, 4))
    monte_carlo_score = Column(Numeric(10, 4))
    is_active = Column(Boolean, default=True)
    optimized_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class SystemState(Base):
    __tablename__ = "system_state"

    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
