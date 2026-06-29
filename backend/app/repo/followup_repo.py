from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import row_to_dict, rows_to_dicts


class FollowupRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_by_trust_asset_id(self, trust_asset_id: int, limit: int = 100) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_product_id,
                        trust_asset_id,
                        data_date,
                        trigger_source,
                        overdue_reason,
                        follow_up_plan,
                        status,
                        owner_name,
                        last_follow_up_at,
                        trust_feedback,
                        created_at,
                        updated_at
                    FROM trust_overdue_followups
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_active_by_trust_asset_id(self, trust_asset_id: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_product_id,
                        trust_asset_id,
                        data_date,
                        trigger_source,
                        overdue_reason,
                        follow_up_plan,
                        status,
                        owner_name,
                        last_follow_up_at,
                        trust_feedback,
                        created_at,
                        updated_at
                    FROM trust_overdue_followups
                    WHERE trust_asset_id = :trust_asset_id
                      AND status IN ('open', 'in_progress')
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"trust_asset_id": trust_asset_id},
            ).fetchone()
        return row_to_dict(row)

    def fetch_by_trust_asset_ids(
        self, trust_asset_ids: list[int], limit: int = 200
    ) -> list[dict]:
        if not trust_asset_ids:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        f.id,
                        f.trust_product_id,
                        f.trust_asset_id,
                        ta.asset_code,
                        f.data_date,
                        f.trigger_source,
                        f.overdue_reason,
                        f.follow_up_plan,
                        f.status,
                        f.owner_name,
                        f.last_follow_up_at,
                        f.trust_feedback,
                        f.created_at,
                        f.updated_at
                    FROM trust_overdue_followups f
                    INNER JOIN trust_assets ta ON ta.id = f.trust_asset_id
                    WHERE f.trust_asset_id = ANY(:trust_asset_ids)
                    ORDER BY f.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_ids": trust_asset_ids, "limit": limit},
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_case_by_asset_code(
        self, trust_product_id: int, asset_code: str, active_only: bool = False
    ) -> dict | None:
        sql = """
            SELECT id, trust_product_id, asset_code, custody_asset_code, data_date, status,
                   owner_name, opened_at, closed_at, last_follow_up_at,
                   created_by, updated_by, created_at, updated_at
            FROM trust_overdue_followup_cases
            WHERE trust_product_id = :trust_product_id
              AND asset_code = :asset_code
        """
        if active_only:
            sql += " AND status IN ('open', 'in_progress')"
        sql += " ORDER BY id DESC LIMIT 1"
        with self._engine.connect() as conn:
            row = conn.execute(
                text(sql),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
        return row_to_dict(row)

    def fetch_case_by_custody(
        self, trust_product_id: int, custody_asset_code: str, active_only: bool = False
    ) -> dict | None:
        """Deprecated: resolve via asset_code at service layer."""
        return None

    def fetch_entries_by_case_id(self, case_id: int, limit: int = 200) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, case_id, entry_type, status_snapshot,
                           overdue_reason, follow_up_plan, trust_feedback, note,
                           owner_name, created_by, created_at
                    FROM trust_overdue_followup_entries
                    WHERE case_id = :case_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"case_id": case_id, "limit": limit},
            ).fetchall()
        return rows_to_dicts(rows)

    def count_entries_by_asset_code(self, trust_product_id: int, asset_code: str) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(e.id) AS cnt
                    FROM trust_overdue_followup_entries e
                    INNER JOIN trust_overdue_followup_cases c ON c.id = e.case_id
                    WHERE c.trust_product_id = :trust_product_id
                      AND c.asset_code = :asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
        return int(row.cnt) if row else 0

    def count_entries_by_custody(self, trust_product_id: int, custody_asset_code: str) -> int:
        return 0

    def insert_entry_and_update_case(
        self,
        *,
        trust_product_id: int,
        asset_code: str,
        data_date: str,
        status: str,
        owner_name: str | None,
        overdue_reason: str | None,
        follow_up_plan: str | None,
        trust_feedback: str | None,
        note: str | None,
        entry_type: str,
        created_by: str | None,
    ) -> dict:
        valid_status = {"open", "in_progress", "resolved", "closed"}
        if status not in valid_status:
            raise ValueError(f"Invalid status: {status}")

        with self._engine.begin() as conn:
            case = conn.execute(
                text(
                    """
                    SELECT id FROM trust_overdue_followup_cases
                    WHERE trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                      AND status IN ('open', 'in_progress')
                    LIMIT 1
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()

            if case is None:
                case_row = conn.execute(
                    text(
                        """
                        INSERT INTO trust_overdue_followup_cases (
                            trust_product_id, asset_code, custody_asset_code, data_date,
                            status, owner_name, opened_at, closed_at,
                            last_follow_up_at, created_by, updated_by
                        ) VALUES (
                            :trust_product_id, :asset_code, :asset_code, :data_date,
                            :status, :owner_name, NOW(),
                            CASE WHEN :status IN ('resolved', 'closed') THEN NOW() ELSE NULL END,
                            NOW(), :created_by, :created_by
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "trust_product_id": trust_product_id,
                        "asset_code": asset_code,
                        "data_date": data_date,
                        "status": status,
                        "owner_name": owner_name,
                        "created_by": created_by,
                    },
                ).fetchone()
                case_id = int(case_row.id)
            else:
                case_id = int(case.id)
                conn.execute(
                    text(
                        """
                        UPDATE trust_overdue_followup_cases
                        SET status = :status,
                            owner_name = COALESCE(:owner_name, owner_name),
                            last_follow_up_at = NOW(),
                            updated_by = :created_by,
                            closed_at = CASE
                                WHEN :status IN ('resolved', 'closed') THEN NOW()
                                ELSE NULL
                            END
                        WHERE id = :case_id
                        """
                    ),
                    {
                        "case_id": case_id,
                        "status": status,
                        "owner_name": owner_name,
                        "created_by": created_by,
                    },
                )

            entry_row = conn.execute(
                text(
                    """
                    INSERT INTO trust_overdue_followup_entries (
                        case_id, entry_type, status_snapshot,
                        overdue_reason, follow_up_plan, trust_feedback, note,
                        owner_name, created_by
                    ) VALUES (
                        :case_id, :entry_type, :status_snapshot,
                        :overdue_reason, :follow_up_plan, :trust_feedback, :note,
                        :owner_name, :created_by
                    )
                    RETURNING id, created_at
                    """
                ),
                {
                    "case_id": case_id,
                    "entry_type": entry_type,
                    "status_snapshot": status,
                    "overdue_reason": overdue_reason,
                    "follow_up_plan": follow_up_plan,
                    "trust_feedback": trust_feedback,
                    "note": note,
                    "owner_name": owner_name,
                    "created_by": created_by,
                },
            ).fetchone()

        return {
            "case_id": case_id,
            "entry_id": int(entry_row.id),
            "created_at": str(entry_row.created_at),
            "status": status,
        }

    def update_in_progress_entry(
        self,
        *,
        entry_id: int,
        trust_product_id: int,
        asset_code: str,
        status: str,
        owner_name: str | None,
        overdue_reason: str | None,
        follow_up_plan: str | None,
        trust_feedback: str | None,
        note: str | None,
        updated_by: str | None,
    ) -> dict:
        valid_status = {"open", "in_progress", "resolved", "closed"}
        if status not in valid_status:
            raise ValueError(f"Invalid status: {status}")

        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT e.id, e.case_id, e.status_snapshot
                    FROM trust_overdue_followup_entries e
                    INNER JOIN trust_overdue_followup_cases c ON c.id = e.case_id
                    WHERE e.id = :entry_id
                      AND c.trust_product_id = :trust_product_id
                      AND c.asset_code = :asset_code
                    LIMIT 1
                    """
                ),
                {
                    "entry_id": entry_id,
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
            if row is None:
                raise ValueError("Followup entry not found")
            if row.status_snapshot != "in_progress":
                raise ValueError("Only in_progress followup entries can be edited")

            case_id = int(row.case_id)
            conn.execute(
                text(
                    """
                    UPDATE trust_overdue_followup_entries
                    SET status_snapshot = :status,
                        owner_name = :owner_name,
                        overdue_reason = :overdue_reason,
                        follow_up_plan = :follow_up_plan,
                        trust_feedback = :trust_feedback,
                        note = :note
                    WHERE id = :entry_id
                    """
                ),
                {
                    "entry_id": entry_id,
                    "status": status,
                    "owner_name": owner_name,
                    "overdue_reason": overdue_reason,
                    "follow_up_plan": follow_up_plan,
                    "trust_feedback": trust_feedback,
                    "note": note,
                },
            )

            latest = conn.execute(
                text(
                    """
                    SELECT id FROM trust_overdue_followup_entries
                    WHERE case_id = :case_id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            ).fetchone()
            if latest and int(latest.id) == entry_id:
                conn.execute(
                    text(
                        """
                        UPDATE trust_overdue_followup_cases
                        SET status = :status,
                            owner_name = :owner_name,
                            updated_by = :updated_by,
                            closed_at = CASE
                                WHEN :status IN ('resolved', 'closed') THEN NOW()
                                ELSE NULL
                            END
                        WHERE id = :case_id
                        """
                    ),
                    {
                        "case_id": case_id,
                        "status": status,
                        "owner_name": owner_name,
                        "updated_by": updated_by,
                    },
                )

        return {"case_id": case_id, "entry_id": entry_id, "status": status}

    def insert_attachments(
        self,
        entry_id: int,
        attachments: list[dict],
        uploaded_by: str | None,
    ) -> list[dict]:
        if not attachments:
            return []
        results: list[dict] = []
        with self._engine.begin() as conn:
            for att in attachments:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO trust_overdue_followup_attachments (
                            entry_id, file_name, stored_path, content_type,
                            file_size, attachment_type, uploaded_by
                        ) VALUES (
                            :entry_id, :file_name, :stored_path, :content_type,
                            :file_size, :attachment_type, :uploaded_by
                        )
                        RETURNING id, file_name, stored_path, attachment_type, created_at
                        """
                    ),
                    {
                        "entry_id": entry_id,
                        "file_name": att["file_name"],
                        "stored_path": att["stored_path"],
                        "content_type": att.get("content_type"),
                        "file_size": att.get("file_size"),
                        "attachment_type": att.get("attachment_type", "file"),
                        "uploaded_by": uploaded_by,
                    },
                ).fetchone()
                results.append(row_to_dict(row))
        return results

    def fetch_attachment(self, attachment_id: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, entry_id, file_name, stored_path, content_type,
                           file_size, attachment_type, uploaded_by, created_at
                    FROM trust_overdue_followup_attachments
                    WHERE id = :id
                    """
                ),
                {"id": attachment_id},
            ).fetchone()
        return row_to_dict(row)

    def fetch_attachments_by_entry_ids(self, entry_ids: list[int]) -> list[dict]:
        if not entry_ids:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, entry_id, file_name, stored_path, content_type,
                           file_size, attachment_type, created_at
                    FROM trust_overdue_followup_attachments
                    WHERE entry_id = ANY(:entry_ids)
                    ORDER BY id
                    """
                ),
                {"entry_ids": entry_ids},
            ).fetchall()
        return rows_to_dicts(rows)

    def count_attachments_for_entry(self, entry_id: int) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM trust_overdue_followup_attachments
                    WHERE entry_id = :entry_id
                    """
                ),
                {"entry_id": entry_id},
            ).fetchone()
        return int(row.cnt) if row else 0
