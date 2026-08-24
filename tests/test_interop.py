import json

import pytest

from app.core.exceptions import BadRequestError, PolicyDecisionError, TooManyRequestsError
from app.core.websocket import stamp_payload
from app.main import _problem, http_exception_handler


def test_problem_json_preserves_string_detail():
    response = _problem(status_code=400, title="Bad Request", detail="Nope")
    assert response.media_type == "application/problem+json"
    body = json.loads(response.body.decode())
    assert body["detail"] == "Nope"
    assert body["message"] == "Nope"
    assert body["status"] == 400


def test_policy_decision_error_is_structured():
    error = PolicyDecisionError(
        level="block",
        code="events_after_ft",
        message="Blocked",
        can_override=True,
    )
    assert error.status_code == 409
    assert error.detail["type"] == "policy_decision"
    assert error.detail["can_override"] is True


def test_bad_request_error_keeps_legacy_string_detail():
    error = BadRequestError("Invalid fixture")
    assert error.detail == "Invalid fixture"


def test_stamp_payload_idempotent_for_server_time():
    stamped = stamp_payload({"type": "event", "server_time": "fixed"})
    assert stamped["server_time"] == "fixed"


def test_problem_json_preserves_structured_policy_detail():
    detail = {
        "type": "policy_decision",
        "level": "warn",
        "code": "second_yellow",
        "message": "Second yellow requires acknowledgement.",
        "can_override": False,
    }
    response = _problem(status_code=409, title="Conflict", detail=detail)
    body = json.loads(response.body.decode())
    assert body["detail"] == detail
    assert body["message"] == detail["message"]
    assert body["type"] == "policy_decision"
    assert body["code"] == "second_yellow"
    assert body["can_override"] is False


@pytest.mark.asyncio
async def test_http_handler_maps_429_title():
    exc = TooManyRequestsError("Too many requests. Try again in 60 seconds.")
    response = await http_exception_handler(None, exc)
    body = json.loads(response.body.decode())
    assert response.status_code == 429
    assert body["title"] == "Too Many Requests"
    assert "60 seconds" in body["detail"]
