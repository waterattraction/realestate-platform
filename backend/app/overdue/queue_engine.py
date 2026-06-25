"""Queue Engine — operational sort view (rule-based priority, not AI)."""

from app.overdue.rules import STAGE_WEIGHT


class QueueEngine:
    """
    priority = stage_weight + sla_breach_boost + amount_weight
    """

    def build_queue(
        self,
        cases: list[dict],
        actions: list[dict],
        sla_records: list[dict],
    ) -> list[dict]:
        action_by_case = {a["case_id"]: a for a in actions}
        sla_by_case = {s["case_id"]: s for s in sla_records}

        queue: list[dict] = []
        for case in cases:
            case_id = case["case_id"]
            action = action_by_case.get(case_id, {})
            sla = sla_by_case.get(case_id, {})
            stage = case["stage"]
            breach = bool(sla.get("breach"))
            amount = float(case.get("amount") or 0)

            stage_weight = STAGE_WEIGHT.get(stage, 0)
            sla_breach_boost = 1000 if breach else 0
            amount_weight = min(int(amount / 10_000), 99)

            priority = stage_weight + sla_breach_boost + amount_weight

            queue.append(
                {
                    "case_id": case_id,
                    "identity_id": case["identity_id"],
                    "custody_asset_code": case.get("custody_asset_code"),
                    "stage": stage,
                    "amount": amount,
                    "priority": priority,
                    "stage_weight": stage_weight,
                    "sla_breach": breach,
                    "sla_due": sla.get("sla_due"),
                    "action_type": action.get("type"),
                    "action_status": action.get("status"),
                    "due_date": action.get("due_date"),
                }
            )

        queue.sort(
            key=lambda item: (
                -item["priority"],
                -item["amount"],
                item["case_id"],
            )
        )
        return queue
