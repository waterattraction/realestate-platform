"""Map monitor read service — Spatial P0 consumer."""

from __future__ import annotations

from urllib.parse import urlencode

from sqlalchemy.engine import Engine

from app.repo.location_repo import LocationRepo, UNKNOWN_CITY
from app.service import checks_service


class SpatialMapService:
    def __init__(self, engine: Engine):
        self._repo = LocationRepo(engine)

    def list_cities(self) -> list[dict]:
        return self._repo.fetch_map_cities()

    def get_map_data(self, city: str) -> dict:
        city = (city or "").strip()
        if not city or city == UNKNOWN_CITY:
            raise ValueError("Invalid city")
        rows = self._repo.fetch_map_points(city)
        items = []
        for row in rows:
            remaining = float(row.get("remaining_amount") or 0)
            if checks_service.is_es_closed(remaining):
                bucket = "ES"
                overdue_days = None
            else:
                overdue_days = int(row.get("overdue_days") or 0)
                bucket = checks_service.calc_risk_level(overdue_days, remaining)

            pid = int(row["trust_product_id"])
            ac = str(row["asset_code"])
            qs = urlencode({"trust_product_id": pid, "asset_code": ac})
            items.append(
                {
                    "trust_product_id": pid,
                    "trust_product_name": row.get("trust_product_name"),
                    "asset_code": ac,
                    "data_date": str(row.get("data_date") or ""),
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "delinquency_bucket": bucket,
                    "overdue_days": overdue_days,
                    "remaining_amount": remaining,
                    "formatted_address": row.get("formatted_address")
                    or row.get("raw_address"),
                    "workbench_url": f"/overdue/workbench?{qs}",
                }
            )
        by_bucket: dict[str, int] = {}
        products: dict[int, dict] = {}
        for item in items:
            b = str(item["delinquency_bucket"])
            by_bucket[b] = by_bucket.get(b, 0) + 1
            pid = int(item["trust_product_id"])
            if pid not in products:
                products[pid] = {
                    "trust_product_id": pid,
                    "trust_product_name": item.get("trust_product_name"),
                    "count": 0,
                }
            products[pid]["count"] += 1
        return {
            "city": city,
            "items": items,
            "stats": {
                "point_count": len(items),
                "product_count": len(products),
                "by_bucket": by_bucket,
                "products": sorted(
                    products.values(),
                    key=lambda p: (str(p.get("trust_product_name") or ""), p["trust_product_id"]),
                ),
            },
        }


def build_spatial_map_service(engine: Engine) -> SpatialMapService:
    return SpatialMapService(engine)
