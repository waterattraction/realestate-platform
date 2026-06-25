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
from app.service.followup_upload import save_entry_files, upload_root

router = APIRouter(tags=["overdue-followups"])

_engine = get_engine()
_repo = FollowupRepo(_engine)
_get_user = auth.make_current_user_dependency(_engine)


@router.post("/overdue/workbench/followups/entries")
async def create_followup_entry(
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    custody_asset_code: str = Form(...),
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
    custody = query_utils.clean_optional_str(custody_asset_code) or ""
    try:
        result = _repo.insert_entry_and_update_case(
            trust_product_id=trust_product_id,
            custody_asset_code=custody,
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
        saved = await save_entry_files(result["case_id"], result["entry_id"], files)
        attachments = _repo.insert_attachments(
            result["entry_id"], saved, current_user.get("username")
        )
        result["attachments"] = attachments

    if redirect_to_workbench:
        qs = f"?trust_product_id={trust_product_id}&custody_asset_code={quote(custody)}"
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
    return FileResponse(
        path=resolved,
        filename=att["file_name"],
        media_type=att.get("content_type") or "application/octet-stream",
    )
