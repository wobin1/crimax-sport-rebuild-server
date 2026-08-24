from app.core.dependencies import PLATFORM_OPS_ROLES
from app.core.exceptions import BadRequestError, ForbiddenError, PolicyDecisionError
from app.core.match_rules import PolicyDecision, PolicyEvaluation


def enforce_policy(
    evaluation: PolicyEvaluation,
    *,
    actor: dict,
    acknowledged_warnings: list[str],
    override: bool,
    override_reason: str | None,
) -> list[PolicyDecision]:
    """Raise for unresolved decisions and return any overridden blocks."""
    blocks = [decision for decision in evaluation.decisions if decision.level == "block"]
    warnings = [
        decision
        for decision in evaluation.decisions
        if decision.level == "warn"
        and decision.code not in acknowledged_warnings
    ]

    if blocks:
        decision = blocks[0]
        can_override = actor["role"] in PLATFORM_OPS_ROLES
        if not override:
            raise PolicyDecisionError(
                level=decision.level,
                code=decision.code,
                message=decision.message,
                can_override=can_override,
            )
        if not can_override:
            raise ForbiddenError("Only platform administrators may override match rules.")
        if not override_reason or not override_reason.strip():
            raise BadRequestError("An override reason is required.")
        return blocks

    if override:
        if actor["role"] not in PLATFORM_OPS_ROLES:
            raise ForbiddenError("Only platform administrators may override match rules.")
        if not override_reason or not override_reason.strip():
            raise BadRequestError("An override reason is required.")

    if warnings:
        decision = warnings[0]
        raise PolicyDecisionError(
            level=decision.level,
            code=decision.code,
            message=decision.message,
        )

    return []
