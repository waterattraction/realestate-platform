"""Shared UI constants for overdue module (no main.py import)."""

from app.overdue.buckets import DELINQUENCY_BUCKET_COLORS, DELINQUENCY_BUCKET_LABELS

FOLLOWUP_STATUS_LABELS = {
    "open": "待处理",
    "in_progress": "跟进中",
    "resolved": "已解决",
    "closed": "已关闭",
}

TRUST_MARKER_OPTIONS = [
    "未标记",
    "信托已关注",
    "信托要求跟进",
    "信托确认无风险",
    "信托要求说明",
    "已反馈信托",
]

INTERNAL_STATUS_OPTIONS = ["待跟进", "跟进中", "已解决", "已关闭"]

__all__ = [
    "DELINQUENCY_BUCKET_COLORS",
    "DELINQUENCY_BUCKET_LABELS",
    "FOLLOWUP_STATUS_LABELS",
    "INTERNAL_STATUS_OPTIONS",
    "TRUST_MARKER_OPTIONS",
]
