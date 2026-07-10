"""高德 Web 服务地理编码 — Spatial P0 Lite."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class GeocodeError(Exception):
    pass


def get_amap_api_key() -> str:
    key = os.getenv("AMAP_API_KEY", "").strip()
    if not key:
        raise GeocodeError("AMAP_API_KEY is not configured")
    return key


def geocode_address(
    raw_address: str,
    *,
    city: str | None = None,
    sleep_seconds: float = 0.12,
) -> dict:
    """Call Amap geocode API; returns normalized result dict."""
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    key = get_amap_api_key()
    params = {
        "key": key,
        "address": raw_address.strip(),
        "output": "JSON",
    }
    if city and city.strip() and city.strip() != "未知":
        params["city"] = city.strip()

    url = "https://restapi.amap.com/v3/geocode/geo?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise GeocodeError(str(exc)) from exc

    if payload.get("status") != "1":
        raise GeocodeError(payload.get("info") or "Geocode failed")

    geocodes = payload.get("geocodes") or []
    if not geocodes:
        raise GeocodeError("No geocode result")

    first = geocodes[0]
    location = str(first.get("location") or "")
    if "," not in location:
        raise GeocodeError("Invalid location in response")

    lng_str, lat_str = location.split(",", 1)
    province = first.get("province") or None
    city_name = first.get("city") or None
    if city_name in ("[]", ""):
        city_name = None
    district = first.get("district") or None
    if district in ("[]", ""):
        district = None

    return {
        "latitude": float(lat_str),
        "longitude": float(lng_str),
        "province": province,
        "city": city_name,
        "district": district,
        "formatted_address": first.get("formatted_address") or raw_address,
        "geocode_level": first.get("level") or None,
        "provider": "amap",
    }
