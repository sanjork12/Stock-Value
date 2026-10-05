"""Typed helpers for industry datasets (dict-backed for JSON friendliness)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def require_keys(row: Dict[str, Any], keys: List[str], *, ctx: str) -> None:
    missing = [k for k in keys if k not in row or row.get(k) in (None, "")]
    # Allow empty lists for some fields; only flag truly missing keys
    missing = [k for k in keys if k not in row]
    if missing:
        raise ValueError(f"{ctx}: missing keys {missing}")


def segment_pct_sum(segments: List[Dict[str, Any]]) -> float:
    total = 0.0
    for seg in segments or []:
        pct = seg.get("percentage_of_total")
        if pct is None:
            continue
        total += float(pct)
    return total


def has_source(row: Dict[str, Any]) -> bool:
    if row.get("source") or row.get("source_url") or row.get("source_urls"):
        return True
    if row.get("source_name"):
        return True
    return False
