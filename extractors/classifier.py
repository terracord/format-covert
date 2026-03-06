"""Stage 2: Document classification - detect document format patterns."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

PATTERNS_DIR = Path(__file__).parent.parent / "patterns"


def load_patterns() -> list[dict]:
    """Load all pattern definitions from the patterns directory."""
    patterns = []
    if not PATTERNS_DIR.exists():
        return patterns
    for f in sorted(PATTERNS_DIR.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            patterns.append(json.load(fh))
    return patterns


def classify_by_filename(filename: str, patterns: list[dict]) -> Optional[dict]:
    """Try to classify by filename patterns."""
    filename_lower = filename.lower()
    for pattern in patterns:
        keywords = pattern.get("fingerprint", {}).get("filename_keywords", [])
        if any(kw.lower() in filename_lower for kw in keywords):
            return pattern
    return None


def classify_by_content(page_results: list[dict], patterns: list[dict]) -> Optional[dict]:
    """Try to classify by content keywords from extracted pages."""
    all_text = ""
    for page in page_results[:5]:  # Check first 5 pages
        for elem in page.get("elements", []):
            if elem.get("type") == "text_block":
                all_text += " " + elem.get("content", "")
            elif elem.get("type") == "table":
                for h in elem.get("headers", []):
                    all_text += " " + h

    all_text_lower = all_text.lower()

    best_match = None
    best_score = 0

    for pattern in patterns:
        fp = pattern.get("fingerprint", {})
        header_keywords = fp.get("header_keywords", [])
        score = sum(1 for kw in header_keywords if kw.lower() in all_text_lower)
        if score > best_score:
            best_score = score
            best_match = pattern

    if best_score > 0:
        return best_match
    return None


def classify_document(
    filename: str,
    page_results: list[dict],
) -> dict:
    """Classify a document into a known pattern.

    Returns pattern dict if matched, or a generic fallback pattern.
    """
    patterns = load_patterns()

    match = classify_by_filename(filename, patterns)
    if match:
        return {**match, "classification_method": "filename"}

    match = classify_by_content(page_results, patterns)
    if match:
        return {**match, "classification_method": "content"}

    return {
        "pattern_id": "generic",
        "name": "Generic Document",
        "classification_method": "fallback",
        "mapping_template": None,
    }


def get_suggested_columns(page_results: list[dict]) -> list[str]:
    """Suggest CSV columns based on extracted content."""
    columns = []

    has_tables = False
    has_text = False
    has_checkboxes = False
    table_headers = []

    for page in page_results:
        for elem in page.get("elements", []):
            etype = elem.get("type")
            if etype == "table":
                has_tables = True
                table_headers.extend(elem.get("headers", []))
            elif etype == "text_block":
                has_text = True
            elif etype == "checkbox_group":
                has_checkboxes = True

    if has_tables and table_headers:
        seen = set()
        for h in table_headers:
            h = h.strip()
            if h and h not in seen:
                columns.append(h)
                seen.add(h)
    else:
        columns = ["page", "content"]

    if has_checkboxes and "checkbox_value" not in columns:
        columns.append("checkbox_label")
        columns.append("checkbox_value")

    return columns
