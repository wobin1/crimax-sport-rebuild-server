from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from app.core.rulesets import MatchRuleset


class FixtureStatus(str, Enum):
    scheduled = "scheduled"
    live = "live"
    completed = "completed"
    postponed = "postponed"
    cancelled = "cancelled"


class MatchPeriod(str, Enum):
    first_half = "first_half"
    half_time = "half_time"
    second_half = "second_half"
    full_time = "full_time"


class ClockAction(str, Enum):
    start_1h = "start_1h"
    ht = "ht"
    start_2h = "start_2h"
    ft = "ft"
    nudge = "nudge"
    set_stoppage = "set_stoppage"


class FixtureCreate(BaseModel):
    tournament_id: Optional[str] = None
    home_club_id: str
    away_club_id: str
    match_date: str
    match_time: Optional[str] = None
    venue: Optional[str] = None
    round: Optional[str] = None


class FixtureUpdate(BaseModel):
    match_date: Optional[str] = None
    match_time: Optional[str] = None
    venue: Optional[str] = None
    round: Optional[str] = None
    status: Optional[FixtureStatus] = None


class ClockUpdate(BaseModel):
    action: ClockAction
    minute: Optional[int] = Field(None, ge=0, le=130)
    stoppage_minutes: Optional[int] = Field(None, ge=0, le=30)
    acknowledged_warnings: list[str] = Field(default_factory=list, max_length=10)
    override: bool = False
    override_reason: Optional[str] = Field(None, max_length=500)


class ClubSummary(BaseModel):
    id: str
    name: str
    short_name: Optional[str]
    logo_url: Optional[str]


class GoalScorerOut(BaseModel):
    player_name: Optional[str]
    minute: int
    extra_time_minute: Optional[int] = None
    is_own_goal: bool = False
    club_id: str


class FixtureOut(BaseModel):
    id: str
    tournament_id: str
    tournament_name: str
    home_club: ClubSummary
    away_club: ClubSummary
    match_date: str
    match_time: Optional[str]
    venue: Optional[str]
    round: Optional[str]
    status: str
    home_score: int
    away_score: int
    period: Optional[str] = None
    period_started_at: Optional[str] = None
    period_base_minute: int = 0
    stoppage_minutes: Optional[int] = None
    clock_minute: Optional[int] = None
    clock_label: Optional[str] = None
    ruleset_snapshot: Optional[MatchRuleset] = None
    goal_scorers: dict[str, list[GoalScorerOut]] = Field(
        default_factory=lambda: {"home": [], "away": []}
    )
    created_at: str
    updated_at: str
