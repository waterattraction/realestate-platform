"""Overdue workbench — single read path: get_detail()."""

from sqlalchemy.engine import Engine

DEFAULT_DELINQUENCY_BUCKET = "M2_PLUS"

from app.repo.followup_repo import FollowupRepo
from app.repo.issuance_repo import IssuanceRepo
from app.repo.marks_repo import MarksRepo
from app.repo.monitor_repo import MonitorRepo
from app.repo.repayment_repo import RepaymentRepo
from app.service import checks_service
from app.service.ops_service import suggest_ops


class OverdueWorkbenchService:
    def __init__(self, engine: Engine):
        self._engine = engine
        self._issuance = IssuanceRepo(engine)
        self._monitor = MonitorRepo(engine)
        self._repayment = RepaymentRepo(engine)
        self._followup = FollowupRepo(engine)
        self._marks = MarksRepo(engine)

    def get_detail(
        self,
        *,
        trust_product_id: int | None = None,
        custody_asset_code: str | None = None,
        trust_asset_id: int | None = None,
        data_date: str | None = None,
    ) -> dict:
        empty = {
            "trust_product_id": trust_product_id,
            "custody_asset_code": custody_asset_code,
            "identity_id": None,
            "data_date": data_date,
            "summary": None,
            "issuance_records": [],
            "repayment": {"total_repaid": 0.0, "items": [], "recent_repayment_date": None},
            "monitor": {"custody": None, "splits": []},
            "checks": None,
            "trust_mark": None,
            "ops": None,
            "followup_case": None,
            "timeline": [],
            "queue": [],
            "selected_asset_id": None,
            "detail": None,
        }

        if trust_product_id is None or not custody_asset_code:
            return empty

        resolved_date = self._monitor.resolve_latest_data_date(trust_product_id, data_date)
        if resolved_date is None:
            return empty

        issuance_records = self._issuance.fetch_by_product_custody(
            trust_product_id, custody_asset_code
        )
        identity_id = issuance_records[0]["id"] if issuance_records else None

        splits_raw = self._monitor.fetch_splits_by_custody(
            trust_product_id, custody_asset_code, resolved_date
        )
        if not splits_raw:
            empty["data_date"] = resolved_date
            empty["issuance_records"] = issuance_records
            empty["trust_mark"] = self._marks.fetch_mark(
                trust_product_id, custody_asset_code, resolved_date
            )
            empty["ops"] = suggest_ops(self._engine, identity_id)
            return empty

        repayment_total = self._repayment.sum_by_product_custody(
            trust_product_id, custody_asset_code
        )
        repayment_items = self._repayment.fetch_by_product_custody(
            trust_product_id, custody_asset_code
        )

        trust_asset_ids = [int(s["trust_asset_id"]) for s in splits_raw]
        followup_history = self._followup.fetch_by_trust_asset_ids(trust_asset_ids)

        queue = []
        for row in splits_raw:
            remaining = float(row.get("remaining_amount") or 0)
            is_es = checks_service.is_es_closed(remaining)
            od_val = None if is_es else int(row.get("overdue_days") or 0)
            bucket = (
                "ES"
                if is_es
                else checks_service.calc_risk_level(int(row.get("overdue_days") or 0), remaining)
            )
            detail_total = repayment_total
            checks = checks_service.run_asset_checks(
                float(row.get("initial_transfer_amount") or 0),
                float(row.get("repaid_amount") or 0),
                remaining,
                detail_total,
            )
            active = self._followup.fetch_active_by_trust_asset_id(int(row["trust_asset_id"]))
            queue.append(
                {
                    "trust_asset_id": row["trust_asset_id"],
                    "asset_code": row.get("asset_code"),
                    "custody_asset_code": row.get("custody_asset_code"),
                    "source_asset_code": row.get("source_asset_code"),
                    "asset_name": row.get("asset_name"),
                    "trust_product_id": row.get("trust_product_id"),
                    "trust_product_name": row.get("trust_product_name"),
                    "data_date": str(row.get("data_date")),
                    "overdue_days": od_val,
                    "risk_score": row.get("risk_score"),
                    "risk_level": "ES" if is_es else row.get("risk_level"),
                    "delinquency_bucket": bucket,
                    "last_payment_date": (
                        str(row["last_payment_date"]) if row.get("last_payment_date") else None
                    ),
                    "initial_transfer_amount": float(row.get("initial_transfer_amount") or 0),
                    "repaid_amount": float(row.get("repaid_amount") or 0),
                    "remaining_amount": remaining,
                    "checks": checks,
                    "followup_id": active.get("id") if active else None,
                    "followup_status": active.get("status") if active else None,
                    "followup_owner": active.get("owner_name") if active else None,
                    "followup_reason": active.get("overdue_reason") if active else None,
                    "followup_plan": active.get("follow_up_plan") if active else None,
                    "followup_feedback": active.get("trust_feedback") if active else None,
                    "followup_last_at": active.get("last_follow_up_at") if active else None,
                    "has_follow_up": active is not None,
                }
            )

        selected_id = trust_asset_id
        if selected_id is None and queue:
            selected_id = queue[0]["trust_asset_id"]
        elif selected_id is not None and not any(q["trust_asset_id"] == selected_id for q in queue):
            selected_id = queue[0]["trust_asset_id"] if queue else None

        detail = next((q for q in queue if q["trust_asset_id"] == selected_id), None)
        if detail:
            asset_history = [f for f in followup_history if f["trust_asset_id"] == selected_id]
            custody_history = [
                f for f in followup_history if f["trust_asset_id"] in trust_asset_ids
            ]
            detail = {
                **detail,
                "followup_history": asset_history,
                "custody_followup_history": custody_history,
            }

        custody_checks = checks_service.run_custody_checks(queue, repayment_total)

        custody_agg = {
            "initial_transfer_amount": sum(q["initial_transfer_amount"] for q in queue),
            "repaid_amount": sum(q["repaid_amount"] for q in queue),
            "remaining_amount": sum(q["remaining_amount"] for q in queue),
            "overdue_days": max(
                (q["overdue_days"] for q in queue if q["overdue_days"] is not None),
                default=None,
            ),
            "split_count": len(queue),
        }
        if queue:
            remaining_sum = custody_agg["remaining_amount"]
            if checks_service.is_es_closed(remaining_sum):
                custody_agg["delinquency_bucket"] = "ES"
            else:
                custody_agg["delinquency_bucket"] = checks_service.calc_risk_level(
                    int(custody_agg["overdue_days"] or 0),
                    remaining_sum,
                )

        recent_repay = None
        if repayment_items:
            recent_repay = repayment_items[0].get("repayment_date")

        case_row = self._followup.fetch_case_by_custody(
            trust_product_id, custody_asset_code, active_only=False
        )
        entry_list: list[dict] = []
        if case_row:
            entry_list = self._followup.fetch_entries_by_case_id(int(case_row["id"]))

        entry_ids = [int(e["id"]) for e in entry_list]
        attachments = self._followup.fetch_attachments_by_entry_ids(entry_ids)
        attachments_by_entry: dict[int, list] = {}
        for att in attachments:
            attachments_by_entry.setdefault(int(att["entry_id"]), []).append(att)

        timeline = _build_timeline(
            repayment_items, followup_history, entry_list, attachments_by_entry
        )
        trust_mark = self._marks.fetch_mark(
            trust_product_id, custody_asset_code, resolved_date
        )
        ops = suggest_ops(self._engine, identity_id)

        primary = detail or (queue[0] if queue else {})
        has_check_anomaly = False
        if custody_checks:
            has_check_anomaly = not (
                custody_checks["balance_equation"]["passed"]
                and custody_checks["cross_sheet_repayment"]["passed"]
            )
        summary = {
            "delinquency_bucket": custody_agg.get("delinquency_bucket")
            or primary.get("delinquency_bucket"),
            "overdue_days": custody_agg.get("overdue_days")
            if custody_agg.get("overdue_days") is not None
            else primary.get("overdue_days"),
            "risk_level": primary.get("risk_level"),
            "risk_score": primary.get("risk_score"),
            "trust_product_name": primary.get("trust_product_name"),
            "remaining_amount": custody_agg.get("remaining_amount"),
            "repaid_amount": custody_agg.get("repaid_amount"),
            "initial_transfer_amount": custody_agg.get("initial_transfer_amount"),
            "split_count": custody_agg.get("split_count"),
            "internal_status": (trust_mark or {}).get("internal_status"),
            "has_check_anomaly": has_check_anomaly,
        }

        followup_case = self._followup.fetch_case_by_custody(
            trust_product_id, custody_asset_code, active_only=True
        ) or case_row

        last_follow_up_at = None
        last_follow_up_owner = None
        if followup_case:
            last_follow_up_at = followup_case.get("last_follow_up_at")
            last_follow_up_owner = followup_case.get("owner_name")
        if entry_list:
            if not last_follow_up_at:
                last_follow_up_at = entry_list[0].get("created_at")
            if not last_follow_up_owner:
                last_follow_up_owner = entry_list[0].get("owner_name")

        summary["last_follow_up_at"] = (
            str(last_follow_up_at) if last_follow_up_at is not None else None
        )
        summary["last_follow_up_owner"] = last_follow_up_owner

        product_queue = self.get_product_queue(trust_product_id, resolved_date)

        return {
            "trust_product_id": trust_product_id,
            "custody_asset_code": custody_asset_code,
            "identity_id": identity_id,
            "data_date": resolved_date,
            "summary": summary,
            "issuance_records": issuance_records,
            "repayment": {
                "total_repaid": repayment_total,
                "items": repayment_items,
                "recent_repayment_date": recent_repay,
                "period_count": len(repayment_items),
            },
            "monitor": {"custody": custody_agg, "splits": queue},
            "checks": custody_checks,
            "trust_mark": trust_mark,
            "ops": ops,
            "followup_case": followup_case,
            "timeline": timeline,
            "product_queue": product_queue,
            "queue": queue,
            "selected_asset_id": selected_id,
            "detail": detail,
        }

    def get_asset_list(
        self,
        *,
        trust_product_id: int | None,
        data_date: str | None = None,
    ) -> dict:
        """Return asset_list dict (asset_code-based) for render.py."""
        resolved_date = self._monitor.resolve_latest_data_date(trust_product_id, data_date)
        if resolved_date is None:
            return {"data_date": None, "items": []}

        rows = self._monitor.fetch_asset_queue(trust_product_id, resolved_date)
        items = []
        for row in rows:
            ac = row["asset_code"]
            pid = row["trust_product_id"]
            custodies = list(row.get("custody_asset_codes") or [])
            remaining = float(row.get("remaining_amount") or 0)
            overdue_days = row.get("overdue_days")

            if checks_service.is_es_closed(remaining):
                bucket = "ES"
            else:
                bucket = checks_service.calc_risk_level(int(overdue_days or 0), remaining)

            followup_count = sum(
                self._followup.count_entries_by_custody(pid, c) for c in custodies
            )
            primary_custody = custodies[0] if custodies else ac
            internal_status = self._marks.fetch_mark(
                pid, primary_custody, resolved_date
            ).get("internal_status")

            items.append(
                {
                    "asset_code": ac,
                    "trust_product_id": pid,
                    "trust_product_name": row.get("trust_product_name"),
                    "overdue_days": overdue_days,
                    "remaining_amount": remaining,
                    "delinquency_bucket": bucket,
                    "followup_count": followup_count,
                    "internal_status": internal_status,
                    "custody_asset_codes": custodies,
                    "primary_custody_asset_code": primary_custody,
                }
            )
        return {"data_date": resolved_date, "items": items}

    def get_workbench_page_dto(
        self,
        *,
        trust_product_id: int | None = None,
        asset_code: str | None = None,
        custody_asset_code: str | None = None,
        delinquency_bucket: str = "M2_PLUS",
        data_date: str | None = None,
        list_product_id: int | None = None,
        list_product_scope_explicit: bool = False,
        trust_asset_id: int | None = None,
    ) -> dict:
        """Build full DTO expected by render.py (asset_code-centric)."""
        # Resolve effective custody: use provided value, or fall back to asset_code
        effective_custody = custody_asset_code or asset_code
        effective_asset_code = asset_code or custody_asset_code

        filters = {
            "trust_product_id": trust_product_id,
            "delinquency_bucket": delinquency_bucket,
            "list_product_id": list_product_id,
            "list_product_scope_explicit": list_product_scope_explicit,
        }

        # Get detail DTO using existing method
        old = self.get_detail(
            trust_product_id=trust_product_id,
            custody_asset_code=effective_custody,
            trust_asset_id=trust_asset_id,
            data_date=data_date,
        )
        resolved_date = old.get("data_date")

        # Determine list scope product id
        list_pid = list_product_id if list_product_scope_explicit else trust_product_id

        # Get asset list (may be slow on large datasets; acceptable for now)
        asset_list = self.get_asset_list(
            trust_product_id=list_pid,
            data_date=resolved_date,
        )

        # Collect custody codes from monitor splits
        old_queue = old.get("queue") or []
        custody_codes = list(
            dict.fromkeys(
                q.get("custody_asset_code")
                for q in old_queue
                if q.get("custody_asset_code")
            )
        )
        primary_custody = custody_codes[0] if custody_codes else effective_custody

        # Fetch issuance records for ALL custody codes under this asset
        all_issuance: list[dict] = []
        if trust_product_id and custody_codes:
            all_issuance = self._issuance.fetch_by_product_custodies(
                trust_product_id, custody_codes
            )
        elif trust_product_id and effective_custody:
            all_issuance = self._issuance.fetch_by_product_custodies(
                trust_product_id, [effective_custody]
            )
        else:
            all_issuance = old.get("issuance_records") or []

        # Build nested asset dict for render.py
        asset_dict: dict = {}
        if effective_asset_code or effective_custody:
            asset_dict = {
                "asset_code": effective_asset_code,
                "custody_asset_codes": custody_codes,
                "primary_custody_asset_code": primary_custody,
                "selected_trust_asset_id": old.get("selected_asset_id"),
                "selected_split": old.get("detail"),
                "summary": old.get("summary"),
                "checks": old.get("checks"),
                "issuance_records": all_issuance,
                "repayment": old.get("repayment") or {},
                "monitor": old.get("monitor") or {},
                "trust_mark": old.get("trust_mark"),
                "timeline": old.get("timeline") or [],
                "ops": old.get("ops"),
                "followup_case": old.get("followup_case"),
            }

        return {
            "trust_product_id": trust_product_id,
            "asset_code": effective_asset_code,
            "primary_custody_asset_code": primary_custody,
            "custody_asset_codes": custody_codes,
            "identity_id": old.get("identity_id"),
            "data_date": resolved_date,
            "filters": filters,
            "asset": asset_dict,
            "asset_list": asset_list,
        }

    def get_product_queue(
        self,
        trust_product_id: int,
        data_date: str | None = None,
    ) -> dict:
        resolved_date = self._monitor.resolve_latest_data_date(trust_product_id, data_date)
        if resolved_date is None:
            return {"trust_product_id": trust_product_id, "data_date": None, "items": []}

        rows = self._monitor.fetch_custody_queue(trust_product_id, resolved_date)
        items = []
        for row in rows:
            custody = row["custody_asset_code"]
            items.append(
                {
                    "custody_asset_code": custody,
                    "overdue_days": row.get("overdue_days"),
                    "remaining_amount": float(row.get("remaining_amount") or 0),
                    "split_count": row.get("split_count"),
                    "followup_count": self._followup.count_entries_by_custody(
                        trust_product_id, custody
                    ),
                    "internal_status": self._marks.fetch_mark(
                        trust_product_id, custody, resolved_date
                    ).get("internal_status"),
                }
            )
        return {
            "trust_product_id": trust_product_id,
            "data_date": resolved_date,
            "items": items,
        }


def _migrated_legacy_followup_ids(entries: list[dict]) -> set[int]:
    ids: set[int] = set()
    for entry in entries:
        note = entry.get("note") or ""
        if not note.startswith("legacy_followup_id:"):
            continue
        raw = note.removeprefix("legacy_followup_id:").strip()
        head = raw.split(None, 1)[0] if raw else ""
        if head.isdigit():
            ids.add(int(head))
    return ids


def _build_timeline(
    repayment_items: list[dict],
    legacy_followups: list[dict],
    entries: list[dict],
    attachments_by_entry: dict[int, list] | None = None,
) -> list[dict]:
    migrated_legacy_ids = _migrated_legacy_followup_ids(entries)
    events: list[dict] = []
    for item in repayment_items:
        occurred = item.get("repayment_date") or item.get("synced_at") or item.get("created_at")
        events.append(
            {
                "event_type": "repayment",
                "occurred_at": occurred,
                "title": f"还款 期次 {item.get('period_no') or '—'}",
                "amount": item.get("actual_repayment_amount"),
                "source_asset_code": item.get("source_asset_code") or item.get("asset_code"),
                "legacy": False,
            }
        )
    for entry in entries:
        eid = int(entry["id"])
        entry_attachments = (attachments_by_entry or {}).get(eid, [])
        events.append(
            {
                "event_type": "followup",
                "occurred_at": entry.get("created_at"),
                "title": f"跟进 · {entry.get('status_snapshot') or '—'}",
                "owner_name": entry.get("owner_name"),
                "overdue_reason": entry.get("overdue_reason"),
                "follow_up_plan": entry.get("follow_up_plan"),
                "entry_type": entry.get("entry_type"),
                "entry_id": eid,
                "attachments": entry_attachments,
                "legacy": False,
            }
        )
    for fu in legacy_followups:
        if fu.get("id") in migrated_legacy_ids:
            continue
        occurred = fu.get("last_follow_up_at") or fu.get("created_at")
        events.append(
            {
                "event_type": "followup",
                "occurred_at": occurred,
                "title": f"跟进 · {fu.get('status') or '—'}",
                "owner_name": fu.get("owner_name"),
                "overdue_reason": fu.get("overdue_reason"),
                "follow_up_plan": fu.get("follow_up_plan"),
                "asset_code": fu.get("asset_code"),
                "legacy": True,
                "legacy_label": "历史台账",
            }
        )
    events.sort(key=lambda e: str(e.get("occurred_at") or ""), reverse=True)
    return events


def build_overdue_workbench_service(engine: Engine) -> OverdueWorkbenchService:
    return OverdueWorkbenchService(engine)
