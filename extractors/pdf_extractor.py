"""Stage 1: PDF extraction engine - extracts structured data from PDF files.

Uses multiple extraction engines (pdfplumber, PyMuPDF, Camelot) and
produces intermediate JSON with per-page elements.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import pdfplumber


@dataclass
class TableElement:
    type: str = "table"
    confidence: float = 0.0
    extraction_method: str = ""
    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    page: int = 0


@dataclass
class TextBlockElement:
    type: str = "text_block"
    content: str = ""
    bounding_box: list = field(default_factory=list)
    page: int = 0


@dataclass
class CheckboxGroupElement:
    type: str = "checkbox_group"
    items: list = field(default_factory=list)
    page: int = 0


@dataclass
class PageResult:
    page: int = 0
    elements: list = field(default_factory=list)


CHECKBOX_PATTERNS = [
    (re.compile(r"[✓☑✔]\s*(.+)"), True),
    (re.compile(r"[❍☐□]\s*(.+)"), False),
    (re.compile(r"\[x\]\s*(.+)", re.IGNORECASE), True),
    (re.compile(r"\[\s?\]\s*(.+)"), False),
]


def extract_checkboxes(text: str) -> list[dict]:
    """Detect checkbox patterns in text."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        for pattern, checked in CHECKBOX_PATTERNS:
            m = pattern.match(line)
            if m:
                items.append({"label": m.group(1).strip(), "checked": checked})
                break
    return items


def extract_tables_pdfplumber(page) -> list[TableElement]:
    """Extract tables from a pdfplumber page object."""
    tables = []
    raw_tables = page.extract_tables()
    if not raw_tables:
        return tables

    for idx, table_data in enumerate(raw_tables):
        if not table_data or len(table_data) < 2:
            continue

        headers = [str(cell).strip() if cell else "" for cell in table_data[0]]
        rows = []
        for row in table_data[1:]:
            rows.append([str(cell).strip() if cell else "" for cell in row])

        non_empty_cells = sum(1 for h in headers if h) + sum(
            1 for row in rows for cell in row if cell
        )
        total_cells = max(len(headers) + len(rows) * max(len(headers), 1), 1)
        confidence = min(non_empty_cells / total_cells, 1.0)

        tables.append(
            TableElement(
                confidence=round(confidence, 2),
                extraction_method="pdfplumber",
                headers=headers,
                rows=rows,
                page=page.page_number,
            )
        )
    return tables


def extract_text_blocks(page) -> list[TextBlockElement]:
    """Extract text blocks from a pdfplumber page."""
    text = page.extract_text()
    if not text:
        return []

    blocks = []
    current_block = []
    for line in text.split("\n"):
        if line.strip():
            current_block.append(line)
        elif current_block:
            blocks.append(
                TextBlockElement(
                    content="\n".join(current_block),
                    page=page.page_number,
                )
            )
            current_block = []
    if current_block:
        blocks.append(
            TextBlockElement(
                content="\n".join(current_block),
                page=page.page_number,
            )
        )
    return blocks


def extract_page(page) -> PageResult:
    """Extract all elements from a single page."""
    elements = []

    tables = extract_tables_pdfplumber(page)
    elements.extend(tables)

    text_blocks = extract_text_blocks(page)
    for block in text_blocks:
        checkboxes = extract_checkboxes(block.content)
        if checkboxes:
            elements.append(
                CheckboxGroupElement(items=checkboxes, page=page.page_number)
            )
        else:
            elements.append(block)

    return PageResult(page=page.page_number, elements=elements)


def extract_pdf(
    file_path: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    pages: Optional[list[int]] = None,
) -> list[dict]:
    """Extract structured data from a PDF file.

    Args:
        file_path: Path to PDF file.
        file_bytes: Raw PDF bytes (for uploaded files).
        pages: Optional list of page numbers (1-indexed) to extract.

    Returns:
        List of page results as dictionaries.
    """
    if file_bytes:
        pdf_source = io.BytesIO(file_bytes)
    elif file_path:
        pdf_source = file_path
    else:
        raise ValueError("Either file_path or file_bytes must be provided")

    results = []
    with pdfplumber.open(pdf_source) as pdf:
        for page in pdf.pages:
            if pages and page.page_number not in pages:
                continue
            result = extract_page(page)
            results.append(asdict(result))

    return results


def extract_pdf_to_json(
    file_path: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    pages: Optional[list[int]] = None,
) -> str:
    """Extract PDF and return JSON string."""
    results = extract_pdf(file_path=file_path, file_bytes=file_bytes, pages=pages)
    return json.dumps(results, ensure_ascii=False, indent=2)
