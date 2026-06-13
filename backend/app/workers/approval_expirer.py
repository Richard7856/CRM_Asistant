"""
Approval expirer — the 6th background worker (P0.8).

P0.5 set `expires_at` on every PENDING approval request but nothing ever acted on
it, so a request nobody answered sat PENDING forever. This worker periodically
sweeps overdue PENDING requests to EXPIRED and audits each one (APPROVAL_EXPIRED).

Same single-process asyncio pattern as the other workers (see lifecycle_monitor).
NOTE: like the rest, this lives inside the FastAPI process — fine for now, but when
we run agents 24/7 (Track A / A1) the scheduler moves to a separate process.
"""

import asyncio
import logging

from app.approvals.service import expire_overdue_approvals
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)


async def run_approval_expirer(interval_seconds: int = 300) -> None:
    """Every `interval_seconds`, expire PENDING approval requests past their deadline."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with async_session_factory() as session:
                count = await expire_overdue_approvals(session)
                await session.commit()
                if count > 0:
                    logger.info("Expired %d overdue approval request(s)", count)
        except Exception:
            logger.exception("Approval expirer run failed")
