"""Save followup attachment files under INGESTION_UPLOAD_DIR/followups/."""

import os
from pathlib import Path

from fastapi import HTTPException, UploadFile

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES_PER_ENTRY = 10

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
FILE_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}


def upload_root() -> Path:
    return Path(os.getenv("INGESTION_UPLOAD_DIR", "/data/uploads"))


def entry_dir(case_id: int, entry_id: int) -> Path:
    dest = upload_root() / "followups" / str(case_id) / str(entry_id)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


async def save_entry_files(
    case_id: int,
    entry_id: int,
    files: list[UploadFile],
) -> list[dict]:
    if len(files) > MAX_FILES_PER_ENTRY:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_FILES_PER_ENTRY} files per entry",
        )

    saved: list[dict] = []
    dest = entry_dir(case_id, entry_id)

    for uf in files:
        if not uf.filename:
            continue
        safe_name = Path(uf.filename).name
        ext = Path(safe_name).suffix.lower()
        if ext not in FILE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {safe_name}")

        content = await uf.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File too large: {safe_name}")

        path = dest / safe_name
        path.write_bytes(content)
        rel_path = str(path.relative_to(upload_root()))
        attachment_type = "image" if ext in IMAGE_EXTENSIONS else "file"
        saved.append(
            {
                "file_name": safe_name,
                "stored_path": rel_path,
                "content_type": uf.content_type,
                "file_size": len(content),
                "attachment_type": attachment_type,
            }
        )

    return saved
