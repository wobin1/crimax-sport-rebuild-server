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
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    club_id: Optional[str] = None
    club_name: Optional[str] = None
    event_type: str
    minute: int
    extra_time_minute: Optional[int] = None
    description: Optional[str] = None
    created_at: str
