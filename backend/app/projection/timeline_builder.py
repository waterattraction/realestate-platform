from app.projection.constants import (
    BUILDER_VERSION_TIMELINE,
    TIMELINE_VERSION,
)
from app.projection.meta import build_meta, wrap_projection
from app.projection.scope import resolve_trust_asset_id
from app.repo.event_repo import EventRepo
from app.repo.issuance_repo import IssuanceRepo
from app.repo.trust_asset_repo import TrustAssetRepo


def _occurred_sort_key(event: dict) -> str:
    return str(event.get("occurred_at") or "")


class TimelineBuilder:
    def __init__(
        self,
        issuance_repo: IssuanceRepo,
        event_repo: EventRepo,
        trust_asset_repo: TrustAssetRepo,
    ):
        self._issuance_repo = issuance_repo
        self._event_repo = event_repo
        self._trust_asset_repo = trust_asset_repo

    def build(self, identity_id: int) -> dict | None:
        issuance = self._issuance_repo.fetch_by_identity_id(identity_id)
        if not issuance:
            return None

        events: list[dict] = []
        issuance_event = self._event_repo.fetch_issuance_event(identity_id)
        if issuance_event:
            events.append(issuance_event)

        trust_asset_id = resolve_trust_asset_id(issuance, self._trust_asset_repo)
        if trust_asset_id:
            events.extend(self._event_repo.fetch_monitor_events(trust_asset_id))
            events.extend(self._event_repo.fetch_repayment_events(trust_asset_id))
            events.extend(self._event_repo.fetch_risk_events(trust_asset_id))
            events.extend(self._event_repo.fetch_followup_events(trust_asset_id))

        events.sort(key=_occurred_sort_key, reverse=True)

        data = {
            "identity_id": identity_id,
            "projection_kind": "asset_timeline",
            "events": events,
        }
        meta = build_meta(
            builder_version=BUILDER_VERSION_TIMELINE,
            timeline_version=TIMELINE_VERSION,
        )
        return wrap_projection(data, meta)
