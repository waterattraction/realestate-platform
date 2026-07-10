"""asset_locations + spatial_geocode_runs — Spatial P0."""

from __future__ import annotations

import hashlib
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import row_to_dict, rows_to_dicts

UNKNOWN_CITY = "未知"


def address_hash(raw_address: str | None) -> str | None:
    if not raw_address or not str(raw_address).strip():
        return None
    return hashlib.sha256(str(raw_address).strip().encode("utf-8")).hexdigest()


class LocationRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_by_product_asset(
        self, trust_product_id: int, asset_code: str
    ) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM asset_locations
                    WHERE trust_product_id = :pid AND asset_code = :ac
                    LIMIT 1
                    """
                ),
                {"pid": trust_product_id, "ac": asset_code},
            ).fetchone()
        return row_to_dict(row)

    def fetch_by_id(self, location_id: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT al.*,
                           tp.name AS trust_product_name,
                           i.property_address AS issuance_address,
                           i.city AS issuance_city,
                           i.contract_name,
                           i.debtor_name,
                           i.custody_asset_code
                    FROM asset_locations al
                    INNER JOIN trust_products tp ON tp.id = al.trust_product_id
                    LEFT JOIN trust_product_issuance_asset_records i
                        ON i.id = al.source_issuance_id
                    WHERE al.id = :id
                    LIMIT 1
                    """
                ),
                {"id": location_id},
            ).fetchone()
        return row_to_dict(row)

    def fetch_locations_page(
        self,
        *,
        city: str,
        page: int,
        page_size: int,
        geocode_status: str | None = None,
        q: str | None = None,
    ) -> tuple[list[dict], int]:
        city = (city or "").strip()
        if not city or city == UNKNOWN_CITY:
            return [], 0

        offset = max(page - 1, 0) * page_size
        params: dict = {
            "city": city,
            "unknown": UNKNOWN_CITY,
            "limit": page_size,
            "offset": offset,
        }
        filters = [
            "COALESCE(NULLIF(TRIM(al.city), ''), :unknown) = :city",
        ]
        if geocode_status:
            filters.append("al.geocode_status = :geocode_status")
            params["geocode_status"] = geocode_status
        if q:
            filters.append(
                """(
                    al.asset_code ILIKE :q
                    OR al.raw_address ILIKE :q
                    OR COALESCE(i.contract_name, '') ILIKE :q
                    OR COALESCE(i.debtor_name, '') ILIKE :q
                    OR COALESCE(i.property_address, '') ILIKE :q
                )"""
            )
            params["q"] = f"%{q.strip()}%"

        where_sql = " AND ".join(filters)
        base_from = f"""
            FROM asset_locations al
            INNER JOIN trust_products tp ON tp.id = al.trust_product_id
            LEFT JOIN trust_product_issuance_asset_records i
                ON i.id = al.source_issuance_id
            WHERE {where_sql}
        """

        with self._engine.connect() as conn:
            total_row = conn.execute(
                text(f"SELECT COUNT(*) AS cnt {base_from}"),
                params,
            ).fetchone()
            total = int(total_row.cnt) if total_row else 0
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        al.id AS location_id,
                        al.trust_product_id,
                        tp.name AS trust_product_name,
                        al.asset_code,
                        al.property_id,
                        al.raw_address,
                        al.city,
                        al.province,
                        al.district,
                        al.formatted_address,
                        al.latitude,
                        al.longitude,
                        al.geocode_status,
                        al.geocode_provider,
                        al.geocode_level,
                        al.geocode_error,
                        al.geocoded_at,
                        al.location_source,
                        al.source_issuance_id,
                        al.address_hash,
                        al.created_at,
                        al.updated_at,
                        i.property_address AS issuance_address,
                        i.city AS issuance_city,
                        i.contract_name,
                        i.debtor_name,
                        i.custody_asset_code
                    {base_from}
                    ORDER BY
                        CASE al.geocode_status
                            WHEN 'failed' THEN 1
                            WHEN 'pending' THEN 2
                            WHEN 'success' THEN 3
                            ELSE 4
                        END,
                        al.updated_at DESC,
                        al.id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).fetchall()
        return rows_to_dicts(rows), total

    def sync_locations_after_sheet_import(
        self,
        conn,
        *,
        trust_product_id: int,
        issue_date,
        file_name: str,
        sheet_name: str,
    ) -> int:
        """Upsert asset_locations from rows just imported in this sheet scope."""
        rows = conn.execute(
            text(
                """
                SELECT i.id AS source_issuance_id,
                       ta.trust_product_id,
                       ta.asset_code,
                       i.property_address AS raw_address,
                       i.city
                FROM trust_product_issuance_asset_records i
                INNER JOIN trust_assets ta
                    ON ta.trust_product_id = i.trust_product_id
                   AND ta.custody_asset_code = i.custody_asset_code
                WHERE i.trust_product_id = :pid
                  AND i.issue_date = :issue
                  AND i.source_file_name = :fn
                  AND i.source_sheet_name = :sn
                  AND i.property_address IS NOT NULL
                  AND TRIM(i.property_address) <> ''
                """
            ),
            {
                "pid": trust_product_id,
                "issue": issue_date,
                "fn": file_name,
                "sn": sheet_name,
            },
        ).fetchall()
        changed = 0
        for row in rows:
            d = row_to_dict(row)
            if self.upsert_from_issuance(
                trust_product_id=int(d["trust_product_id"]),
                asset_code=str(d["asset_code"]),
                raw_address=str(d["raw_address"]),
                city=d.get("city"),
                source_issuance_id=int(d["source_issuance_id"]),
            ):
                changed += 1
        return changed

    def upsert_from_issuance(
        self,
        *,
        trust_product_id: int,
        asset_code: str,
        raw_address: str,
        city: str | None,
        source_issuance_id: int,
    ) -> bool:
        """Returns True if row was inserted or address changed (needs geocode)."""
        addr = str(raw_address).strip()
        city_val = (city or "").strip() or None
        h = address_hash(addr)
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, address_hash, geocode_status
                    FROM asset_locations
                    WHERE trust_product_id = :pid AND asset_code = :ac
                    """
                ),
                {"pid": trust_product_id, "ac": asset_code},
            ).fetchone()
            if row is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO asset_locations (
                            trust_product_id, asset_code, raw_address, city,
                            location_source, source_issuance_id, address_hash,
                            geocode_status, updated_at
                        ) VALUES (
                            :pid, :ac, :addr, :city,
                            'ISSUANCE', :iid, :h,
                            'pending', NOW()
                        )
                        """
                    ),
                    {
                        "pid": trust_product_id,
                        "ac": asset_code,
                        "addr": addr,
                        "city": city_val,
                        "iid": source_issuance_id,
                        "h": h,
                    },
                )
                return True
            if row.address_hash == h:
                return False
            conn.execute(
                text(
                    """
                    UPDATE asset_locations
                    SET raw_address = :addr,
                        city = :city,
                        source_issuance_id = :iid,
                        address_hash = :h,
                        geocode_status = 'pending',
                        geocode_provider = NULL,
                        geocode_level = NULL,
                        geocode_error = NULL,
                        geocoded_at = NULL,
                        latitude = NULL,
                        longitude = NULL,
                        province = NULL,
                        district = NULL,
                        formatted_address = NULL,
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": row.id,
                    "addr": addr,
                    "city": city_val,
                    "iid": source_issuance_id,
                    "h": h,
                },
            )
            return True

    def fetch_pending_for_geocode(self, limit: int = 200) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, trust_product_id, asset_code, raw_address, city
                    FROM asset_locations
                    WHERE geocode_status IN ('pending', 'failed')
                      AND raw_address IS NOT NULL
                      AND TRIM(raw_address) <> ''
                    ORDER BY updated_at ASC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).fetchall()
        return rows_to_dicts(rows)

    def count_pending_geocode(self) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM asset_locations
                    WHERE geocode_status IN ('pending', 'failed')
                      AND raw_address IS NOT NULL
                      AND TRIM(raw_address) <> ''
                    """
                ),
            ).fetchone()
        return int(row.cnt) if row else 0

    def mark_geocode_success(
        self,
        location_id: int,
        *,
        latitude: float,
        longitude: float,
        province: str | None,
        city: str | None,
        district: str | None,
        formatted_address: str | None,
        geocode_level: str | None,
        provider: str = "amap",
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE asset_locations
                    SET latitude = :lat,
                        longitude = :lng,
                        province = :province,
                        city = COALESCE(city, :city),
                        district = :district,
                        formatted_address = :formatted,
                        geocode_status = 'success',
                        geocode_provider = :provider,
                        geocode_level = :level,
                        geocode_error = NULL,
                        geocoded_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": location_id,
                    "lat": latitude,
                    "lng": longitude,
                    "province": province,
                    "city": city,
                    "district": district,
                    "formatted": formatted_address,
                    "provider": provider,
                    "level": geocode_level,
                },
            )

    def mark_geocode_failed(self, location_id: int, error: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE asset_locations
                    SET geocode_status = 'failed',
                        geocode_error = :err,
                        geocoded_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": location_id, "err": error[:2000]},
            )

    def fetch_issuance_backfill_rows(self) -> list[dict]:
        """Latest issuance row per (trust_product_id, asset_code) with address."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (ta.trust_product_id, ta.asset_code)
                        i.id AS source_issuance_id,
                        ta.trust_product_id,
                        ta.asset_code,
                        i.property_address AS raw_address,
                        i.city
                    FROM trust_product_issuance_asset_records i
                    INNER JOIN trust_assets ta
                        ON ta.trust_product_id = i.trust_product_id
                       AND ta.custody_asset_code = i.custody_asset_code
                    WHERE i.property_address IS NOT NULL
                      AND TRIM(i.property_address) <> ''
                    ORDER BY ta.trust_product_id, ta.asset_code,
                             i.issue_date DESC, i.id DESC
                    """
                ),
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_map_cities(self) -> list[dict]:
        """Cities from issuance excluding 未知, with monitor + geocode stats."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    WITH issuance_cities AS (
                        SELECT DISTINCT COALESCE(NULLIF(TRIM(city), ''), :unknown) AS city
                        FROM trust_product_issuance_asset_records
                        WHERE COALESCE(NULLIF(TRIM(city), ''), :unknown) <> :unknown
                    ),
                    product_latest AS (
                        SELECT trust_product_id, MAX(data_date) AS data_date
                        FROM trust_asset_monitor_records
                        GROUP BY trust_product_id
                    ),
                    monitor_by_city AS (
                        SELECT
                            COALESCE(NULLIF(TRIM(al.city), ''), :unknown) AS city,
                            COUNT(DISTINCT (m.trust_product_id, m.asset_code)) AS monitor_count
                        FROM trust_asset_monitor_records m
                        INNER JOIN product_latest pl
                            ON pl.trust_product_id = m.trust_product_id
                           AND m.data_date = pl.data_date
                        INNER JOIN asset_locations al
                            ON al.trust_product_id = m.trust_product_id
                           AND al.asset_code = m.asset_code
                        WHERE COALESCE(NULLIF(TRIM(al.city), ''), :unknown) <> :unknown
                        GROUP BY 1
                    ),
                    geocoded_by_city AS (
                        SELECT
                            COALESCE(NULLIF(TRIM(city), ''), :unknown) AS city,
                            COUNT(*) AS geocoded_count
                        FROM asset_locations
                        WHERE geocode_status = 'success'
                          AND latitude IS NOT NULL
                          AND longitude IS NOT NULL
                          AND COALESCE(NULLIF(TRIM(city), ''), :unknown) <> :unknown
                        GROUP BY 1
                    )
                    SELECT
                        ic.city,
                        COALESCE(mc.monitor_count, 0) AS monitor_count,
                        COALESCE(gc.geocoded_count, 0) AS geocoded_count
                    FROM issuance_cities ic
                    LEFT JOIN monitor_by_city mc ON mc.city = ic.city
                    LEFT JOIN geocoded_by_city gc ON gc.city = ic.city
                    ORDER BY ic.city
                    """
                ),
                {"unknown": UNKNOWN_CITY},
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_map_points(self, city: str) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    WITH product_latest AS (
                        SELECT trust_product_id, MAX(data_date) AS data_date
                        FROM trust_asset_monitor_records
                        GROUP BY trust_product_id
                    ),
                    monitor_agg AS (
                        SELECT
                            m.trust_product_id,
                            tp.name AS trust_product_name,
                            m.asset_code,
                            pl.data_date,
                            MAX(m.overdue_days) AS overdue_days,
                            SUM(m.remaining_amount) AS remaining_amount
                        FROM trust_asset_monitor_records m
                        INNER JOIN product_latest pl
                            ON pl.trust_product_id = m.trust_product_id
                           AND m.data_date = pl.data_date
                        INNER JOIN trust_products tp ON tp.id = m.trust_product_id
                        GROUP BY m.trust_product_id, tp.name, m.asset_code, pl.data_date
                    )
                    SELECT
                        ma.trust_product_id,
                        ma.trust_product_name,
                        ma.asset_code,
                        ma.data_date,
                        ma.overdue_days,
                        ma.remaining_amount,
                        al.latitude,
                        al.longitude,
                        al.formatted_address,
                        al.raw_address,
                        al.city AS location_city
                    FROM monitor_agg ma
                    INNER JOIN asset_locations al
                        ON al.trust_product_id = ma.trust_product_id
                       AND al.asset_code = ma.asset_code
                    WHERE al.geocode_status = 'success'
                      AND al.latitude IS NOT NULL
                      AND al.longitude IS NOT NULL
                      AND COALESCE(NULLIF(TRIM(al.city), ''), :unknown) = :city
                    ORDER BY ma.overdue_days DESC NULLS LAST, ma.asset_code
                    """
                ),
                {"city": city, "unknown": UNKNOWN_CITY},
            ).fetchall()
        return rows_to_dicts(rows)

    def create_geocode_run(self, triggered_by: str, pending_count: int) -> int:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO spatial_geocode_runs (
                        status, triggered_by, pending_count
                    ) VALUES ('running', :by, :pending)
                    RETURNING id
                    """
                ),
                {"by": triggered_by, "pending": pending_count},
            ).fetchone()
        return int(row.id)

    def finish_geocode_run(
        self,
        run_id: int,
        *,
        status: str,
        success_count: int,
        failed_count: int,
        error_message: str | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE spatial_geocode_runs
                    SET status = :status,
                        success_count = :success,
                        failed_count = :failed,
                        error_message = :err,
                        finished_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "status": status,
                    "success": success_count,
                    "failed": failed_count,
                    "err": error_message,
                },
            )

    def fetch_latest_geocode_run(self) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM spatial_geocode_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                ),
            ).fetchone()
        return row_to_dict(row)

    def has_running_geocode_run(self) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1 FROM spatial_geocode_runs
                    WHERE status = 'running'
                    LIMIT 1
                    """
                ),
            ).fetchone()
        return row is not None
