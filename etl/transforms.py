"""Safe application of transformation-rule logic to pandas Series."""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from core.models import TransformationRule

WHEN_RE = re.compile(
    r"WHEN\s+src\s*=\s*'([^']*)'\s+THEN\s+(NULL|'[^']*'|\d+|true|false)",
    re.IGNORECASE,
)


def apply_rule(series: pd.Series, rule: TransformationRule) -> pd.Series:
    cleaned = series.map(_normalize_null)
    if rule.transform_type == "map" or rule.mapping_dict:
        mapping = rule.mapping_dict or _mapping_from_case(rule.logic)
        result = cleaned.map(lambda v: _lookup(v, mapping))
    elif rule.transform_type == "date" or "TO_DATE" in (rule.logic or "").upper():
        result = cleaned.map(_parse_date)
    elif rule.transform_type == "trim" or "TRIM(" in (rule.logic or "").upper():
        result = cleaned.map(lambda v: str(v).strip() if v is not None else None)
    elif rule.transform_type == "cast" or "CAST(" in (rule.logic or "").upper():
        result = pd.to_numeric(cleaned, errors="coerce")
    elif (rule.logic or "").strip().upper().startswith("CASE"):
        mapping = _mapping_from_case(rule.logic)
        result = cleaned.map(lambda v: _lookup(v, mapping))
    else:
        result = cleaned
    return _none_not_nan(result)


def _none_not_nan(series: pd.Series) -> pd.Series:
    as_obj = series.astype(object)
    return as_obj.where(pd.notna(as_obj), other=None)


def _normalize_null(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def _lookup(value, mapping: dict[str, str]):
    if value is None:
        return None
    key = str(value).strip()
    if key in mapping:
        mapped = mapping[key]
        return _coerce_literal(mapped)
    return None


def _mapping_from_case(logic: str) -> dict[str, str]:
    found = {}
    for match in WHEN_RE.finditer(logic or ""):
        src, dest = match.group(1), match.group(2)
        found[src] = dest
    return found


def _coerce_literal(raw: str):
    if raw is None:
        return None
    text = str(raw)
    if text.upper() == "NULL":
        return None
    if text.upper() == "TRUE":
        return True
    if text.upper() == "FALSE":
        return False
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


def _parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()
