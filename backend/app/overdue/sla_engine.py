"""SLA Engine — independent SLA evaluation per case."""

from datetime import date, datetime, timedelta, timezone

from app.overdue.rules import STAGE_SLA_DAYS, utc_today


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


class SLAEngine:
    """SLA is evaluated independently from case/action storage."""

    def evaluate(self, cases: list[dict], *, as_of: date | None = None) -> list[dict]:
        today = as_of or utc_today()
        records: list[dict] = []
        for case in cases:
            stage = case["stage"]
            sla_days = STAGE_SLA_DAYS[stage]
            opened = _parse_date(case.get("opened_at")) or today
            sla_due = opened + timedelta(days=sla_days)
            breach = today > sla_due
            records.append(
                {
                    "case_id": case["case_id"],
                    "identity_id": case["identity_id"],
                    "stage": stage,
                    "sla_days": sla_days,
                    "sla_due": sla_due.isoformat(),
                    "breach": breach,
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return records
