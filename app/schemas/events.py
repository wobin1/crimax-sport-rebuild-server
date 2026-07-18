from pydantic import BaseModel
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
    player_id: Optional[str] = None
    club_id: str
    event_type: EventType
    minute: int
    extra_time_minute: Optional[int] = None
    description: Optional[str] = None


class EventOut(BaseModel):
    id: str
    fixture_id: str
    player_id: Optional[str]
    player_name: Optional[str]
    club_id: Optional[str]
    club_name: Optional[str]
    event_type: str
    minute: int
    extra_time_minute: Optional[int]
    description: Optional[str]
    created_at: str
