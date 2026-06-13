"""
Retention purger — the 7th background worker (P0.7b).

Runs daily, deletes log rows past their per-tenant retention window (see
app/compliance/retention.py allowlist), and audits each purge. Retention is
opt-in: a table is only touched for tenants that set an enabled RetentionPolicy.

Same single-process asyncio pattern as the other workers. Moves to a separate
process when we run 24/7 (Track A / A1).
"""

import asyncio
import logging

from app.compliance.service import purge_expired_data
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)


async def run_retention_purger(interval_seconds: int = 86400) -> None:
    """Every `interval_seconds` (default daily), purge data past retention."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with async_session_factory() as session:
                total = await purge_expired_data(session)
                await session.commit()
                if total > 0:
                    logger.info("Retention purge removed %d row(s)", total)
        except Exception:
            logger.exception("Retention purge run failed")
