from datetime import date, datetime
from decimal import Decimal


def row_to_dict(row) -> dict | None:
    if row is None:
        return None
    out = {}
    for key, value in row._mapping.items():
        out[key] = serialize_value(value)
    return out


def rows_to_dicts(rows) -> list[dict]:
    return [row_to_dict(r) for r in rows]


def serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
