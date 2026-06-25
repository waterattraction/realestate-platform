"""Ops suggestions for overdue workbench — read-only, no DB writes."""

from sqlalchemy.engine import Engine

from app.service.overdue_ops_service import build_overdue_ops_service


def suggest_ops(engine: Engine, identity_id: int | None) -> dict | None:
    if identity_id is None:
        return None
    payload = build_overdue_ops_service(engine).get_ops(identity_id)
    if payload is None:
        return None

    cases = payload.get("cases") or []
    actions = payload.get("actions") or []
    sla_list = payload.get("sla") or []

    primary_case = cases[0] if cases else {}
    bucket = primary_case.get("stage") or primary_case.get("delinquency_bucket")
    overdue_days = primary_case.get("overdue_days")

    recommended_actions = []
    for action in actions:
        recommended_actions.append(
            {
                "action_type": action.get("action_type"),
                "label": action.get("label") or action.get("action_type"),
                "priority": action.get("priority"),
                "due_date": action.get("due_date"),
            }
        )

    sla_summary = None
    if sla_list:
        first = sla_list[0]
        sla_summary = {
            "due_date": first.get("due_date"),
            "is_breached": first.get("is_breached"),
            "days_remaining": first.get("days_remaining"),
        }

    return {
        "bucket": bucket,
        "overdue_days": overdue_days,
        "risk_level": primary_case.get("risk_level"),
        "recommended_actions": recommended_actions,
        "sla": sla_summary,
        "cases": cases,
        "engine": payload.get("engine"),
    }
