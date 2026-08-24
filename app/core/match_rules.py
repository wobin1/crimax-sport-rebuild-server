from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from app.core.rulesets import MatchRuleset


DecisionLevel = Literal["warn", "block"]


@dataclass(frozen=True)
class PolicyDecision:
    level: DecisionLevel
    code: str
    message: str


@dataclass
class PolicyEvaluation:
    decisions: list[PolicyDecision] = field(default_factory=list)
    auto_red: bool = False


def evaluate_event(
    payload: dict,
    fixture: dict,
    events: list[dict],
    ruleset: MatchRuleset,
    *,
    now: datetime | None = None,
) -> PolicyEvaluation:
    result = PolicyEvaluation()
    event_type = payload["event_type"]
    player_id = payload.get("player_id")

    if fixture.get("status") == "completed" or fixture.get("period") == "full_time":
        if ruleset.events_after_ft == "block":
            result.decisions.append(
                PolicyDecision(
                    "block",
                    "events_after_ft",
                    "This tournament does not allow events after full-time.",
                )
            )
        else:
            result.decisions.append(
                PolicyDecision(
                    "warn",
                    "events_after_ft",
                    "This match is at full-time. Confirm that this is a correction.",
                )
            )

    if ruleset.require_player_on_events and not player_id:
        result.decisions.append(
            PolicyDecision(
                "block",
                "player_required",
                "This tournament requires a player for every match event.",
            )
        )

    if event_type == "yellow_card" and player_id:
        yellow_count = sum(
            1
            for event in events
            if event.get("player_id") == player_id
            and event.get("event_type") == "yellow_card"
        )
        if yellow_count >= 1:
            if ruleset.second_yellow_policy == "auto_red":
                result.auto_red = True
            else:
                result.decisions.append(
                    PolicyDecision(
                        "warn",
                        "second_yellow",
                        "This is the player's second yellow card. Confirm before recording it.",
                    )
                )

    if event_type == "substitution_in" and ruleset.max_substitutions is not None:
        substitutions = sum(
            1
            for event in events
            if event.get("club_id") == payload.get("club_id")
            and event.get("event_type") == "substitution_in"
        )
        if substitutions >= ruleset.max_substitutions:
            result.decisions.append(
                PolicyDecision(
                    "block",
                    "substitution_limit",
                    f"This tournament allows at most {ruleset.max_substitutions} substitutions.",
                )
            )

    duplicate = _recent_duplicate(
        payload,
        events,
        window_ms=ruleset.duplicate_event_window_ms,
        now=now or datetime.now(timezone.utc),
    )
    if duplicate:
        result.decisions.append(
            PolicyDecision(
                "warn",
                "possible_duplicate",
                "A matching event was just recorded. Confirm that this is a separate event.",
            )
        )

    return result


def evaluate_clock(
    action: str,
    fixture: dict,
    ruleset: MatchRuleset,
) -> PolicyEvaluation:
    current_period = fixture.get("period")
    expected_period = {
        "start_1h": None,
        "ht": "first_half",
        "start_2h": "half_time",
        "ft": "second_half",
    }.get(action)

    if action not in ("start_1h", "ht", "start_2h", "ft"):
        return PolicyEvaluation()

    valid = current_period == expected_period
    if action == "start_1h":
        valid = valid and fixture.get("status") == "scheduled"
    if valid:
        return PolicyEvaluation()

    level: DecisionLevel = (
        "block" if ruleset.clock_transitions == "strict" else "warn"
    )
    return PolicyEvaluation(
        decisions=[
            PolicyDecision(
                level,
                "invalid_clock_transition",
                f"Cannot apply {action} while the match period is {current_period or 'not started'}.",
            )
        ]
    )


def evaluate_event_deletion(
    fixture: dict,
    ruleset: MatchRuleset,
) -> PolicyEvaluation:
    if fixture.get("status") != "completed" and fixture.get("period") != "full_time":
        return PolicyEvaluation()
    level: DecisionLevel = (
        "block" if ruleset.events_after_ft == "block" else "warn"
    )
    return PolicyEvaluation(
        decisions=[
            PolicyDecision(
                level,
                "delete_after_ft",
                "This match is at full-time. Confirm this event correction.",
            )
        ]
    )


def _recent_duplicate(
    payload: dict,
    events: list[dict],
    *,
    window_ms: int,
    now: datetime,
) -> bool:
    if window_ms <= 0:
        return False
    fields = ("club_id", "player_id", "event_type", "minute", "extra_time_minute")
    for event in reversed(events):
        if not all(event.get(field) == payload.get(field) for field in fields):
            continue
        created_at = _parse_time(event.get("created_at"))
        if created_at is None:
            continue
        age_ms = (now - created_at).total_seconds() * 1000
        if 0 <= age_ms <= window_ms:
            return True
    return False


def _parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
