from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class EventType(str, Enum):
    goal = "goal"
    own_goal = "own_goal"
    yellow_card = "yellow_card"
    red_card = "red_card"
    substitution_in = "substitution_in"
    substitution_out = "substitution_out"
    penalty_scored = "penalty_scored"
    penalty_missed = "penalty_missed"


class EventCreate(BaseModel):
    fixture_id: str
    client_event_id: Optional[str] = Field(None, min_length=1, max_length=64)
    player_id: Optional[str] = None
    club_id: str
    event_type: EventType
    minute: int = Field(ge=0, le=130)
    extra_time_minute: Optional[int] = Field(None, ge=0, le=30)
    description: Optional[str] = Field(None, max_length=1000)
    acknowledged_warnings: list[str] = Field(default_factory=list, max_length=10)
    override: bool = False
    override_reason: Optional[str] = Field(None, max_length=500)


class EventOut(BaseModel):
    id: str
    fixture_id: str
    client_event_id: Optional[str] = None
    source_event_id: Optional[str] = None
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    club_id: Optional[str] = None
    club_name: Optional[str] = None
    event_type: str
    minute: int
    extra_time_minute: Optional[int] = None
    description: Optional[str] = None
    created_at: str
