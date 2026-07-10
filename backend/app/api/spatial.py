"""Spatial P0 API — city gate, map data, geocode refresh."""

import os
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app import auth_html
from app import query_utils
from app.repo.location_repo import UNKNOWN_CITY
from app.service.location_service import build_location_service
from app.service.spatial_map_service import build_spatial_map_service
from app.spatial_constants import city_center
from app.spatial_html import render_spatial_map_gate_html, render_spatial_map_view_html


def _amap_key() -> str:
    return os.getenv("AMAP_API_KEY", "").strip()


def _validate_city(city: str) -> str:
    city = (city or "").strip()
    if not city or city == UNKNOWN_CITY:
        raise HTTPException(status_code=400, detail="Invalid city")
    return city


def build_spatial_router(
    engine,
    get_page_user: Callable,
    get_current_user: Callable,
) -> APIRouter:
    router = APIRouter(tags=["spatial"])

    def require_admin(
        current_user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        return current_user

    @router.get("/spatial/map", response_class=HTMLResponse)
    def spatial_map_gate(
        page_user: Annotated[dict, Depends(get_page_user)],
    ):
        map_svc = build_spatial_map_service(engine)
        loc_svc = build_location_service(engine)
        cities = map_svc.list_cities()
        latest_run = loc_svc._repo.fetch_latest_geocode_run()
        html = render_spatial_map_gate_html(
            cities,
            latest_run=latest_run,
            is_admin=page_user.get("role") == "admin",
        )
        return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))

    @router.get("/spatial/locations/data")
    def spatial_locations_data(
        page_user: Annotated[dict, Depends(get_page_user)],
        city: str = Query(...),
        page: str | None = Query(default=None),
        page_size: str | None = Query(default=None),
        geocode_status: str | None = Query(default=None),
        q: str | None = Query(default=None),
    ):
        city = _validate_city(city)
        page_no, page_sz = query_utils.parse_pagination(page, page_size)
        status = query_utils.clean_optional_str(geocode_status)
        if status and status not in ("pending", "success", "failed", "skipped"):
            status = None
        search = query_utils.clean_optional_str(q)
        svc = build_location_service(engine)
        return svc.list_locations(
            city=city,
            page=page_no,
            page_size=page_sz,
            geocode_status=status,
            q=search,
        )

    @router.get("/spatial/map/view", response_class=HTMLResponse)
    def spatial_map_view(
        page_user: Annotated[dict, Depends(get_page_user)],
        city: str = Query(...),
    ):
        city = _validate_city(city)
        key = _amap_key()
        if not key:
            raise HTTPException(status_code=503, detail="AMAP_API_KEY not configured")
        from urllib.parse import quote

        lng, lat = city_center(city)
        data_url = f"/spatial/map/view/data?city={quote(city)}"
        html = render_spatial_map_view_html(
            city,
            amap_key=key,
            map_data_url=data_url,
            city_center=[lng, lat],
        )
        return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))

    @router.get("/spatial/map/view/data")
    def spatial_map_view_data(
        page_user: Annotated[dict, Depends(get_page_user)],
        city: str = Query(...),
    ):
        city = _validate_city(city)
        svc = build_spatial_map_service(engine)
        return svc.get_map_data(city)

    @router.post("/spatial/geocode/refresh")
    def spatial_geocode_refresh(
        admin_user: Annotated[dict, Depends(require_admin)],
    ):
        loc_svc = build_location_service(engine)
        if loc_svc._repo.has_running_geocode_run():
            raise HTTPException(status_code=409, detail="Geocode task already running")
        try:
            run_id = loc_svc.start_geocode_refresh_async(
                admin_user.get("username") or "admin"
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": run_id, "status": "running"}

    @router.post("/spatial/geocode/refresh/{location_id}")
    def spatial_geocode_refresh_one(
        location_id: int,
        admin_user: Annotated[dict, Depends(require_admin)],
    ):
        loc_svc = build_location_service(engine)
        try:
            item = loc_svc.geocode_single(location_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": item}

    @router.get("/spatial/geocode/runs/latest")
    def spatial_geocode_latest(
        page_user: Annotated[dict, Depends(get_page_user)],
    ):
        repo = build_location_service(engine)._repo
        run = repo.fetch_latest_geocode_run()
        return {"run": run}

    return router
