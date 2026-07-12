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


def parse_trust_product_ids(
    trust_product_id=None,
    trust_product_ids: list | None = None,
) -> list[int] | None:
    """解析信托产品筛选：None 表示全部；非空 list 表示限定在这些 id。"""
    ids: list[int] = []
    if trust_product_ids:
        for value in trust_product_ids:
            if value in _EMPTY_VALUES:
                continue
            ids.append(int(value))
    if trust_product_id not in _EMPTY_VALUES:
        single = int(trust_product_id)
        if single not in ids:
            ids.append(single)
    if not ids:
        return None
    seen: set[int] = set()
    ordered: list[int] = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


def sql_in_int_column(
    column: str,
    ids: list[int] | None,
    *,
    param_prefix: str = "tpid",
) -> tuple[str, dict]:
    """返回 SQL 片段（含前导 AND）与 bind 参数；ids 为 None 时不加条件。"""
    if ids is None:
        return ("", {})
    if len(ids) == 1:
        key = f"{param_prefix}_0"
        return (f" AND {column} = :{key}", {key: ids[0]})
    params: dict = {}
    placeholders: list[str] = []
    for index, pid in enumerate(ids):
        key = f"{param_prefix}_{index}"
        params[key] = pid
        placeholders.append(f":{key}")
    return (f" AND {column} IN ({', '.join(placeholders)})", params)


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
