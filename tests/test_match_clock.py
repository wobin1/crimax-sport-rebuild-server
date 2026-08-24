"""Match clock display helpers."""

from datetime import datetime, timedelta, timezone

from app.core.match_clock import (
    PERIOD_FIRST_HALF,
    PERIOD_FULL_TIME,
    PERIOD_HALF_TIME,
    PERIOD_SECOND_HALF,
    clock_label,
    compute_elapsed_minute,
    enrich_clock_fields,
)


NOW = datetime(2026, 7, 26, 15, 30, tzinfo=timezone.utc)


def test_elapsed_minute_first_half():
    started = NOW - timedelta(minutes=23)
    assert (
        compute_elapsed_minute(PERIOD_FIRST_HALF, started, period_base_minute=0, now=NOW)
        == 23
    )


def test_elapsed_none_at_half_time():
    assert compute_elapsed_minute(PERIOD_HALF_TIME, NOW, now=NOW) is None


def test_clock_label_ht_ft():
    assert clock_label(PERIOD_HALF_TIME) == "HT"
    assert clock_label(PERIOD_FULL_TIME) == "FT"


def test_clock_label_regulation_and_stoppage():
    started = NOW - timedelta(minutes=47)
    assert (
        clock_label(PERIOD_FIRST_HALF, started, period_base_minute=0, now=NOW) == "45+2′"
    )


def test_clock_label_second_half():
    started = NOW - timedelta(minutes=10)
    assert (
        clock_label(
            PERIOD_SECOND_HALF, started, period_base_minute=45, now=NOW
        )
        == "55′"
    )


def test_enrich_clock_fields_mutates_fixture():
    started = NOW - timedelta(minutes=5)
    fixture = {
        "period": PERIOD_FIRST_HALF,
        "period_started_at": started,
        "period_base_minute": 0,
        "stoppage_minutes": None,
    }
    enrich_clock_fields(fixture, now=NOW)
    assert fixture["clock_minute"] == 5
    assert fixture["clock_label"] == "5′"
