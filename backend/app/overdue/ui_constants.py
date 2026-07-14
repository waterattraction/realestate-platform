"""Shared UI constants for overdue module (no main.py import)."""

from app.overdue.buckets import DELINQUENCY_BUCKET_COLORS, DELINQUENCY_BUCKET_LABELS

FOLLOWUP_STATUS_LABELS = {
    "open": "待跟进",
    "in_progress": "跟进中",
    "settled_week": "本周结算",
    "resolved": "已解决",
    "closed": "已关闭",
}

FOLLOWUP_CASE_CATEGORIES = [
    "轻度逾期",
    "重度逾期",
    "回购",
    "置换",
    "潜在风险",
]

TRUST_MARKER_OPTIONS = [
    "无标记",
    "已关注",
    "重点关注",
]

# tone, short_label — 列表/摘要徽章用
TRUST_MARKER_VISUAL = {
    "无标记": ("none", "无"),
    "已关注": ("watch", "已关注"),
    "重点关注": ("focus", "重点关注"),
}

# 派生展示：正常 | 待跟进(N) | 本周结算(M) — 列表筛选用通配由页面逻辑处理
INTERNAL_STATUS_OPTIONS = ["正常", "待跟进", "本周结算"]

TRUST_MARKER_DEFAULT = "无标记"
INTERNAL_STATUS_DEFAULT = "正常"

__all__ = [
    "DELINQUENCY_BUCKET_COLORS",
    "DELINQUENCY_BUCKET_LABELS",
    "FOLLOWUP_CASE_CATEGORIES",
    "FOLLOWUP_STATUS_LABELS",
    "INTERNAL_STATUS_DEFAULT",
    "INTERNAL_STATUS_OPTIONS",
    "TRUST_MARKER_DEFAULT",
    "TRUST_MARKER_OPTIONS",
    "TRUST_MARKER_VISUAL",
]
