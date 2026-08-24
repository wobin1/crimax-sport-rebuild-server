import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RulesetPreset = Literal["grassroots", "cup_formal", "custom"]


class RulesetConfig(BaseModel):
    """Tournament-level preset plus optional policy overrides."""

    model_config = ConfigDict(extra="forbid")

    preset: RulesetPreset = "grassroots"
    second_yellow_policy: Literal["warn", "auto_red"] | None = None
    events_after_ft: Literal["allow_with_warning", "block"] | None = None
    max_substitutions: int | None = Field(None, ge=0, le=12)
    require_player_on_events: bool | None = None
    clock_transitions: Literal["flexible", "strict"] | None = None
    duplicate_event_window_ms: int | None = Field(None, ge=0, le=30_000)


class MatchRuleset(BaseModel):
    """Fully resolved policy snapshot used by a fixture."""

    model_config = ConfigDict(extra="forbid")

    preset: RulesetPreset
    second_yellow_policy: Literal["warn", "auto_red"]
    events_after_ft: Literal["allow_with_warning", "block"]
    max_substitutions: int | None = Field(None, ge=0, le=12)
    require_player_on_events: bool
    clock_transitions: Literal["flexible", "strict"]
    duplicate_event_window_ms: int = Field(3000, ge=0, le=30_000)


RULESET_PRESETS: dict[str, dict] = {
    "grassroots": {
        "preset": "grassroots",
        "second_yellow_policy": "warn",
        "events_after_ft": "allow_with_warning",
        "max_substitutions": None,
        "require_player_on_events": False,
        "clock_transitions": "flexible",
        "duplicate_event_window_ms": 3000,
    },
    "cup_formal": {
        "preset": "cup_formal",
        "second_yellow_policy": "auto_red",
        "events_after_ft": "block",
        "max_substitutions": 5,
        "require_player_on_events": True,
        "clock_transitions": "strict",
        "duplicate_event_window_ms": 3000,
    },
}


def _as_dict(value: dict | str | None) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("Ruleset must be a JSON object.")
        return parsed
    return value


def resolve_ruleset(value: dict | str | None) -> MatchRuleset:
    config = RulesetConfig.model_validate(_as_dict(value))
    base_name = config.preset if config.preset in RULESET_PRESETS else "grassroots"
    resolved = dict(RULESET_PRESETS[base_name])
    for field, field_value in config.model_dump(exclude_none=True).items():
        resolved[field] = field_value
    resolved["preset"] = config.preset
    return MatchRuleset.model_validate(resolved)


def store_ruleset(value: RulesetConfig | dict | str | None) -> dict:
    """Validate and return the compact tournament-level representation."""
    if isinstance(value, RulesetConfig):
        config = value
    else:
        config = RulesetConfig.model_validate(_as_dict(value))
    # Validate that the compact config resolves before it reaches the database.
    resolve_ruleset(config.model_dump(exclude_none=True))
    return config.model_dump(exclude_none=True)
