"""Spatial map constants — city centers (lng, lat) for AMap."""

# AMap uses [longitude, latitude]
CITY_CENTERS: dict[str, tuple[float, float]] = {
    "上海": (121.473701, 31.230416),
    "北京": (116.407396, 39.904211),
}

DEFAULT_CENTER = (116.407396, 39.904211)
DEFAULT_ZOOM = 11


def city_center(city: str) -> tuple[float, float]:
    key = (city or "").strip()
    return CITY_CENTERS.get(key, DEFAULT_CENTER)
