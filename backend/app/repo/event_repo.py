from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.projection.events import standard_event
from app.repo._serialize import row_to_dict, rows_to_dicts


class EventRepo:
    """Append-only event sources — one SELECT per fact table, no SQL JOIN."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_issuance_event(self, identity_id: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, issue_date, custody_asset_code, created_at
                    FROM trust_product_issuance_asset_records
                    WHERE id = :identity_id
                    LIMIT 1
                    """
                ),
                {"identity_id": identity_id},
            ).fetchone()
        rec = row_to_dict(row)
        if not rec:
            return None
        rid = rec["id"]
        return standard_event(
            event_id=f"issuance:{rid}",
            event_type="ISSUANCE",
            occurred_at=rec.get("issue_date") or rec.get("created_at"),
            source="issuance",
            correlation_id=f"issuance:{rid}",
            recorded_at=rec.get("created_at"),
            source_ref=str(rid),
            payload_summary=f"Issuance {rec.get('custody_asset_code') or ''}".strip(),
        )

    def fetch_monitor_events(self, trust_asset_id: int, limit: int = 20) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, data_date, synced_at, overdue_days
                    FROM trust_asset_monitor_records
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY data_date DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        events = []
        for row in rows:
            rec = row_to_dict(row)
            mid = rec["id"]
            batch_key = f"monitor:{trust_asset_id}:{rec.get('data_date')}"
            events.append(
                standard_event(
                    event_id=f"monitor:{mid}",
                    event_type="MONITOR_IMPORTED",
                    occurred_at=rec.get("data_date") or rec.get("synced_at"),
                    source="monitor",
                    correlation_id=batch_key,
                    recorded_at=rec.get("synced_at"),
                    source_ref=str(mid),
                    payload_summary=f"Monitor as-of {rec.get('data_date')}",
                )
            )
        return events

    def fetch_repayment_events(self, trust_asset_id: int, limit: int = 50) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, repayment_date, created_at, actual_repayment_amount
                    FROM trust_repayment_detail_records
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY repayment_date DESC NULLS LAST, id DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        events = []
        for row in rows:
            rec = row_to_dict(row)
            rid = rec["id"]
            events.append(
                standard_event(
                    event_id=f"repayment:{rid}",
                    event_type="REPAYMENT_IMPORTED",
                    occurred_at=rec.get("repayment_date") or rec.get("created_at"),
                    source="repayment",
                    correlation_id=f"repayment_row:{rid}",
                    recorded_at=rec.get("created_at"),
                    source_ref=str(rid),
                    payload_summary=f"Repayment {rec.get('actual_repayment_amount')}",
                )
            )
        return events

    def fetch_risk_events(self, trust_asset_id: int, limit: int = 50) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, risk_type, generated_at, status
                    FROM risk_alerts
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY generated_at DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        events = []
        for row in rows:
            rec = row_to_dict(row)
            aid = rec["id"]
            events.append(
                standard_event(
                    event_id=f"risk:{aid}",
                    event_type="RISK_CREATED",
                    occurred_at=rec.get("generated_at"),
                    source="risk",
                    correlation_id=f"risk:{aid}",
                    recorded_at=rec.get("generated_at"),
                    source_ref=str(aid),
                    payload_summary=f"{rec.get('risk_type')} ({rec.get('status')})",
                )
            )
        return events

    def fetch_followup_events(self, trust_asset_id: int, limit: int = 50) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT e.id, e.status_snapshot, e.created_at, c.id AS case_id
                    FROM trust_overdue_followup_entries e
                    INNER JOIN trust_overdue_followup_cases c ON c.id = e.case_id
                    INNER JOIN trust_assets ta
                        ON ta.trust_product_id = c.trust_product_id
                       AND ta.asset_code = c.asset_code
                    WHERE ta.id = :trust_asset_id
                    ORDER BY e.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        events = []
        for row in rows:
            rec = row_to_dict(row)
            eid = rec["id"]
            events.append(
                standard_event(
                    event_id=f"followup:{eid}",
                    event_type="FOLLOWUP_CREATED",
                    occurred_at=rec.get("created_at"),
                    source="ops",
                    correlation_id=f"followup:case:{rec.get('case_id')}",
                    recorded_at=rec.get("created_at"),
                    source_ref=str(eid),
                    payload_summary=f"Follow-up {rec.get('status_snapshot')}",
                )
            )
        return events
