"""Stage 3: CSV conversion engine - maps extracted data to CSV format."""

import csv
import io
from typing import Optional

import pandas as pd


def flatten_tables(page_results: list[dict], columns: list[str]) -> list[dict]:
    """Flatten extracted tables into rows matching the target columns."""
    rows = []

    for page in page_results:
        page_num = page.get("page", 0)
        for elem in page.get("elements", []):
            etype = elem.get("type")

            if etype == "table":
                headers = elem.get("headers", [])
                for table_row in elem.get("rows", []):
                    row_dict = {"page": str(page_num)}
                    for i, header in enumerate(headers):
                        if header in columns:
                            val = table_row[i] if i < len(table_row) else ""
                            row_dict[header] = val
                    # Include cells even if headers don't match target columns
                    if len(row_dict) <= 1:
                        for i, val in enumerate(table_row):
                            col_name = headers[i] if i < len(headers) else f"col_{i}"
                            row_dict[col_name] = val
                    rows.append(row_dict)

            elif etype == "text_block":
                content = elem.get("content", "")
                row_dict = {"page": str(page_num), "content": content}
                rows.append(row_dict)

            elif etype == "checkbox_group":
                for item in elem.get("items", []):
                    row_dict = {
                        "page": str(page_num),
                        "checkbox_label": item.get("label", ""),
                        "checkbox_value": str(item.get("checked", False)),
                    }
                    rows.append(row_dict)

    return rows


def build_dataframe(
    page_results: list[dict],
    columns: list[str],
    include_page_ref: bool = True,
    include_element_type: bool = False,
    table_only: bool = False,
    text_only: bool = False,
) -> pd.DataFrame:
    """Build a pandas DataFrame from extraction results.

    Args:
        page_results: Extracted page data.
        columns: Target column names.
        include_page_ref: Add page reference column.
        include_element_type: Add element type column.
        table_only: Only include table elements.
        text_only: Only include text elements.
    """
    rows = []

    for page in page_results:
        page_num = page.get("page", 0)

        for elem in page.get("elements", []):
            etype = elem.get("type")

            if table_only and etype != "table":
                continue
            if text_only and etype not in ("text_block", "checkbox_group"):
                continue

            if etype == "table":
                headers = elem.get("headers", [])
                for table_row in elem.get("rows", []):
                    row = {}
                    if include_page_ref:
                        row["page"] = page_num
                    if include_element_type:
                        row["element_type"] = "table"
                    row["confidence"] = elem.get("confidence", 0)
                    for i, val in enumerate(table_row):
                        col = headers[i] if i < len(headers) else f"col_{i}"
                        row[col] = val
                    rows.append(row)

            elif etype == "text_block":
                row = {}
                if include_page_ref:
                    row["page"] = page_num
                if include_element_type:
                    row["element_type"] = "text"
                row["content"] = elem.get("content", "")
                rows.append(row)

            elif etype == "checkbox_group":
                for item in elem.get("items", []):
                    row = {}
                    if include_page_ref:
                        row["page"] = page_num
                    if include_element_type:
                        row["element_type"] = "checkbox"
                    row["checkbox_label"] = item.get("label", "")
                    row["checkbox_value"] = item.get("checked", False)
                    rows.append(row)

    df = pd.DataFrame(rows)

    # Reorder columns: put requested columns first
    existing_cols = [c for c in columns if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    ordered_cols = existing_cols + remaining_cols
    df = df.reindex(columns=ordered_cols)

    return df


def dataframe_to_csv(df: pd.DataFrame, encoding: str = "utf-8-sig") -> str:
    """Convert DataFrame to CSV string."""
    return df.to_csv(index=False, encoding=encoding)


def dataframe_to_csv_bytes(df: pd.DataFrame, encoding: str = "utf-8-sig") -> bytes:
    """Convert DataFrame to CSV bytes for download."""
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding=encoding)
    return buf.getvalue()


def convert_excel_to_dataframe(
    file_bytes: bytes,
    sheet_name: Optional[str] = None,
) -> pd.DataFrame:
    """Read an Excel file into a DataFrame."""
    kwargs = {}
    if sheet_name is not None:
        kwargs["sheet_name"] = sheet_name
    return pd.read_excel(io.BytesIO(file_bytes), **kwargs)


def convert_csv_to_dataframe(
    file_bytes: bytes,
    encoding: str = "utf-8",
) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
