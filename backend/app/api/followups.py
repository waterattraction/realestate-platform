"""Followup write API — cases + entries + attachments."""

from typing import Annotated
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import auth
from app import query_utils
from app.db import get_engine
from app.repo.followup_repo import (
    CASE_CATEGORIES,
    DEFAULT_CASE_CATEGORY,
    DEFAULT_CASE_STATUS,
    FollowupRepo,
)
from app.service.followup_upload import (
    attachment_content_disposition,
    save_entry_files,
    upload_root,
)

router = APIRouter(tags=["overdue-followups"])


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


def _workbench_followup_redirect_qs(
    trust_product_id: int,
    asset_code: str,
    *,
    case_id: int | None = None,
    entry_id: int | None = None,
    new_case: bool = False,
    request: Request | None = None,
) -> str:
    qs = (
        f"?trust_product_id={trust_product_id}"
        f"&asset_code={quote(asset_code)}"
        f"&followup_expanded=1"
    )
    if case_id is not None:
        qs += f"&followup_case_id={case_id}"
    if entry_id is not None:
        qs += f"&followup_entry_id={entry_id}"
    if new_case:
        qs += "&new_followup_case=1"
    if request is not None:
        bucket = query_utils.clean_optional_str(request.query_params.get("delinquency_bucket"))
        if bucket:
            qs += f"&delinquency_bucket={quote(bucket)}"
        rt = _safe_return_to(request.query_params.get("return_to"))
        if rt:
            qs += f"&return_to={quote(rt, safe='')}"
    return qs


def _resolve_asset_code(
    trust_product_id: int,
    asset_code: str,
    custody_asset_code: str,
    data_date: str | None,
) -> str:
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
    return ac


_engine = get_engine()
_repo = FollowupRepo(_engine)
_get_user = auth.make_current_user_dependency(_engine)


@router.post("/overdue/workbench/followups/cases")
async def create_followup_case(
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    data_date: str = Form(...),
    category: str = Form(DEFAULT_CASE_CATEGORY),
    description: str = Form(""),
    status: str = Form(DEFAULT_CASE_STATUS),
    owner_name: str = Form(""),
    redirect_to_workbench: str | None = Form(None),
):
    ac = _resolve_asset_code(
        trust_product_id, asset_code, custody_asset_code, data_date
    )
    cat = (category or DEFAULT_CASE_CATEGORY).strip()
    if cat not in CASE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {cat}")
    try:
        result = _repo.create_case(
            trust_product_id=trust_product_id,
            asset_code=ac,
            data_date=data_date,
            category=cat,
            description=description or None,
            status=status or DEFAULT_CASE_STATUS,
            owner_name=owner_name or None,
            created_by=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if redirect_to_workbench:
        qs = _workbench_followup_redirect_qs(
            trust_product_id, ac, case_id=int(result["case_id"]), request=request
        )
        return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)
    return result


@router.post("/overdue/workbench/followups/cases/{case_id}")
async def update_followup_case(
    case_id: int,
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    data_date: str = Form(""),
    status: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    owner_name: str = Form(""),
    redirect_to_workbench: str | None = Form(None),
):
    ac = _resolve_asset_code(
        trust_product_id, asset_code, custody_asset_code, data_date or None
    )
    try:
        result = _repo.update_case(
            case_id=case_id,
            trust_product_id=trust_product_id,
            asset_code=ac,
            status=status or None,
            category=category or None,
            description=description if description != "" else None,
            owner_name=owner_name or None,
            updated_by=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if redirect_to_workbench:
        qs = _workbench_followup_redirect_qs(
            trust_product_id, ac, case_id=case_id, request=request
        )
        return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)
    return result


@router.post("/overdue/workbench/followups/entries")
async def create_followup_entry(
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    data_date: str = Form(""),
    case_id: int = Form(...),
    owner_name: str = Form(""),
    overdue_reason: str = Form(""),
    follow_up_plan: str = Form(""),
    entry_type: str = Form("manual"),
    redirect_to_workbench: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    # 兼容旧表单字段（忽略）
    status: str = Form(""),
    trust_feedback: str = Form(""),
    note: str = Form(""),
):
    del status, trust_feedback, note
    ac = _resolve_asset_code(
        trust_product_id, asset_code, custody_asset_code, data_date or None
    )
    try:
        result = _repo.insert_entry(
            case_id=case_id,
            trust_product_id=trust_product_id,
            asset_code=ac,
            owner_name=owner_name or None,
            overdue_reason=overdue_reason or None,
            follow_up_plan=follow_up_plan or None,
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
        qs = _workbench_followup_redirect_qs(
            trust_product_id,
            ac,
            case_id=int(result["case_id"]),
            entry_id=int(result["entry_id"]),
            request=request,
        )
        return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)

    return result


@router.post("/overdue/workbench/followups/entries/{entry_id}")
async def update_followup_entry(
    entry_id: int,
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    data_date: str = Form(""),
    owner_name: str = Form(""),
    overdue_reason: str = Form(""),
    follow_up_plan: str = Form(""),
    redirect_to_workbench: str | None = Form(None),
    remove_attachment_ids: list[int] = Form(default=[]),
    files: list[UploadFile] = File(default=[]),
    status: str = Form(""),
    trust_feedback: str = Form(""),
    note: str = Form(""),
):
    del status, trust_feedback, note
    ac = _resolve_asset_code(
        trust_product_id, asset_code, custody_asset_code, data_date or None
    )
    try:
        result = _repo.update_entry(
            entry_id=entry_id,
            trust_product_id=trust_product_id,
            asset_code=ac,
            owner_name=owner_name or None,
            overdue_reason=overdue_reason or None,
            follow_up_plan=follow_up_plan or None,
            updated_by=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if remove_attachment_ids:
        try:
            _repo.delete_attachments(
                attachment_ids=remove_attachment_ids,
                entry_id=entry_id,
                trust_product_id=trust_product_id,
                asset_code=ac,
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
        qs = _workbench_followup_redirect_qs(
            trust_product_id,
            ac,
            case_id=int(result["case_id"]),
            entry_id=entry_id,
            request=request,
        )
        return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)

    return result


@router.post("/overdue/workbench/followups/entries/{entry_id}/delete")
def delete_followup_entry(
    entry_id: int,
    request: Request,
    current_user: Annotated[dict, Depends(_get_user)],
    trust_product_id: int = Form(...),
    asset_code: str = Form(""),
    custody_asset_code: str = Form(""),
    redirect_to_workbench: str | None = Form(None),
):
    ac = _resolve_asset_code(
        trust_product_id, asset_code, custody_asset_code, None
    )
    try:
        result = _repo.delete_entry(
            entry_id=entry_id,
            trust_product_id=trust_product_id,
            asset_code=ac,
            updated_by=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if redirect_to_workbench:
        qs = _workbench_followup_redirect_qs(
            trust_product_id, ac, case_id=int(result["case_id"]), request=request
        )
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
