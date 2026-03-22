-- Claude BTC Perp Trader — Database Schema

CREATE TABLE IF NOT EXISTS candles (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open_time TIMESTAMPTZ NOT NULL,
    open NUMERIC(18,2) NOT NULL,
    high NUMERIC(18,2) NOT NULL,
    low NUMERIC(18,2) NOT NULL,
    close NUMERIC(18,2) NOT NULL,
    volume NUMERIC(24,4) NOT NULL,
    close_time TIMESTAMPTZ NOT NULL,
    UNIQUE(symbol, timeframe, open_time)
);
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, open_time DESC);

CREATE TABLE IF NOT EXISTS funding_rates (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    funding_rate NUMERIC(12,8) NOT NULL,
    funding_time TIMESTAMPTZ NOT NULL,
    UNIQUE(symbol, funding_time)
);
CREATE INDEX IF NOT EXISTS idx_funding_lookup ON funding_rates(symbol, funding_time DESC);

CREATE TABLE IF NOT EXISTS open_interest (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    open_interest NUMERIC(24,4) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    UNIQUE(symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_oi_lookup ON open_interest(symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO strategies (name) VALUES
    ('liquidity_sweep'),
    ('trend_continuation'),
    ('breakout_expansion'),
    ('ema_momentum')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL DEFAULT 'BTCUSDT',
    timeframe VARCHAR(10) NOT NULL,
    direction VARCHAR(5) NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price NUMERIC(18,2) NOT NULL,
    stop_loss NUMERIC(18,2) NOT NULL,
    take_profit NUMERIC(18,2) NOT NULL,
    confidence_score NUMERIC(5,2) NOT NULL,
    reasoning TEXT,
    position_size_pct NUMERIC(10,6),
    kelly_fraction NUMERIC(10,6),
    bar_index BIGINT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACTIVE', 'WIN', 'LOSS', 'EXPIRED'))
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_generated ON signals(generated_at DESC);

CREATE TABLE IF NOT EXISTS outcomes (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT REFERENCES signals(id) ON DELETE CASCADE,
    result VARCHAR(4) NOT NULL CHECK (result IN ('WIN', 'LOSS')),
    exit_price NUMERIC(18,2) NOT NULL,
    pnl_pct NUMERIC(10,6) NOT NULL,
    duration_minutes INTEGER,
    resolved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(50) NOT NULL,
    window_days INTEGER NOT NULL,
    win_rate NUMERIC(8,4),
    sharpe_ratio NUMERIC(10,4),
    max_drawdown NUMERIC(8,4),
    total_trades INTEGER DEFAULT 0,
    is_overfitted BOOLEAN DEFAULT FALSE,
    monte_carlo_passed BOOLEAN DEFAULT FALSE,
    oos_win_rate NUMERIC(8,4),
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_backtest_lookup ON backtest_results(strategy_name, run_at DESC);

CREATE TABLE IF NOT EXISTS strategy_performance (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(50) UNIQUE NOT NULL,
    win_rate NUMERIC(8,4) DEFAULT 0.5,
    total_trades INTEGER DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,
    sharpe_ratio NUMERIC(10,4) DEFAULT 0,
    avg_rr NUMERIC(10,4) DEFAULT 2.0,
    performance_score NUMERIC(10,4) DEFAULT 50.0,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO strategy_performance (strategy_name) VALUES
    ('liquidity_sweep'),
    ('trend_continuation'),
    ('breakout_expansion'),
    ('ema_momentum')
ON CONFLICT (strategy_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS optimized_params (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(50) NOT NULL,
    params JSONB NOT NULL,
    performance_score NUMERIC(10,4),
    monte_carlo_score NUMERIC(10,4),
    is_active BOOLEAN DEFAULT TRUE,
    optimized_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_params_active ON optimized_params(strategy_name, is_active);

CREATE TABLE IF NOT EXISTS system_state (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO system_state (key, value) VALUES
    ('circuit_breaker_active', 'false'),
    ('circuit_breaker_until', ''),
    ('daily_loss_pct', '0.0'),
    ('daily_loss_date', CURRENT_DATE::TEXT)
ON CONFLICT (key) DO NOTHING;
