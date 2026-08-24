from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ExternalEntityType(str, Enum):
    club = "club"
    player = "player"
    fixture = "fixture"
    tournament = "tournament"
    user = "user"


class ExternalIdCreate(BaseModel):
    entity_type: ExternalEntityType
    entity_id: str
    provider: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=255)


class ExternalIdOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    provider: str
    external_id: str
    created_at: str
    updated_at: str
