from pydantic import BaseModel
from typing import Optional


class StandingRow(BaseModel):
    position: int
    club_id: str
    club_name: str
    club_short_name: Optional[str]
    club_logo_url: Optional[str]
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


class StandingsOut(BaseModel):
    tournament_id: str
    tournament_name: str
    season: str
    table: list[StandingRow]
