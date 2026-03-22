"""
TelegramNotifier
----------------
Sends signal alerts and health digests via Telegram Bot API.
"""

import logging
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode

from app.config import settings

log = logging.getLogger(__name__)


def _bot() -> Bot:
    return Bot(token=settings.TELEGRAM_BOT_TOKEN)


async def send_signal(
    direction: str,
    strategy: str,
    entry: float,
    sl: float,
    tp: float,
    confidence: float,
    reasoning: str,
    position_pct: float,
) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured, skipping signal send.")
        return

    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
    emoji = "🟢" if direction == "LONG" else "🔴"

    msg = (
        f"{emoji} *BTCUSDT.P — {direction}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Strategy:* {strategy.replace('_', ' ').title()}\n"
        f"*Entry:* `${entry:,.2f}`\n"
        f"*Stop Loss:* `${sl:,.2f}`\n"
        f"*Take Profit:* `${tp:,.2f}`\n"
        f"*R:R:* `{rr:.2f}`\n"
        f"*Confidence:* `{confidence:.0f}/100`\n"
        f"*Size:* `{position_pct * 100:.2f}% of account`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_{reasoning}_"
    )

    try:
        async with _bot() as bot:
            await bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
            )
        log.info("Signal sent to Telegram: %s %s", direction, strategy)
    except Exception as e:
        log.error("Telegram send_signal failed: %s", e)


async def send_health_digest(metrics: dict) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    msg = (
        f"📊 *Daily Health Digest — {datetime.utcnow().strftime('%Y-%m-%d')}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Win Rate (7d):* `{metrics.get('win_rate_7d', 0) * 100:.1f}%`\n"
        f"*Sharpe (7d):* `{metrics.get('sharpe_7d', 0):.2f}`\n"
        f"*Max Drawdown:* `{metrics.get('max_drawdown', 0) * 100:.2f}%`\n"
        f"*Total Signals (7d):* `{metrics.get('total_signals_7d', 0)}`\n"
        f"*Circuit Breaker:* `{'ACTIVE ⛔' if metrics.get('circuit_breaker') else 'OK ✅'}`\n"
        f"*Top Strategy:* `{metrics.get('top_strategy', 'N/A')}`\n"
    )

    try:
        async with _bot() as bot:
            await bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as e:
        log.error("Telegram send_health_digest failed: %s", e)


async def send_circuit_breaker_alert(consecutive_losses: int) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    msg = (
        f"⛔ *CIRCUIT BREAKER TRIGGERED*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{consecutive_losses} consecutive stop losses hit.\n"
        f"System paused for *24 hours*. No new signals will be sent.\n"
        f"Review strategy performance before resuming."
    )

    try:
        async with _bot() as bot:
            await bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as e:
        log.error("Telegram circuit breaker alert failed: %s", e)
