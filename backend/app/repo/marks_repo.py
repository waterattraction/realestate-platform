from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import row_to_dict

TRUST_MARKER_DEFAULT = "未标记"
INTERNAL_STATUS_DEFAULT = "待跟进"


class MarksRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_mark(
        self,
        trust_product_id: int,
        custody_asset_code: str,
        data_date: str,
    ) -> dict:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_product_id,
                        custody_asset_code,
                        data_date,
                        trust_marker,
                        internal_status,
                        marker_note,
                        updated_by,
                        updated_at
                    FROM trust_asset_trust_marks
                    WHERE trust_product_id = :trust_product_id
                      AND custody_asset_code = :custody_asset_code
                      AND data_date = :data_date
                    LIMIT 1
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "custody_asset_code": custody_asset_code,
                    "data_date": data_date,
                },
            ).fetchone()
        if row is None:
            return {
                "trust_product_id": trust_product_id,
                "custody_asset_code": custody_asset_code,
                "data_date": data_date,
                "trust_marker": TRUST_MARKER_DEFAULT,
                "internal_status": INTERNAL_STATUS_DEFAULT,
                "marker_note": None,
            }
        data = row_to_dict(row)
        data["trust_marker"] = data.get("trust_marker") or TRUST_MARKER_DEFAULT
        data["internal_status"] = data.get("internal_status") or INTERNAL_STATUS_DEFAULT
        return data
