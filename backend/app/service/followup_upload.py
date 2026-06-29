"""Save followup attachment files under ASSET_UPLOAD_DIR/followups/."""

import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES_PER_ENTRY = 10

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
FILE_EXTENSIONS = IMAGE_EXTENSIONS | {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv",
}

ALLOWED_EXTENSIONS_ATTR = (
    ".jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt"
)

_DISPLAY_TZ = ZoneInfo("Asia/Shanghai")

_ATTACHMENT_LIMIT_MSG = (
    "附件最多 10 个，请先删除已有附件或减少本次上传数量。"
)


def upload_root() -> Path:
    return Path(os.getenv("ASSET_UPLOAD_DIR", "/data/uploads"))


def entry_dir(case_id: int, entry_id: int) -> Path:
    dest = upload_root() / "followups" / str(case_id) / str(entry_id)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _ext_from_content_type(content_type: str | None) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "application/pdf": ".pdf",
    }
    if content_type:
        return mapping.get(content_type.split(";")[0].strip().lower(), "")
    return ""


def _default_paste_name(content_type: str | None) -> str:
    now = datetime.now(_DISPLAY_TZ)
    ext = _ext_from_content_type(content_type) or ".png"
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return f"screenshot-{stamp}{ext}"


def _resolve_original_name(uf: UploadFile) -> str:
    raw = (uf.filename or "").strip()
    if raw:
        return Path(raw).name
    return _default_paste_name(uf.content_type)


async def save_entry_files(
    case_id: int,
    entry_id: int,
    files: list[UploadFile],
    *,
    existing_attachment_count: int = 0,
) -> list[dict]:
    pending: list[UploadFile] = [f for f in files if f is not None]
    if not pending:
        return []

    if existing_attachment_count + len(pending) > MAX_FILES_PER_ENTRY:
        raise HTTPException(status_code=400, detail=_ATTACHMENT_LIMIT_MSG)

    saved: list[dict] = []
    dest = entry_dir(case_id, entry_id)

    for uf in pending:
        original_name = _resolve_original_name(uf)
        ext = Path(original_name).suffix.lower()
        if not ext:
            ext = _ext_from_content_type(uf.content_type)
            if ext:
                original_name = f"{Path(original_name).stem}{ext}"
        if ext not in FILE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持该文件类型: {original_name}",
            )

        content = await uf.read()
        if not content:
            continue
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"单文件不能超过 10MB: {original_name}",
            )

        stored_name = f"{uuid.uuid4().hex}{ext}"
        path = dest / stored_name
        path.write_bytes(content)
        rel_path = str(path.relative_to(upload_root()))
        attachment_type = "image" if ext in IMAGE_EXTENSIONS else "file"
        saved.append(
            {
                "file_name": original_name,
                "stored_path": rel_path,
                "content_type": uf.content_type,
                "file_size": len(content),
                "attachment_type": attachment_type,
            }
        )

    if existing_attachment_count + len(saved) > MAX_FILES_PER_ENTRY:
        raise HTTPException(status_code=400, detail=_ATTACHMENT_LIMIT_MSG)

    return saved


INLINE_ATTACHMENT_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf",
})

_NEVER_INLINE_EXTENSIONS = frozenset({
    ".html", ".htm", ".js", ".svg", ".xml",
})


def attachment_content_disposition(
    file_name: str,
    content_type: str | None = None,
) -> str:
    """Return 'inline' for images/PDF only; never inline html/js."""
    ext = Path(file_name).suffix.lower()
    if ext in _NEVER_INLINE_EXTENSIONS:
        return "attachment"
    if ext in INLINE_ATTACHMENT_EXTENSIONS:
        return "inline"
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct.startswith("image/") or ct == "application/pdf":
            return "inline"
    return "attachment"
