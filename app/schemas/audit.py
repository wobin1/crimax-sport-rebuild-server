from typing import Any, Optional

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    fixture_id: Optional[str] = None
    club_id: Optional[str] = None
    before_data: Optional[Any] = None
    after_data: Optional[Any] = None
    reason: Optional[str] = None
    ruleset: Optional[Any] = None
    request_id: Optional[str] = None
    created_at: str
