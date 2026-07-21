"""系统时间统一：北京时间（Asia/Shanghai）。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def to_beijing(value: Any) -> datetime | None:
    """将 DB/序列化时间转到北京时间；无时区按 UTC 解释。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text or text == "—":
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def format_beijing_datetime(value: Any, *, with_seconds: bool = True) -> str | None:
    """展示用北京时间字符串。"""
    dt = to_beijing(value)
    if dt is None:
        return None
    if with_seconds:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y-%m-%d %H:%M")


def now_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)
