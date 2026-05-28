"""MaintenanceCalendar — TTL-cached suppression lookup."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from croniter import CroniterBadCronError, croniter  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.models import MaintenanceWindow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CompiledWindow:
    window_id: int
    scope_type: str
    scope_id: int
    schedule_type: str
    starts_at: datetime | None
    ends_at: datetime | None
    cron_expr: str | None
    duration_minutes: int | None
    suppress_alert_types: tuple[str, ...] | None  # None = suppress all


class MaintenanceCalendar:
    """In-memory cache of active maintenance windows.

    Thread-safety: single writer (the refresh loop) + many readers. Python's GIL
    plus the atomic list swap in refresh_now keeps reads consistent.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        ttl_s: int | None = None,
    ) -> None:
        self._sf = session_factory
        self._ttl_s = ttl_s if ttl_s is not None else get_settings().maintenance_cache_ttl_s
        self._windows: list[_CompiledWindow] = []
        self._expires_at: float = 0.0

    def invalidate(self) -> None:
        """Force the next is_suppressed() call to refresh from DB."""
        self._expires_at = 0.0

    def refresh_now(self) -> None:
        session = self._sf()
        rows = session.query(MaintenanceWindow).filter_by(is_active=True).all()
        compiled: list[_CompiledWindow] = []
        for r in rows:
            types: tuple[str, ...] | None = None
            if r.suppress_alert_types is not None:
                try:
                    parsed = json.loads(r.suppress_alert_types)
                    if isinstance(parsed, list):
                        types = tuple(str(t) for t in parsed)
                except json.JSONDecodeError:
                    logger.warning(
                        "maintenance_window %s: malformed suppress_alert_types JSON",
                        r.window_id,
                    )
                    continue
            compiled.append(
                _CompiledWindow(
                    window_id=r.window_id,
                    scope_type=r.scope_type,
                    scope_id=r.scope_id,
                    schedule_type=r.schedule_type,
                    starts_at=r.starts_at,
                    ends_at=r.ends_at,
                    cron_expr=r.cron_expr,
                    duration_minutes=r.duration_minutes,
                    suppress_alert_types=types,
                )
            )
        self._windows = compiled
        self._expires_at = time.monotonic() + self._ttl_s

    def _maybe_refresh(self) -> None:
        if time.monotonic() >= self._expires_at:
            self.refresh_now()

    def is_suppressed(
        self,
        *,
        camera_id: int | None,
        zone_id: int | None,
        alert_type: str,
        event_ts: datetime,
    ) -> int | None:
        """Return window_id of the matching active window, or None."""
        self._maybe_refresh()
        for w in self._windows:
            if w.scope_type == "CAMERA":
                if camera_id is None or w.scope_id != camera_id:
                    continue
            elif w.scope_type == "ZONE":
                if zone_id is None or w.scope_id != zone_id:
                    continue
            else:
                continue

            if w.suppress_alert_types is not None and alert_type not in w.suppress_alert_types:
                continue

            if not self._covers(w, event_ts):
                continue
            return w.window_id
        return None

    @staticmethod
    def _covers(w: _CompiledWindow, ts: datetime) -> bool:
        if w.schedule_type == "ONE_TIME":
            if w.starts_at is None or w.ends_at is None:
                return False
            return w.starts_at <= ts <= w.ends_at
        if w.schedule_type == "RECURRING":
            if w.cron_expr is None or w.duration_minutes is None:
                return False
            try:
                it = croniter(w.cron_expr, ts)
            except (CroniterBadCronError, ValueError):
                logger.warning("maintenance_window %s: invalid cron %r", w.window_id, w.cron_expr)
                return False
            prev_fire: datetime = it.get_prev(datetime)
            end = prev_fire + timedelta(minutes=w.duration_minutes)
            return prev_fire <= ts <= end
        return False
