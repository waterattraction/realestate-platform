"""统一 GET Query / HTML 表单空值解析。"""

from __future__ import annotations

_EMPTY_VALUES = frozenset({None, "", "null", "None"})


def parse_optional_int(value) -> int | None:
    if value in _EMPTY_VALUES:
        return None
    return int(value)


def parse_optional_date(value) -> str | None:
    if value in _EMPTY_VALUES:
        return None
    return str(value).strip() or None


def parse_optional_bool(value) -> bool | None:
    if value in _EMPTY_VALUES:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return None


def clean_optional_str(value) -> str | None:
    if value in _EMPTY_VALUES:
        return None
    text = str(value).strip()
    return text or None


def parse_pagination(
    page,
    page_size,
    *,
    default_page: int = 1,
    default_size: int = 50,
) -> tuple[int, int]:
    parsed_page = parse_optional_int(page)
    parsed_size = parse_optional_int(page_size)
    return (
        parsed_page if parsed_page is not None else default_page,
        parsed_size if parsed_size is not None else default_size,
    )
