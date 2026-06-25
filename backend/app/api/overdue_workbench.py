"""Overdue workbench API — thin read layer."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import auth
from app import query_utils
from app.db import get_engine
from app.service.overdue_workbench import build_overdue_workbench_service

router = APIRouter(tags=["overdue-workbench"])

_engine = get_engine()
_service = build_overdue_workbench_service(_engine)
_get_user = auth.make_current_user_dependency(_engine)


@router.get("/overdue/workbench/detail")
def get_overdue_workbench_detail(
    _user: Annotated[dict, Depends(_get_user)],
    trust_product_id: str | None = None,
    custody_asset_code: str | None = None,
    trust_asset_id: str | None = None,
    data_date: str | None = None,
) -> dict:
    return _service.get_detail(
        trust_product_id=query_utils.parse_optional_int(trust_product_id),
        custody_asset_code=query_utils.clean_optional_str(custody_asset_code),
        trust_asset_id=query_utils.parse_optional_int(trust_asset_id),
        data_date=query_utils.parse_optional_date(data_date),
    )


@router.get("/overdue/ops/queue")
def get_overdue_ops_queue(
    _user: Annotated[dict, Depends(_get_user)],
    trust_product_id: str | None = None,
    data_date: str | None = None,
) -> dict:
    pid = query_utils.parse_optional_int(trust_product_id)
    if pid is None:
        return {"trust_product_id": None, "data_date": None, "items": []}
    return _service.get_product_queue(
        pid, query_utils.parse_optional_date(data_date)
    )
