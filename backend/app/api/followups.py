"""Followup write API — single entry POST + attachments."""

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import auth
from app import query_utils
from app.db import get_engine
from app.repo.followup_repo import FollowupRepo
from app.service.followup_upload import (
    attachment_content_disposition,
    save_entry_files,
    upload_root,
)

router = APIRouter(tags=["overdue-followups"])

_engine = get_engine()
_repo = FollowupRepo(_engine)
_get_user = auth.make_current_user_dependency(_engine)


@router.post("/overdue/workbench/followups/entries")
async def create_followup_entry(
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    data_date: str = Form(...),
    status: str = Form("in_progress"),
    owner_name: str = Form(""),
    overdue_reason: str = Form(""),
    follow_up_plan: str = Form(""),
    trust_feedback: str = Form(""),
    note: str = Form(""),
    entry_type: str = Form("manual"),
    redirect_to_workbench: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    ac = query_utils.clean_optional_str(asset_code) or ""
    if not ac and custody_asset_code:
        from app.service.overdue_workbench import build_overdue_workbench_service

        svc = build_overdue_workbench_service(_engine)
        resolved = svc.resolve_asset_code(
            trust_product_id,
            query_utils.clean_optional_str(custody_asset_code) or "",
            data_date,
        )
        ac = resolved or ""
    if not ac:
        raise HTTPException(status_code=400, detail="asset_code is required")

    try:
        result = _repo.insert_entry_and_update_case(
            trust_product_id=trust_product_id,
            asset_code=ac,
            data_date=data_date,
            status=status or "in_progress",
            owner_name=owner_name or None,
            overdue_reason=overdue_reason or None,
            follow_up_plan=follow_up_plan or None,
            trust_feedback=trust_feedback or None,
            note=note or None,
            entry_type=entry_type or "manual",
            created_by=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if files:
        saved = await save_entry_files(
            result["case_id"],
            result["entry_id"],
            files,
            existing_attachment_count=0,
        )
        attachments = _repo.insert_attachments(
            result["entry_id"], saved, current_user.get("username")
        )
        result["attachments"] = attachments

    if redirect_to_workbench:
        qs = f"?trust_product_id={trust_product_id}&asset_code={quote(ac)}"
        return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)

    return result


@router.post("/overdue/workbench/followups/entries/{entry_id}")
async def update_followup_entry(
    entry_id: int,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    data_date: str = Form(""),
    status: str = Form("in_progress"),
    owner_name: str = Form(""),
    overdue_reason: str = Form(""),
    follow_up_plan: str = Form(""),
    trust_feedback: str = Form(""),
    note: str = Form(""),
    redirect_to_workbench: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    ac = query_utils.clean_optional_str(asset_code) or ""
    if not ac and custody_asset_code:
        from app.service.overdue_workbench import build_overdue_workbench_service

        svc = build_overdue_workbench_service(_engine)
        resolved = svc.resolve_asset_code(
            trust_product_id,
            query_utils.clean_optional_str(custody_asset_code) or "",
            data_date or None,
        )
        ac = resolved or ""
    if not ac:
        raise HTTPException(status_code=400, detail="asset_code is required")

    try:
        result = _repo.update_in_progress_entry(
            entry_id=entry_id,
            trust_product_id=trust_product_id,
            asset_code=ac,
            status=status or "in_progress",
            owner_name=owner_name or None,
            overdue_reason=overdue_reason or None,
            follow_up_plan=follow_up_plan or None,
            trust_feedback=trust_feedback or None,
            note=note or None,
            updated_by=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if files:
        existing_count = _repo.count_attachments_for_entry(result["entry_id"])
        saved = await save_entry_files(
            result["case_id"],
            result["entry_id"],
            files,
            existing_attachment_count=existing_count,
        )
        attachments = _repo.insert_attachments(
            result["entry_id"], saved, current_user.get("username")
        )
        result["attachments"] = attachments

    if redirect_to_workbench:
        qs = f"?trust_product_id={trust_product_id}&asset_code={quote(ac)}"
        return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)

    return result


@router.get("/overdue/workbench/attachments/{attachment_id}")
def download_followup_attachment(
    attachment_id: int,
    current_user: Annotated[dict, Depends(_get_user)],
):
    att = _repo.fetch_attachment(attachment_id)
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    full_path = upload_root() / att["stored_path"]
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")
    resolved = full_path.resolve()
    if not str(resolved).startswith(str(upload_root().resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    file_name = str(att["file_name"])
    media_type = att.get("content_type") or "application/octet-stream"
    disposition = attachment_content_disposition(file_name, media_type)
    return FileResponse(
        path=resolved,
        filename=file_name,
        media_type=media_type,
        content_disposition_type=disposition,
    )
