"""Fetch PDF or other files from URLs."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests


SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


def fetch_file_from_url(url: str, timeout: int = 60) -> tuple[bytes, str, str]:
    """Download a file from a URL.

    Args:
        url: The URL to download from.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (file_bytes, filename, content_type).

    Raises:
        ValueError: If the URL is invalid or file type is unsupported.
        requests.RequestException: On network errors.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    content_length = int(response.headers.get("Content-Length", 0))
    if content_length > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {content_length} bytes (max {MAX_FILE_SIZE})")

    path = Path(parsed.path)
    filename = path.name or "downloaded_file"

    file_bytes = response.content
    return file_bytes, filename, content_type


def detect_file_type(filename: str, content_type: str) -> str:
    """Detect file type from filename and content type."""
    ext = Path(filename).suffix.lower()

    if ext in SUPPORTED_EXTENSIONS:
        return ext

    ct_map = {
        "application/pdf": ".pdf",
        "text/csv": ".csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
    }
    for ct_prefix, file_ext in ct_map.items():
        if ct_prefix in content_type:
            return file_ext

    return ext or ".unknown"
