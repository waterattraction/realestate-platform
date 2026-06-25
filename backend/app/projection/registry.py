"""Lightweight ProjectionRegistry — Phase 0 hook for swap / cache / rebuild."""

from app.projection.cache import ProjectionCache
from app.projection.meta import utc_now_iso

# M3.3 rebuild order: timeline before snapshot aggregates
REBUILD_ORDER = ("timeline", "snapshot", "operations", "header")


class ProjectionRegistry:
    def __init__(self, cache: ProjectionCache | None = None) -> None:
        self._builders: dict[str, object] = {}
        self._cache = cache or ProjectionCache()

    @property
    def cache(self) -> ProjectionCache:
        return self._cache

    def register(self, kind: str, builder: object) -> None:
        self._builders[kind] = builder

    def get(self, kind: str) -> object:
        if kind not in self._builders:
            raise KeyError(f"projection builder not registered: {kind}")
        return self._builders[kind]

    def build(self, kind: str, identity_id: int, *, use_cache: bool = True) -> dict | None:
        if use_cache:
            cached = self._cache.get(identity_id, kind)
            if cached is not None:
                return cached

        builder = self.get(kind)
        projection = builder.build(identity_id)
        if projection is not None and use_cache:
            projection = self._cache.put(identity_id, kind, projection)
        return projection

    def invalidate(self, identity_id: int) -> int:
        """Bump cache_inv_version and clear cached projections; no DB write, no rebuild."""
        return self._cache.invalidate(identity_id)

    def rebuild_all(self, identity_id: int) -> dict | None:
        """
        Full projection rebuild for one identity (M3.3 A-1).
        Invalidates cache, rebuilds all registered kinds, returns audit envelope.
        """
        inv = self._cache.invalidate(identity_id)
        projections: dict[str, dict | None] = {}
        rebuilt_at = utc_now_iso()

        for kind in REBUILD_ORDER:
            if kind not in self._builders:
                continue
            projections[kind] = self.build(kind, identity_id, use_cache=True)

        if projections.get("header") is None:
            return None

        return {
            "identity_id": identity_id,
            "rebuilt_at": rebuilt_at,
            "cache_inv_version": inv,
            "kinds": [k for k in REBUILD_ORDER if k in projections],
            "projections": projections,
        }

    def kinds(self) -> list[str]:
        return list(self._builders.keys())
