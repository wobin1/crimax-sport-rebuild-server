from pydantic import BaseModel, Field
from typing import Optional


class LineupPlayerIn(BaseModel):
    player_id: str
    slot_key: str
    offset_x: float = Field(default=0, ge=-12, le=12)
    offset_y: float = Field(default=0, ge=-12, le=12)


class LineupUpsert(BaseModel):
    formation: str
    players: list[LineupPlayerIn]


class LineupPlayerOut(BaseModel):
    player_id: str
    full_name: str
    jersey_number: Optional[int]
    photo_url: Optional[str]
    position: Optional[str]
    slot_key: str
    slot_label: str
    x: float
    y: float
    offset_x: float
    offset_y: float
    is_starter: bool = True


class LineupOut(BaseModel):
    id: str
    fixture_id: str
    club_id: str
    club_name: str
    club_short_name: Optional[str]
    club_logo_url: Optional[str]
    formation: str
    players: list[LineupPlayerOut]
    updated_at: str


class FixtureLineupsOut(BaseModel):
    fixture_id: str
    home: Optional[LineupOut] = None
    away: Optional[LineupOut] = None
