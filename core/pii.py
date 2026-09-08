"""PII / sensitive-column heuristics used by the schema profiler (bonus)."""

from __future__ import annotations

import re
from typing import Any

NAME_PATTERNS: list[tuple[str, str]] = [
    (r"ssn|sin|national.?id|tax.?id", "national_id"),
    (r"dob|birth|bdate", "date_of_birth"),
    (r"email", "email"),
    (r"phone|mobile|tel", "phone"),
    (r"(^|_)nm$|(^|_)name$|pat_nm|stf_nm", "person_name"),
    (r"zip|postal", "postal_code"),
    (r"addr|street|city", "address"),
    (r"mrn|medical.?record", "medical_record_number"),
]

VALUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\d{3}-\d{2}-\d{4}$"), "national_id"),
    (re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"), "email"),
    (re.compile(r"^\+?\d[\d\-\s]{7,}$"), "phone"),
]


def detect_pii(column_name: str, sample_values: list[Any]) -> list[str]:
    flags: set[str] = set()
    lowered = column_name.lower()
    for pattern, label in NAME_PATTERNS:
        if re.search(pattern, lowered):
            flags.add(label)
    for value in sample_values[:20]:
        if value is None:
            continue
        text = str(value).strip()
        for regex, label in VALUE_PATTERNS:
            if regex.match(text):
                flags.add(label)
    return sorted(flags)
