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
    sl_pct = abs(entry - sl) / entry * 100
    tp_pct = abs(tp - entry) / entry * 100
    arrow = "▲" if direction == "LONG" else "▼"
    sl_sign = "−" if direction == "LONG" else "+"
    tp_sign = "+" if direction == "LONG" else "−"

    msg = (
        f"{arrow} *{direction}*  ·  {settings.SYMBOL}  ·  {strategy.replace('_', ' ').title()}\n"
        f"\n"
        f"`Entry   ${entry:>12,.2f}`\n"
        f"`SL      ${sl:>12,.2f}  ({sl_sign}{sl_pct:.2f}%)`\n"
        f"`TP      ${tp:>12,.2f}  ({tp_sign}{tp_pct:.2f}%)`\n"
        f"`R:R     {rr:>6.2f}×   ·   Size {position_pct * 100:.1f}%`\n"
        f"\n"
        f"_Confidence {confidence:.0f}/100 · {reasoning}_"
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

    status = "Paused ⛔" if metrics.get("circuit_breaker") else "Running ✓"
    top = metrics.get("top_strategy", "N/A").replace("_", " ").title()

    msg = (
        f"*Daily Digest*  ·  {datetime.utcnow().strftime('%d %b %Y')}\n"
        f"\n"
        f"`Win Rate    {metrics.get('win_rate_7d', 0) * 100:>6.1f}%`\n"
        f"`Sharpe      {metrics.get('sharpe_7d', 0):>6.2f}`\n"
        f"`Drawdown    {metrics.get('max_drawdown', 0) * 100:>6.2f}%`\n"
        f"`Signals     {metrics.get('total_signals_7d', 0):>6}`\n"
        f"`Top         {top}`\n"
        f"`System      {status}`\n"
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
        f"⛔ *Trading Paused*\n"
        f"\n"
        f"`{consecutive_losses} consecutive losses hit the limit.`\n"
        f"_System halted for 24 hours. No new signals will be sent._"
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
