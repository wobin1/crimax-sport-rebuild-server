"""International football match clock helpers (1H / HT / 2H / FT + stoppage)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


PERIOD_FIRST_HALF = "first_half"
PERIOD_HALF_TIME = "half_time"
PERIOD_SECOND_HALF = "second_half"
PERIOD_FULL_TIME = "full_time"

TICKING_PERIODS = frozenset({PERIOD_FIRST_HALF, PERIOD_SECOND_HALF})


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_elapsed_minute(
    period: Optional[str],
    period_started_at: Any,
    period_base_minute: int = 0,
    now: Optional[datetime] = None,
) -> Optional[int]:
    """Return current regulation-style minute while a half is ticking."""
    if period not in TICKING_PERIODS:
        return None
    started = _parse_ts(period_started_at)
    if not started:
        return None
    now = now or datetime.now(timezone.utc)
    elapsed = max(0, int((now - started).total_seconds() // 60))
    return period_base_minute + elapsed


def clock_label(
    period: Optional[str],
    period_started_at: Any = None,
    period_base_minute: int = 0,
    stoppage_minutes: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """
    Human clock label for boards/cards.
    Examples: 23′, 45+2′, HT, FT, 90+3′
    """
    if period == PERIOD_HALF_TIME:
        return "HT"
    if period == PERIOD_FULL_TIME:
        return "FT"
    if period not in TICKING_PERIODS:
        return None

    minute = compute_elapsed_minute(period, period_started_at, period_base_minute, now)
    if minute is None:
        return None

    regulation_end = 45 if period == PERIOD_FIRST_HALF else 90
    if minute <= regulation_end:
        return f"{minute}′"

    extra = minute - regulation_end
    if stoppage_minutes is not None and stoppage_minutes >= 0:
        # Still show counting extras; announced stoppage is informational.
        pass
    return f"{regulation_end}+{extra}′"


def enrich_clock_fields(fixture: dict, now: Optional[datetime] = None) -> dict:
    """Attach computed clock display fields onto a fixture dict (in place)."""
    period = fixture.get("period")
    base = int(fixture.get("period_base_minute") or 0)
    stoppage = fixture.get("stoppage_minutes")
    started = fixture.get("period_started_at")

    fixture["clock_minute"] = compute_elapsed_minute(period, started, base, now)
    fixture["clock_label"] = clock_label(period, started, base, stoppage, now)
    return fixture
