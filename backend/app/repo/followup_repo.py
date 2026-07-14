"""运营跟进：cases（事项）+ entries（记录）。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app import query_utils
from app.repo._serialize import row_to_dict, rows_to_dicts
from app.service.followup_upload import upload_root

CASE_STATUSES = frozenset(
    {"open", "in_progress", "settled_week", "resolved", "closed"}
)
# 问题态：驱动「待跟进(N)」
PROBLEM_CASE_STATUSES = frozenset({"open", "in_progress"})
# 兼容旧名 = 问题态
ACTIVE_CASE_STATUSES = PROBLEM_CASE_STATUSES
# 可写跟进记录（含本周结算）
ENTRY_MUTABLE_STATUSES = frozenset({"open", "in_progress", "settled_week"})
CASE_CATEGORIES = frozenset({"轻度逾期", "重度逾期", "回购", "置换", "潜在风险"})
DEFAULT_CASE_STATUS = "open"
DEFAULT_CASE_CATEGORY = "轻度逾期"


def format_internal_status(
    problem_count: int, settled_week_count: int = 0
) -> str:
    if problem_count > 0:
        return f"待跟进({problem_count})"
    if settled_week_count > 0:
        return f"本周结算({settled_week_count})"
    return "正常"


class FollowupRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_cases_list(
        self,
        trust_product_ids: list[int] | None = None,
        status: str | None = None,
        limit: int = 500,
        *,
        include_latest_entry: bool = False,
    ) -> list[dict]:
        latest_cols = ""
        latest_join = ""
        if include_latest_entry:
            latest_cols = """,
                le.overdue_reason AS latest_overdue_reason,
                le.follow_up_plan AS latest_follow_up_plan"""
            latest_join = """
            LEFT JOIN LATERAL (
                SELECT e.overdue_reason, e.follow_up_plan
                FROM trust_overdue_followup_entries e
                WHERE e.case_id = c.id
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT 1
            ) le ON TRUE
            """
        sql = f"""
            SELECT
                c.id,
                c.trust_product_id,
                tp.name AS trust_product_name,
                c.asset_code,
                c.custody_asset_code,
                c.data_date,
                c.category,
                c.description,
                c.status,
                c.owner_name,
                c.opened_at,
                c.closed_at,
                c.last_follow_up_at,
                c.created_by,
                c.updated_by,
                c.created_at,
                c.updated_at
                {latest_cols}
            FROM trust_overdue_followup_cases c
            INNER JOIN trust_products tp ON tp.id = c.trust_product_id
            {latest_join}
            WHERE 1=1
        """
        params: dict = {"limit": limit}
        product_sql, product_params = query_utils.sql_in_int_column(
            "c.trust_product_id", trust_product_ids, param_prefix="fpid"
        )
        sql += product_sql
        params.update(product_params)
        if status is not None:
            sql += " AND c.status = :status"
            params["status"] = status
        sql += " ORDER BY c.last_follow_up_at DESC NULLS LAST, c.id DESC LIMIT :limit"
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        items = []
        for row in rows:
            rec = row_to_dict(row)
            items.append(self._serialize_case(rec))
        return items

    def _serialize_case(self, rec: dict) -> dict:
        for key in (
            "data_date",
            "opened_at",
            "closed_at",
            "last_follow_up_at",
            "created_at",
            "updated_at",
        ):
            if rec.get(key) is not None:
                rec[key] = str(rec[key])
        return rec

    def _resolve_asset_code(self, conn, trust_asset_id: int) -> tuple[int, str] | None:
        row = conn.execute(
            text(
                """
                SELECT trust_product_id, asset_code
                FROM trust_assets
                WHERE id = :trust_asset_id
                """
            ),
            {"trust_asset_id": trust_asset_id},
        ).fetchone()
        if row is None:
            return None
        return int(row.trust_product_id), str(row.asset_code)

    def count_active_cases(self, trust_product_id: int, asset_code: str) -> int:
        """问题态事项数（open/in_progress）。"""
        with self._engine.connect() as conn:
            return self._count_status_cases(
                conn, trust_product_id, asset_code, PROBLEM_CASE_STATUSES
            )

    def _count_status_cases(
        self,
        conn,
        trust_product_id: int,
        asset_code: str,
        statuses: frozenset[str],
    ) -> int:
        if not statuses:
            return 0
        status_list = sorted(statuses)
        placeholders = ", ".join(f":s{i}" for i in range(len(status_list)))
        params: dict = {
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
        }
        for i, s in enumerate(status_list):
            params[f"s{i}"] = s
        row = conn.execute(
            text(
                f"""
                SELECT COUNT(*) AS cnt
                FROM trust_overdue_followup_cases
                WHERE trust_product_id = :trust_product_id
                  AND asset_code = :asset_code
                  AND status IN ({placeholders})
                """
            ),
            params,
        ).fetchone()
        return int(row.cnt) if row else 0

    def _count_active_cases(self, conn, trust_product_id: int, asset_code: str) -> int:
        return self._count_status_cases(
            conn, trust_product_id, asset_code, PROBLEM_CASE_STATUSES
        )

    def sync_internal_status(
        self, conn, trust_product_id: int, asset_code: str, updated_by: str | None = None
    ) -> str:
        problem_n = self._count_status_cases(
            conn, trust_product_id, asset_code, PROBLEM_CASE_STATUSES
        )
        settled_n = self._count_status_cases(
            conn, trust_product_id, asset_code, frozenset({"settled_week"})
        )
        label = format_internal_status(problem_n, settled_n)
        result = conn.execute(
            text(
                """
                UPDATE trust_asset_trust_marks
                SET internal_status = :status,
                    updated_by = COALESCE(:updated_by, updated_by),
                    updated_at = NOW()
                WHERE trust_product_id = :pid
                  AND asset_code = :asset_code
                """
            ),
            {
                "pid": trust_product_id,
                "asset_code": asset_code,
                "status": label,
                "updated_by": updated_by,
            },
        )
        if result.rowcount == 0:
            # 尚无标记行：用最新监控日插入一条派生状态
            dd = conn.execute(
                text(
                    """
                    SELECT MAX(data_date) AS dd
                    FROM trust_asset_monitor_records
                    WHERE trust_product_id = :pid
                      AND asset_code = :asset_code
                    """
                ),
                {"pid": trust_product_id, "asset_code": asset_code},
            ).scalar()
            if dd is not None:
                conn.execute(
                    text(
                        """
                        INSERT INTO trust_asset_trust_marks (
                            trust_product_id, asset_code, custody_asset_code, data_date,
                            trust_marker, internal_status, created_by, updated_by
                        ) VALUES (
                            :pid, :asset_code, :asset_code, :dd,
                            '无标记', :status, :updated_by, :updated_by
                        )
                        """
                    ),
                    {
                        "pid": trust_product_id,
                        "asset_code": asset_code,
                        "dd": dd,
                        "status": label,
                        "updated_by": updated_by or "system",
                    },
                )
        return label

    def _case_summary_for_asset(self, conn, trust_asset_id: int) -> dict | None:
        resolved = self._resolve_asset_code(conn, trust_asset_id)
        if resolved is None:
            return None
        trust_product_id, asset_code = resolved
        case = conn.execute(
            text(
                """
                SELECT id, trust_product_id, asset_code, category, description,
                       data_date, status, owner_name, last_follow_up_at,
                       opened_at, created_at, updated_at
                FROM trust_overdue_followup_cases
                WHERE trust_product_id = :trust_product_id
                  AND asset_code = :asset_code
                  AND status IN ('open', 'in_progress')
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"trust_product_id": trust_product_id, "asset_code": asset_code},
        ).fetchone()
        if case is None:
            return None
        latest_entry = conn.execute(
            text(
                """
                SELECT overdue_reason, follow_up_plan
                FROM trust_overdue_followup_entries
                WHERE case_id = :case_id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"case_id": case.id},
        ).fetchone()
        return {
            "id": case.id,
            "trust_product_id": case.trust_product_id,
            "trust_asset_id": trust_asset_id,
            "data_date": str(case.data_date),
            "category": case.category,
            "description": case.description,
            "status": case.status,
            "owner_name": case.owner_name,
            "last_follow_up_at": (
                str(case.last_follow_up_at) if case.last_follow_up_at else None
            ),
            "overdue_reason": latest_entry.overdue_reason if latest_entry else None,
            "follow_up_plan": latest_entry.follow_up_plan if latest_entry else None,
            "created_at": str(case.created_at),
            "updated_at": str(case.updated_at),
        }

    def fetch_by_trust_asset_id(self, trust_asset_id: int, limit: int = 100) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        e.id,
                        c.trust_product_id,
                        ta.id AS trust_asset_id,
                        c.data_date,
                        c.status,
                        e.overdue_reason,
                        e.follow_up_plan,
                        e.owner_name,
                        e.created_at
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
        return rows_to_dicts(rows)

    def fetch_active_by_trust_asset_id(self, trust_asset_id: int) -> dict | None:
        with self._engine.connect() as conn:
            return self._case_summary_for_asset(conn, trust_asset_id)

    def fetch_by_trust_asset_ids(
        self, trust_asset_ids: list[int], limit: int = 200
    ) -> list[dict]:
        return []

    def fetch_cases_by_asset_code(
        self, trust_product_id: int, asset_code: str
    ) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, trust_product_id, asset_code, custody_asset_code,
                           data_date, category, description, status, owner_name,
                           opened_at, closed_at, last_follow_up_at,
                           created_by, updated_by, created_at, updated_at
                    FROM trust_overdue_followup_cases
                    WHERE trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                    ORDER BY
                        CASE WHEN status IN ('open', 'in_progress') THEN 0 ELSE 1 END,
                        created_at DESC,
                        id DESC
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchall()
        return [self._serialize_case(row_to_dict(r)) for r in rows]

    def fetch_case_by_asset_code(
        self, trust_product_id: int, asset_code: str, active_only: bool = False
    ) -> dict | None:
        cases = self.fetch_cases_by_asset_code(trust_product_id, asset_code)
        if active_only:
            cases = [c for c in cases if c.get("status") in ACTIVE_CASE_STATUSES]
        return cases[0] if cases else None

    def fetch_case_by_id(self, case_id: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, trust_product_id, asset_code, custody_asset_code,
                           data_date, category, description, status, owner_name,
                           opened_at, closed_at, last_follow_up_at,
                           created_by, updated_by, created_at, updated_at
                    FROM trust_overdue_followup_cases
                    WHERE id = :id
                    """
                ),
                {"id": case_id},
            ).fetchone()
        return self._serialize_case(row_to_dict(row)) if row else None

    def fetch_case_by_custody(
        self, trust_product_id: int, custody_asset_code: str, active_only: bool = False
    ) -> dict | None:
        return None

    def fetch_entries_by_case_id(self, case_id: int, limit: int = 200) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, case_id, entry_type,
                           overdue_reason, follow_up_plan,
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

    def create_case(
        self,
        *,
        trust_product_id: int,
        asset_code: str,
        data_date: str,
        category: str,
        description: str | None,
        status: str = DEFAULT_CASE_STATUS,
        owner_name: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        if category not in CASE_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")
        if status not in CASE_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO trust_overdue_followup_cases (
                        trust_product_id, asset_code, custody_asset_code, data_date,
                        category, description, status, owner_name,
                        opened_at, closed_at, last_follow_up_at, created_by, updated_by
                    ) VALUES (
                        :trust_product_id, :asset_code, :asset_code, :data_date,
                        :category, :description, :status, :owner_name,
                        NOW(),
                        CASE WHEN :status IN ('resolved', 'closed') THEN NOW() ELSE NULL END,
                        NULL, :created_by, :created_by
                    )
                    RETURNING id
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                    "data_date": data_date,
                    "category": category,
                    "description": description,
                    "status": status,
                    "owner_name": owner_name,
                    "created_by": created_by,
                },
            ).fetchone()
            case_id = int(row.id)
            internal = self.sync_internal_status(
                conn, trust_product_id, asset_code, created_by
            )
        return {
            "case_id": case_id,
            "status": status,
            "internal_status": internal,
        }

    def update_case(
        self,
        *,
        case_id: int,
        trust_product_id: int,
        asset_code: str,
        status: str | None = None,
        category: str | None = None,
        description: str | None = None,
        owner_name: str | None = None,
        updated_by: str | None = None,
    ) -> dict:
        if status is not None and status not in CASE_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if category is not None and category not in CASE_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, status FROM trust_overdue_followup_cases
                    WHERE id = :case_id
                      AND trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                    LIMIT 1
                    """
                ),
                {
                    "case_id": case_id,
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
            if row is None:
                raise ValueError("Followup case not found")
            new_status = status if status is not None else row.status
            conn.execute(
                text(
                    """
                    UPDATE trust_overdue_followup_cases
                    SET status = :status,
                        category = COALESCE(:category, category),
                        description = COALESCE(:description, description),
                        owner_name = COALESCE(:owner_name, owner_name),
                        updated_by = :updated_by,
                        closed_at = CASE
                            WHEN :status IN ('resolved', 'closed') THEN COALESCE(closed_at, NOW())
                            ELSE NULL
                        END
                    WHERE id = :case_id
                    """
                ),
                {
                    "case_id": case_id,
                    "status": new_status,
                    "category": category,
                    "description": description,
                    "owner_name": owner_name,
                    "updated_by": updated_by,
                },
            )
            internal = self.sync_internal_status(
                conn, trust_product_id, asset_code, updated_by
            )
        return {
            "case_id": case_id,
            "status": new_status,
            "internal_status": internal,
        }

    def insert_entry(
        self,
        *,
        case_id: int,
        trust_product_id: int,
        asset_code: str,
        owner_name: str | None,
        overdue_reason: str | None,
        follow_up_plan: str | None,
        entry_type: str,
        created_by: str | None,
    ) -> dict:
        with self._engine.begin() as conn:
            case = conn.execute(
                text(
                    """
                    SELECT id, status FROM trust_overdue_followup_cases
                    WHERE id = :case_id
                      AND trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                    LIMIT 1
                    """
                ),
                {
                    "case_id": case_id,
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
            if case is None:
                raise ValueError("Followup case not found")
            if case.status not in ENTRY_MUTABLE_STATUSES:
                raise ValueError("Cannot add entry to a closed followup case")

            entry_row = conn.execute(
                text(
                    """
                    INSERT INTO trust_overdue_followup_entries (
                        case_id, entry_type,
                        overdue_reason, follow_up_plan,
                        owner_name, created_by
                    ) VALUES (
                        :case_id, :entry_type,
                        :overdue_reason, :follow_up_plan,
                        :owner_name, :created_by
                    )
                    RETURNING id, created_at
                    """
                ),
                {
                    "case_id": case_id,
                    "entry_type": entry_type,
                    "overdue_reason": overdue_reason,
                    "follow_up_plan": follow_up_plan,
                    "owner_name": owner_name,
                    "created_by": created_by,
                },
            ).fetchone()
            conn.execute(
                text(
                    """
                    UPDATE trust_overdue_followup_cases
                    SET last_follow_up_at = NOW(),
                        owner_name = COALESCE(:owner_name, owner_name),
                        updated_by = :created_by
                    WHERE id = :case_id
                    """
                ),
                {
                    "case_id": case_id,
                    "owner_name": owner_name,
                    "created_by": created_by,
                },
            )

        return {
            "case_id": case_id,
            "entry_id": int(entry_row.id),
            "created_at": str(entry_row.created_at),
        }

    # 兼容旧调用名
    def insert_entry_and_update_case(self, **kwargs) -> dict:
        case_id = kwargs.pop("case_id", None)
        if case_id is None:
            raise ValueError("case_id is required")
        kwargs.pop("status", None)
        kwargs.pop("trust_feedback", None)
        kwargs.pop("note", None)
        kwargs.pop("data_date", None)
        return self.insert_entry(case_id=case_id, **kwargs)

    def update_entry(
        self,
        *,
        entry_id: int,
        trust_product_id: int,
        asset_code: str,
        owner_name: str | None,
        overdue_reason: str | None,
        follow_up_plan: str | None,
        updated_by: str | None,
        status: str | None = None,
        trust_feedback: str | None = None,
        note: str | None = None,
    ) -> dict:
        del status, trust_feedback, note  # 已废弃，忽略
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT e.id, e.case_id, c.status AS case_status
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
            if row.case_status not in ENTRY_MUTABLE_STATUSES:
                raise ValueError("Only entries under active cases can be edited")

            case_id = int(row.case_id)
            conn.execute(
                text(
                    """
                    UPDATE trust_overdue_followup_entries
                    SET owner_name = :owner_name,
                        overdue_reason = :overdue_reason,
                        follow_up_plan = :follow_up_plan
                    WHERE id = :entry_id
                    """
                ),
                {
                    "entry_id": entry_id,
                    "owner_name": owner_name,
                    "overdue_reason": overdue_reason,
                    "follow_up_plan": follow_up_plan,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE trust_overdue_followup_cases
                    SET owner_name = COALESCE(:owner_name, owner_name),
                        updated_by = :updated_by
                    WHERE id = :case_id
                    """
                ),
                {
                    "case_id": case_id,
                    "owner_name": owner_name,
                    "updated_by": updated_by,
                },
            )

        return {"case_id": case_id, "entry_id": entry_id}

    update_in_progress_entry = update_entry

    def _unlink_attachment_files(self, stored_paths: list[str]) -> None:
        root = upload_root().resolve()
        for rel in stored_paths:
            try:
                full = (upload_root() / rel).resolve()
                if str(full).startswith(str(root)) and full.is_file():
                    full.unlink()
            except OSError:
                pass

    def _assert_entry_mutable(
        self, conn, *, entry_id: int, trust_product_id: int, asset_code: str
    ):
        row = conn.execute(
            text(
                """
                SELECT e.id, e.case_id, c.status AS case_status
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
        if row.case_status not in ENTRY_MUTABLE_STATUSES:
            raise ValueError("Only entries under active cases can be edited")
        return row

    def delete_attachments(
        self,
        *,
        attachment_ids: list[int],
        entry_id: int,
        trust_product_id: int,
        asset_code: str,
    ) -> int:
        if not attachment_ids:
            return 0
        unique_ids = list(dict.fromkeys(int(i) for i in attachment_ids))
        stored_paths: list[str] = []

        with self._engine.begin() as conn:
            self._assert_entry_mutable(
                conn,
                entry_id=entry_id,
                trust_product_id=trust_product_id,
                asset_code=asset_code,
            )
            att_rows = conn.execute(
                text(
                    """
                    SELECT id, stored_path
                    FROM trust_overdue_followup_attachments
                    WHERE entry_id = :entry_id
                      AND id = ANY(:attachment_ids)
                    """
                ),
                {"entry_id": entry_id, "attachment_ids": unique_ids},
            ).fetchall()
            if len(att_rows) != len(unique_ids):
                raise ValueError("Attachment not found")

            stored_paths = [str(r.stored_path) for r in att_rows if r.stored_path]
            conn.execute(
                text(
                    """
                    DELETE FROM trust_overdue_followup_attachments
                    WHERE entry_id = :entry_id
                      AND id = ANY(:attachment_ids)
                    """
                ),
                {"entry_id": entry_id, "attachment_ids": unique_ids},
            )

        self._unlink_attachment_files(stored_paths)
        return len(unique_ids)

    def delete_entry(
        self,
        *,
        entry_id: int,
        trust_product_id: int,
        asset_code: str,
        updated_by: str | None = None,
    ) -> dict:
        stored_paths: list[str] = []
        case_id: int

        with self._engine.begin() as conn:
            row = self._assert_entry_mutable(
                conn,
                entry_id=entry_id,
                trust_product_id=trust_product_id,
                asset_code=asset_code,
            )
            case_id = int(row.case_id)
            att_rows = conn.execute(
                text(
                    """
                    SELECT stored_path
                    FROM trust_overdue_followup_attachments
                    WHERE entry_id = :entry_id
                    """
                ),
                {"entry_id": entry_id},
            ).fetchall()
            stored_paths = [str(r.stored_path) for r in att_rows if r.stored_path]

            conn.execute(
                text(
                    "DELETE FROM trust_overdue_followup_attachments WHERE entry_id = :entry_id"
                ),
                {"entry_id": entry_id},
            )
            conn.execute(
                text("DELETE FROM trust_overdue_followup_entries WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )
            latest = conn.execute(
                text(
                    """
                    SELECT created_at, owner_name
                    FROM trust_overdue_followup_entries
                    WHERE case_id = :case_id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            ).fetchone()
            conn.execute(
                text(
                    """
                    UPDATE trust_overdue_followup_cases
                    SET last_follow_up_at = :last_at,
                        updated_by = :updated_by
                    WHERE id = :case_id
                    """
                ),
                {
                    "case_id": case_id,
                    "last_at": latest.created_at if latest else None,
                    "updated_by": updated_by,
                },
            )

        self._unlink_attachment_files(stored_paths)
        return {"case_id": case_id, "entry_id": entry_id, "deleted": True}

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
