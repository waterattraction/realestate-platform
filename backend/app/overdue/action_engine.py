"""Action Engine — stage → action_type (deterministic mapping)."""

from datetime import timedelta

from app.overdue.rules import STAGE_ACTION, STAGE_SLA_DAYS, utc_today


class ActionEngine:
    """Action = rule-mapped executable task per case."""

    def build_actions(self, cases: list[dict]) -> list[dict]:
        actions: list[dict] = []
        today = utc_today()
        for case in cases:
            stage = case["stage"]
            action_type = STAGE_ACTION[stage]
            case_id = case["case_id"]
            sla_days = STAGE_SLA_DAYS[stage]
            due = today + timedelta(days=sla_days)
            actions.append(
                {
                    "action_id": f"action:{case_id}:{action_type}",
                    "case_id": case_id,
                    "identity_id": case["identity_id"],
                    "type": action_type,
                    "status": "todo",
                    "due_date": due.isoformat(),
                    "stage": stage,
                }
            )
        return actions
