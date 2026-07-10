"""Location Lite — upsert from issuance + geocode batch."""

from __future__ import annotations

import logging
import threading

from urllib.parse import urlencode

from sqlalchemy.engine import Engine

from app.repo.location_repo import LocationRepo
from app.service.geocode_amap import GeocodeError, geocode_address

logger = logging.getLogger(__name__)

_geocode_lock = threading.Lock()


class LocationService:
    def __init__(self, engine: Engine):
        self._repo = LocationRepo(engine)
        self._engine = engine

    def upsert_from_issuance_row(
        self,
        *,
        trust_product_id: int,
        asset_code: str,
        raw_address: str,
        city: str | None,
        source_issuance_id: int,
    ) -> bool:
        return self._repo.upsert_from_issuance(
            trust_product_id=trust_product_id,
            asset_code=asset_code,
            raw_address=raw_address,
            city=city,
            source_issuance_id=source_issuance_id,
        )

    def backfill_all_from_issuance(self) -> dict:
        rows = self._repo.fetch_issuance_backfill_rows()
        changed = 0
        for row in rows:
            if self.upsert_from_issuance_row(
                trust_product_id=int(row["trust_product_id"]),
                asset_code=str(row["asset_code"]),
                raw_address=str(row["raw_address"]),
                city=row.get("city"),
                source_issuance_id=int(row["source_issuance_id"]),
            ):
                changed += 1
        return {"total": len(rows), "changed": changed}

    def run_geocode_batch(self, *, limit: int = 200) -> dict:
        pending = self._repo.fetch_pending_for_geocode(limit=limit)
        success = 0
        failed = 0
        for row in pending:
            try:
                result = geocode_address(
                    str(row["raw_address"]),
                    city=row.get("city"),
                )
                self._repo.mark_geocode_success(
                    int(row["id"]),
                    latitude=result["latitude"],
                    longitude=result["longitude"],
                    province=result.get("province"),
                    city=result.get("city"),
                    district=result.get("district"),
                    formatted_address=result.get("formatted_address"),
                    geocode_level=result.get("geocode_level"),
                    provider=result.get("provider") or "amap",
                )
                success += 1
            except GeocodeError as exc:
                self._repo.mark_geocode_failed(int(row["id"]), str(exc))
                failed += 1
        return {"processed": len(pending), "success": success, "failed": failed}

    def start_geocode_refresh_async(self, triggered_by: str, *, limit: int = 500) -> int:
        if not _geocode_lock.acquire(blocking=False):
            raise RuntimeError("Geocode refresh already running")

        pending_count = self._repo.count_pending_geocode()
        run_id = self._repo.create_geocode_run(triggered_by, pending_count)

        def _worker() -> None:
            success_total = 0
            failed_total = 0
            status = "completed"
            err_msg = None
            try:
                remaining = min(limit, max(pending_count, 1))
                while remaining > 0:
                    batch_limit = min(200, remaining)
                    result = self.run_geocode_batch(limit=batch_limit)
                    success_total += result["success"]
                    failed_total += result["failed"]
                    if result["processed"] == 0:
                        break
                    remaining -= result["processed"]
            except Exception as exc:
                status = "failed"
                err_msg = str(exc)
                logger.exception("Geocode refresh failed")
            finally:
                self._repo.finish_geocode_run(
                    run_id,
                    status=status,
                    success_count=success_total,
                    failed_count=failed_total,
                    error_message=err_msg,
                )
                _geocode_lock.release()

        threading.Thread(target=_worker, daemon=True).start()
        return run_id

    def list_locations(
        self,
        *,
        city: str,
        page: int = 1,
        page_size: int = 50,
        geocode_status: str | None = None,
        q: str | None = None,
    ) -> dict:
        page_size = min(max(page_size, 1), 200)
        page = max(page, 1)
        rows, total = self._repo.fetch_locations_page(
            city=city,
            page=page,
            page_size=page_size,
            geocode_status=geocode_status,
            q=q,
        )
        items = [self._location_item_dto(row) for row in rows]
        return {
            "city": city.strip(),
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": items,
        }

    def geocode_single(self, location_id: int) -> dict:
        row = self._repo.fetch_by_id(location_id)
        if row is None:
            raise ValueError("Location not found")
        raw = str(row.get("raw_address") or "").strip()
        if not raw:
            raise ValueError("No address to geocode")
        try:
            result = geocode_address(raw, city=row.get("city"))
            self._repo.mark_geocode_success(
                location_id,
                latitude=result["latitude"],
                longitude=result["longitude"],
                province=result.get("province"),
                city=result.get("city"),
                district=result.get("district"),
                formatted_address=result.get("formatted_address"),
                geocode_level=result.get("geocode_level"),
                provider=result.get("provider") or "amap",
            )
        except GeocodeError as exc:
            self._repo.mark_geocode_failed(location_id, str(exc))
        updated = self._repo.fetch_by_id(location_id)
        if updated is None:
            raise ValueError("Location not found after geocode")
        return self._location_item_dto(updated)

    def _location_item_dto(self, row: dict) -> dict:
        pid = int(row["trust_product_id"])
        ac = str(row["asset_code"])
        qs = urlencode({"trust_product_id": pid, "asset_code": ac})
        lat = row.get("latitude")
        lng = row.get("longitude")
        coord = None
        if lat is not None and lng is not None:
            coord = f"{float(lat):.6f}, {float(lng):.6f}"
        contract = row.get("contract_name") or ""
        debtor = row.get("debtor_name") or ""
        listing = contract or debtor or "—"
        return {
            "location_id": int(row.get("location_id") or row["id"]),
            "trust_product_id": pid,
            "trust_product_name": row.get("trust_product_name"),
            "asset_code": ac,
            "property_id": row.get("property_id"),
            "listing_label": listing,
            "contract_name": contract or None,
            "debtor_name": debtor or None,
            "custody_asset_code": row.get("custody_asset_code"),
            "raw_address": row.get("raw_address"),
            "issuance_address": row.get("issuance_address"),
            "city": row.get("city"),
            "issuance_city": row.get("issuance_city"),
            "province": row.get("province"),
            "district": row.get("district"),
            "formatted_address": row.get("formatted_address"),
            "latitude": float(lat) if lat is not None else None,
            "longitude": float(lng) if lng is not None else None,
            "coordinates": coord,
            "geocode_status": row.get("geocode_status"),
            "geocode_provider": row.get("geocode_provider"),
            "geocode_level": row.get("geocode_level"),
            "geocode_error": row.get("geocode_error"),
            "geocoded_at": (
                str(row["geocoded_at"]) if row.get("geocoded_at") is not None else None
            ),
            "location_source": row.get("location_source"),
            "source_issuance_id": row.get("source_issuance_id"),
            "address_hash": row.get("address_hash"),
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
            "workbench_url": f"/overdue/workbench?{qs}",
        }

    def get_spatial_hint(
        self, trust_product_id: int | None, asset_code: str | None
    ) -> dict | None:
        if trust_product_id is None or not asset_code:
            return None
        loc = self._repo.fetch_by_product_asset(trust_product_id, asset_code)
        if loc is None:
            return {
                "label": "该资产暂无地图坐标（尚未从发行回填地址）",
                "ready": False,
            }
        status = loc.get("geocode_status")
        if status == "success" and loc.get("latitude") is not None:
            return None
        if status == "pending":
            return {
                "label": "该资产暂无地图坐标（Geocode 排队中）",
                "ready": False,
            }
        return {
            "label": "该资产暂无地图坐标（Geocode 未成功），请由管理员在首页 → 地图监控刷新地理编码",
            "ready": False,
        }


def build_location_service(engine: Engine) -> LocationService:
    return LocationService(engine)
