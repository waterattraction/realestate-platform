"""手工结算 API — 录入 / 修改 / 作废 + 附件下载。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import auth
from app import manual_settlement as ms
from app import query_utils
from app.db import get_engine

router = APIRouter(tags=["manual-settlements"])

_engine = get_engine()
_get_user = auth.make_current_user_dependency(_engine)


def _safe_return_to(raw: str | None) -> str | None:
    if not raw:
        return None
    path = str(raw).strip()
    if not path.startswith("/"):
        return None
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc or parsed.path != "/overdue":
        return None
    return path


def _workbench_redirect(
    trust_product_id: int,
    asset_code: str,
    *,
    request: Request | None = None,
) -> str:
    qs = (
        f"?trust_product_id={trust_product_id}"
        f"&asset_code={quote(asset_code)}"
        f"&settlement_expanded=1"
    )
    if request is not None:
        bucket = query_utils.clean_optional_str(
            request.query_params.get("delinquency_bucket")
        )
        if bucket:
            qs += f"&delinquency_bucket={quote(bucket)}"
        rt = _safe_return_to(request.query_params.get("return_to"))
        if rt:
            qs += f"&return_to={quote(rt, safe='')}"
    return f"/overdue/workbench{qs}"


def _parse_settlement_fields(
    *,
    asset_code: str,
    settlement_date: str,
    amount: str,
) -> tuple[str, object, float]:
    ac = query_utils.clean_optional_str(asset_code) or ""
    if not ac:
        raise HTTPException(status_code=400, detail="资产主编号不能为空")
    parsed_date = query_utils.parse_optional_date(settlement_date)
    if not parsed_date:
        raise HTTPException(status_code=400, detail="请提供有效结算日期")
    try:
        from datetime import date as date_cls

        as_of = date_cls.fromisoformat(parsed_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="结算日期格式无效") from exc
    try:
        amt = float(str(amount).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="结算金额无效") from exc
    return ac, as_of, amt


def _username(current_user: dict | None) -> str | None:
    return (
        (current_user or {}).get("username")
        or (current_user or {}).get("name")
        or None
    )


@router.post("/overdue/workbench/manual-settlements")
async def create_manual_settlement(
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(...),
    settlement_date: str = Form(...),
    settled_by: str = Form(...),
    payer: str = Form(...),
    repayer: str = Form(""),
    amount: str = Form(...),
    description: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    redirect_to_workbench: str | None = Form("1"),
):
    ac, as_of, amt = _parse_settlement_fields(
        asset_code=asset_code, settlement_date=settlement_date, amount=amount
    )
    file_list = files if isinstance(files, list) else ([files] if files else [])

    with _engine.begin() as conn:
        settlement = ms.create_settlement(
            conn,
            trust_product_id=int(trust_product_id),
            asset_code=ac,
            settlement_date=as_of,
            settled_by=settled_by,
            payer=payer,
            repayer=repayer,
            amount=amt,
            description=description,
            created_by=str(_username(current_user)) if _username(current_user) else None,
        )
        sid = int(settlement["id"])
        saved = await ms.save_settlement_files(sid, file_list)
        if saved:
            ms.insert_attachments(conn, sid, saved)

    if redirect_to_workbench:
        return RedirectResponse(
            url=_workbench_redirect(int(trust_product_id), ac, request=request),
            status_code=303,
        )
    return {"ok": True, "settlement_id": sid}


@router.post("/overdue/workbench/manual-settlements/{settlement_id}")
async def update_manual_settlement(
    settlement_id: int,
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(...),
    settlement_date: str = Form(...),
    settled_by: str = Form(...),
    payer: str = Form(...),
    repayer: str = Form(""),
    amount: str = Form(...),
    description: str = Form(""),
    remove_attachment_ids: list[int] = Form(default=[]),
    files: list[UploadFile] = File(default=[]),
    redirect_to_workbench: str | None = Form("1"),
):
    del current_user  # auth only
    ac, as_of, amt = _parse_settlement_fields(
        asset_code=asset_code, settlement_date=settlement_date, amount=amount
    )
    file_list = files if isinstance(files, list) else ([files] if files else [])
    remove_ids = (
        remove_attachment_ids
        if isinstance(remove_attachment_ids, list)
        else ([remove_attachment_ids] if remove_attachment_ids else [])
    )

    with _engine.begin() as conn:
        ms.update_settlement(
            conn,
            int(settlement_id),
            trust_product_id=int(trust_product_id),
            asset_code=ac,
            settlement_date=as_of,
            settled_by=settled_by,
            payer=payer,
            repayer=repayer,
            amount=amt,
            description=description,
        )
        if remove_ids:
            ms.delete_attachments(
                conn, settlement_id=int(settlement_id), attachment_ids=remove_ids
            )
        existing = ms.count_attachments(conn, int(settlement_id))
        saved = await ms.save_settlement_files(
            int(settlement_id), file_list, existing_attachment_count=existing
        )
        if saved:
            ms.insert_attachments(conn, int(settlement_id), saved)

    if redirect_to_workbench:
        return RedirectResponse(
            url=_workbench_redirect(int(trust_product_id), ac, request=request),
            status_code=303,
        )
    return {"ok": True, "settlement_id": int(settlement_id)}


@router.post("/overdue/workbench/manual-settlements/{settlement_id}/delete")
async def delete_manual_settlement(
    settlement_id: int,
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(...),
    redirect_to_workbench: str | None = Form("1"),
):
    ac = query_utils.clean_optional_str(asset_code) or ""
    if not ac:
        raise HTTPException(status_code=400, detail="资产主编号不能为空")
    with _engine.begin() as conn:
        ms.void_settlement(
            conn,
            int(settlement_id),
            trust_product_id=int(trust_product_id),
            asset_code=ac,
            voided_by=str(_username(current_user)) if _username(current_user) else None,
        )

    if redirect_to_workbench:
        return RedirectResponse(
            url=_workbench_redirect(int(trust_product_id), ac, request=request),
            status_code=303,
        )
    return {"ok": True, "settlement_id": int(settlement_id), "deleted": True}


@router.get("/overdue/workbench/manual-settlements/attachments/{attachment_id}")
def download_manual_settlement_attachment(
    attachment_id: int,
    current_user: Annotated[dict, Depends(_get_user)],
):
    del current_user
    with _engine.connect() as conn:
        att = ms.get_attachment(conn, int(attachment_id))
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = ms.upload_root() / str(att["stored_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件缺失")
    fname = att.get("file_name") or path.name
    return FileResponse(
        path,
        media_type=att.get("content_type") or "application/octet-stream",
        headers={
            "Content-Disposition": ms.attachment_content_disposition(
                fname, att.get("content_type")
            )
        },
    )
