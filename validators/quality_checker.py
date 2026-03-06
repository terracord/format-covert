"""Stage 4: Validation - quality checks and confidence scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class ValidationResult:
    column: str
    row_index: int
    check_type: str
    severity: str  # "high", "medium", "low"
    message: str
    value: str


def check_missing_values(df: pd.DataFrame, required_columns: list[str]) -> list[ValidationResult]:
    """Check for missing values in required columns."""
    results = []
    for col in required_columns:
        if col not in df.columns:
            continue
        mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        for idx in df.index[mask]:
            results.append(
                ValidationResult(
                    column=col,
                    row_index=int(idx),
                    check_type="missing_value",
                    severity="high",
                    message=f"Required field '{col}' is empty",
                    value="",
                )
            )
    return results


def check_numeric_fields(df: pd.DataFrame, numeric_columns: list[str]) -> list[ValidationResult]:
    """Check that numeric columns contain valid numbers."""
    results = []
    for col in numeric_columns:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if pd.isna(val) or str(val).strip() == "":
                continue
            try:
                float(str(val).replace(",", "").replace("%", ""))
            except ValueError:
                results.append(
                    ValidationResult(
                        column=col,
                        row_index=int(idx),
                        check_type="type_mismatch",
                        severity="high",
                        message=f"Expected numeric value in '{col}', got: {val}",
                        value=str(val),
                    )
                )
    return results


def check_percentage_range(df: pd.DataFrame, pct_columns: list[str]) -> list[ValidationResult]:
    """Check percentage values are in 0-100 range."""
    results = []
    for col in pct_columns:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if pd.isna(val) or str(val).strip() == "":
                continue
            try:
                num = float(str(val).replace(",", "").replace("%", ""))
                if num < 0 or num > 100:
                    results.append(
                        ValidationResult(
                            column=col,
                            row_index=int(idx),
                            check_type="range_violation",
                            severity="medium",
                            message=f"Percentage out of range (0-100): {num}",
                            value=str(val),
                        )
                    )
            except ValueError:
                pass
    return results


def check_duplicate_rows(df: pd.DataFrame) -> list[ValidationResult]:
    """Check for duplicate rows."""
    results = []
    dupes = df.duplicated(keep="first")
    for idx in df.index[dupes]:
        results.append(
            ValidationResult(
                column="*",
                row_index=int(idx),
                check_type="duplicate",
                severity="medium",
                message="Duplicate row detected",
                value="",
            )
        )
    return results


def compute_confidence_score(
    df: pd.DataFrame,
    validation_results: list[ValidationResult],
) -> float:
    """Compute overall confidence score (0.0 - 1.0)."""
    if df.empty:
        return 0.0

    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return 0.0

    severity_weights = {"high": 3, "medium": 2, "low": 1}
    penalty = sum(severity_weights.get(r.severity, 1) for r in validation_results)

    score = max(0.0, 1.0 - (penalty / total_cells))
    return round(score, 3)


def compute_row_confidence(
    row_index: int,
    validation_results: list[ValidationResult],
) -> float:
    """Compute confidence for a single row."""
    row_issues = [r for r in validation_results if r.row_index == row_index]
    if not row_issues:
        return 1.0
    severity_weights = {"high": 0.3, "medium": 0.15, "low": 0.05}
    penalty = sum(severity_weights.get(r.severity, 0.05) for r in row_issues)
    return max(0.0, round(1.0 - penalty, 3))


def run_validation(
    df: pd.DataFrame,
    required_columns: Optional[list[str]] = None,
    numeric_columns: Optional[list[str]] = None,
    percentage_columns: Optional[list[str]] = None,
    check_duplicates: bool = True,
) -> tuple[list[ValidationResult], float]:
    """Run all validation checks and return results with confidence score."""
    all_results = []

    if required_columns:
        all_results.extend(check_missing_values(df, required_columns))
    if numeric_columns:
        all_results.extend(check_numeric_fields(df, numeric_columns))
    if percentage_columns:
        all_results.extend(check_percentage_range(df, percentage_columns))
    if check_duplicates:
        all_results.extend(check_duplicate_rows(df))

    confidence = compute_confidence_score(df, all_results)
    return all_results, confidence


