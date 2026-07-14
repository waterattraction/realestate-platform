from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import row_to_dict


TRUST_MARKER_DEFAULT = "无标记"
INTERNAL_STATUS_DEFAULT = "正常"


class MarksRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_mark(
        self,
        trust_product_id: int,
        asset_code: str,
        data_date: str | None = None,
    ) -> dict:
        """按资产主编号取标记；data_date 仅作返回占位，不参与查询。"""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_product_id,
                        asset_code,
                        custody_asset_code,
                        data_date,
                        trust_marker,
                        internal_status,
                        marker_note,
                        updated_by,
                        updated_at
                    FROM trust_asset_trust_marks
                    WHERE trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                    LIMIT 1
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
        if row is None:
            return {
                "trust_product_id": trust_product_id,
                "asset_code": asset_code,
                "data_date": data_date,
                "trust_marker": TRUST_MARKER_DEFAULT,
                "internal_status": INTERNAL_STATUS_DEFAULT,
                "marker_note": None,
            }
        data = row_to_dict(row)
        if data.get("data_date") is not None:
            data["data_date"] = str(data["data_date"])
        data["trust_marker"] = data.get("trust_marker") or TRUST_MARKER_DEFAULT
        data["internal_status"] = data.get("internal_status") or INTERNAL_STATUS_DEFAULT
        return data

    def upsert_mark(
        self,
        *,
        trust_product_id: int,
        asset_code: str,
        data_date: str | None = None,
        trust_marker: str | None = None,
        internal_status: str | None = None,
        updated_by: str | None = None,
    ) -> dict:
        existing = self.fetch_mark(trust_product_id, asset_code)
        if existing.get("id"):
            new_marker = trust_marker if trust_marker is not None else existing["trust_marker"]
            new_status = (
                internal_status if internal_status is not None else existing["internal_status"]
            )
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE trust_asset_trust_marks
                        SET trust_marker = :trust_marker,
                            internal_status = :internal_status,
                            data_date = COALESCE(:data_date, data_date),
                            updated_by = :updated_by,
                            updated_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": existing["id"],
                        "trust_marker": new_marker,
                        "internal_status": new_status,
                        "data_date": data_date,
                        "updated_by": updated_by,
                    },
                )
            return {
                **existing,
                "trust_marker": new_marker,
                "internal_status": new_status,
                "data_date": data_date or existing.get("data_date"),
            }

        if data_date is None:
            raise ValueError("data_date is required when creating a trust mark row")

        new_marker = trust_marker or TRUST_MARKER_DEFAULT
        new_status = internal_status or INTERNAL_STATUS_DEFAULT
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO trust_asset_trust_marks (
                        trust_product_id, asset_code, custody_asset_code, data_date,
                        trust_marker, internal_status, created_by, updated_by
                    ) VALUES (
                        :trust_product_id, :asset_code, :asset_code, :data_date,
                        :trust_marker, :internal_status, :updated_by, :updated_by
                    )
                    RETURNING id
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                    "data_date": data_date,
                    "trust_marker": new_marker,
                    "internal_status": new_status,
                    "updated_by": updated_by,
                },
            ).fetchone()
        return {
            "id": int(row.id),
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
            "data_date": data_date,
            "trust_marker": new_marker,
            "internal_status": new_status,
        }
