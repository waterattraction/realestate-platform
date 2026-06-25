"""Phase-0 in-memory projection cache — invalidate on rebuild."""

from app.projection.meta import utc_now_iso


class ProjectionCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[int, str], dict] = {}
        self._inv_version: dict[int, int] = {}

    def inv_version(self, identity_id: int) -> int:
        return self._inv_version.get(identity_id, 0)

    def invalidate(self, identity_id: int) -> int:
        next_ver = self.inv_version(identity_id) + 1
        self._inv_version[identity_id] = next_ver
        for key in list(self._entries):
            if key[0] == identity_id:
                del self._entries[key]
        return next_ver

    def get(self, identity_id: int, kind: str) -> dict | None:
        return self._entries.get((identity_id, kind))

    def put(self, identity_id: int, kind: str, projection: dict) -> dict:
        if projection is None:
            return projection
        meta = projection.get("meta")
        if isinstance(meta, dict):
            meta = {**meta, "cache_inv_version": self.inv_version(identity_id)}
            projection = {**projection, "meta": meta}
        self._entries[(identity_id, kind)] = projection
        return projection
