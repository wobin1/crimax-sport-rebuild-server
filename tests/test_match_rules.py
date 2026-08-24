from datetime import datetime, timezone

import pytest

from app.core.exceptions import ForbiddenError, PolicyDecisionError
from app.core.match_rules import evaluate_clock, evaluate_event, evaluate_event_deletion
from app.core.policy import enforce_policy
from app.core.rulesets import resolve_ruleset


PLATFORM_ADMIN = {"role": "platform_admin"}
CLUB_MANAGER = {"role": "club_manager"}


def test_formal_second_yellow_auto_red_and_player_requirement():
    ruleset = resolve_ruleset({"preset": "cup_formal"})
    evaluation = evaluate_event(
        {
            "event_type": "yellow_card",
            "player_id": "player-1",
            "club_id": "club-1",
            "minute": 50,
            "extra_time_minute": None,
        },
        {"status": "live", "period": "second_half"},
        [
            {
                "event_type": "yellow_card",
                "player_id": "player-1",
                "club_id": "club-1",
                "minute": 20,
                "extra_time_minute": None,
                "created_at": "2026-07-26T12:00:00+00:00",
            }
        ],
        ruleset,
        now=datetime(2026, 7, 26, 13, 0, tzinfo=timezone.utc),
    )

    assert evaluation.auto_red is True
    assert evaluation.decisions == []


def test_grassroots_second_yellow_requires_acknowledgement():
    ruleset = resolve_ruleset({"preset": "grassroots"})
    evaluation = evaluate_event(
        {
            "event_type": "yellow_card",
            "player_id": "player-1",
            "club_id": "club-1",
            "minute": 50,
            "extra_time_minute": None,
        },
        {"status": "live", "period": "second_half"},
        [
            {
                "event_type": "yellow_card",
                "player_id": "player-1",
                "club_id": "club-1",
                "minute": 20,
                "extra_time_minute": None,
                "created_at": "2026-07-26T12:00:00+00:00",
            }
        ],
        ruleset,
        now=datetime(2026, 7, 26, 13, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(PolicyDecisionError) as exc:
        enforce_policy(
            evaluation,
            actor=CLUB_MANAGER,
            acknowledged_warnings=[],
            override=False,
            override_reason=None,
        )
    assert exc.value.detail["code"] == "second_yellow"

    enforce_policy(
        evaluation,
        actor=CLUB_MANAGER,
        acknowledged_warnings=["second_yellow"],
        override=False,
        override_reason=None,
    )


def test_formal_block_requires_platform_override_and_reason():
    ruleset = resolve_ruleset({"preset": "cup_formal"})
    evaluation = evaluate_event(
        {
            "event_type": "goal",
            "player_id": "player-1",
            "club_id": "club-1",
            "minute": 91,
            "extra_time_minute": None,
        },
        {"status": "completed", "period": "full_time"},
        [],
        ruleset,
    )

    with pytest.raises(PolicyDecisionError) as exc:
        enforce_policy(
            evaluation,
            actor=CLUB_MANAGER,
            acknowledged_warnings=[],
            override=False,
            override_reason=None,
        )
    assert exc.value.detail["can_override"] is False

    with pytest.raises(ForbiddenError):
        enforce_policy(
            evaluation,
            actor=CLUB_MANAGER,
            acknowledged_warnings=[],
            override=True,
            override_reason="Official correction",
        )

    overridden = enforce_policy(
        evaluation,
        actor=PLATFORM_ADMIN,
        acknowledged_warnings=[],
        override=True,
        override_reason="Official correction",
    )
    assert {decision.code for decision in overridden} == {"events_after_ft"}


def test_clock_transition_is_warning_or_block_by_preset():
    fixture = {"status": "live", "period": "first_half"}

    flexible = evaluate_clock("start_2h", fixture, resolve_ruleset({"preset": "grassroots"}))
    strict = evaluate_clock("start_2h", fixture, resolve_ruleset({"preset": "cup_formal"}))

    assert flexible.decisions[0].level == "warn"
    assert strict.decisions[0].level == "block"


def test_deletion_after_full_time_uses_tournament_policy():
    fixture = {"status": "completed", "period": "full_time"}

    flexible = evaluate_event_deletion(
        fixture, resolve_ruleset({"preset": "grassroots"})
    )
    strict = evaluate_event_deletion(
        fixture, resolve_ruleset({"preset": "cup_formal"})
    )

    assert flexible.decisions[0].level == "warn"
    assert strict.decisions[0].level == "block"


def test_custom_ruleset_resolves_overrides():
    ruleset = resolve_ruleset(
        {
            "preset": "custom",
            "max_substitutions": 7,
            "require_player_on_events": True,
        }
    )

    assert ruleset.preset == "custom"
    assert ruleset.max_substitutions == 7
    assert ruleset.require_player_on_events is True
    assert ruleset.clock_transitions == "flexible"
