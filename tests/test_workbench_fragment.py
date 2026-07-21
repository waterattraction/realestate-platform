"""Workbench detail fragment helpers (partial refresh)."""

from app.html.render import (
    build_workbench_fragment_payload,
    render_overdue_workbench_html,
    render_workbench_detail_main,
)
from app.service.overdue_workbench import OverdueWorkbenchService


def _empty_dto(**overrides):
    dto = {
        "trust_product_id": 1,
        "asset_code": "107112622529",
        "identity_id": 42,
        "data_date": "2026-07-17",
        "filters": {
            "list_product_scope_explicit": True,
            "list_product_ids": [1, 2],
            "delinquency_buckets": ["M0_PLUS"],
        },
        "asset": {
            "asset_code": "107112622529",
            "custody_asset_codes": ["107112622529"],
            "selected_trust_asset_id": 11,
            "selected_split": {"trust_asset_id": 11},
            "summary": {"internal_status": "待跟进(1)", "overdue_days": 8},
            "checks": None,
            "issuance_records": [],
            "repayment": {},
            "monitor": {"splits": [{"trust_asset_id": 11}]},
            "trust_mark": {"internal_status": "待跟进(1)"},
            "timeline": [],
            "ops": None,
            "followup_case": None,
            "followup_cases": [],
            "followup_entries": [{"id": 7, "case_id": 3}],
        },
        "queue_patch": {
            "trust_product_id": 1,
            "asset_code": "107112622529",
            "internal_status": "待跟进(1)",
            "followup_count": 1,
        },
        "asset_list": {"data_date": "2026-07-17", "items": []},
    }
    dto.update(overrides)
    return dto


def test_build_asset_panel_dto_maps_detail():
    detail = {
        "asset_code": "A1",
        "custody_asset_codes": ["A1-1"],
        "selected_asset_id": 9,
        "detail": {"x": 1},
        "summary": {"overdue_days": 0},
        "checks": None,
        "issuance_records": [],
        "repayment": {},
        "monitor": {},
        "trust_mark": None,
        "timeline": [],
        "ops": None,
        "spatial_hint": None,
        "followup_case": None,
        "followup_cases": [],
        "followup_entries": [],
    }
    asset = OverdueWorkbenchService.build_asset_panel_dto(detail)
    assert asset["asset_code"] == "A1"
    assert asset["selected_trust_asset_id"] == 9
    assert asset["selected_split"] == {"x": 1}
    assert OverdueWorkbenchService.build_asset_panel_dto({}) == {}


def test_detail_main_stable_id_and_meta():
    html = render_workbench_detail_main(_empty_dto())
    assert 'id="workbench-detail"' in html
    assert "data-wb-meta=" in html
    assert "detail-grid" in html or "empty" in html


def test_fragment_payload_matches_detail_main():
    dto = _empty_dto()
    payload = build_workbench_fragment_payload(dto, followup_expanded=True)
    assert payload["html"] == render_workbench_detail_main(
        dto, followup_expanded=True
    )
    meta = payload["meta"]
    assert meta["asset_code"] == "107112622529"
    assert meta["trust_product_id"] == 1
    assert meta["identity_id"] == 42
    assert meta["scroll_followup"] is True
    assert meta["queue_patch"]["followup_count"] == 1
    assert "internal_status_html" in meta["queue_patch"]
    assert meta["json_href"].startswith("/overdue/workbench/detail?")


def test_full_page_embeds_same_detail_main():
    dto = _empty_dto()
    page = render_overdue_workbench_html(dto)
    main = render_workbench_detail_main(dto)
    assert main in page
    assert "loadWorkbenchDetail" in page
    assert "pageUrlToFragmentUrl" in page
