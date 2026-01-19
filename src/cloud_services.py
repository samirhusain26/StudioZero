"""
Google Sheets and Google Drive integration for StudioZero pipeline.
Uses service account authentication via drive_credentials.json.
"""

from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config

# Scopes required for Sheets and Drive access
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_credentials_path() -> Path:
    """Get the path to service account credentials from environment."""
    creds_path_str = Config.DRIVE_APPLICATION_CREDENTIALS
    if not creds_path_str:
        raise ValueError(
            "DRIVE_APPLICATION_CREDENTIALS not set in environment. "
            "Set it to the path of your Google service account JSON file."
        )
    # Handle both absolute and relative paths
    creds_path = Path(creds_path_str)
    if not creds_path.is_absolute():
        creds_path = Config.PROJECT_ROOT / creds_path
    return creds_path


def _get_credentials() -> Credentials:
    """Load service account credentials."""
    creds_path = _get_credentials_path()
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Service account credentials not found at {creds_path}. "
            "Download from Google Cloud Console and set DRIVE_APPLICATION_CREDENTIALS in .env."
        )
    return Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)


def _get_gspread_client() -> gspread.Client:
    """Get authenticated gspread client."""
    creds = _get_credentials()
    return gspread.authorize(creds)


def _get_drive_service():
    """Get authenticated Google Drive service."""
    creds = _get_credentials()
    return build("drive", "v3", credentials=creds)


def get_pending_jobs(sheet_url: str) -> list[dict]:
    """
    Fetch all rows from a Google Sheet where Status is 'Pending'.

    Args:
        sheet_url: Full URL to the Google Sheet.

    Returns:
        List of dicts, each representing a row with column headers as keys.
    """
    client = _get_gspread_client()
    sheet = client.open_by_url(sheet_url).sheet1

    records = sheet.get_all_records()
    pending = [row for row in records if row.get("Status", "").strip().lower() == "pending"]

    # Add row index (1-based, +2 for header row offset)
    for i, row in enumerate(pending):
        row["_row_index"] = records.index(row) + 2

    return pending


def upload_to_drive(file_path: str | Path, parent_folder_id: str) -> str:
    """
    Upload a file to Google Drive and make it publicly viewable.

    Args:
        file_path: Path to the local file.
        parent_folder_id: Google Drive folder ID to upload into.

    Returns:
        Public webViewLink URL for the uploaded file.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    service = _get_drive_service()

    # Upload file (supportsAllDrives enables Shared Drive support)
    file_metadata = {
        "name": file_path.name,
        "parents": [parent_folder_id],
    }
    media = MediaFileUpload(str(file_path), resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()

    # Make publicly viewable
    service.permissions().create(
        fileId=uploaded["id"],
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()

    return uploaded["webViewLink"]


def update_row(sheet_url: str, row_index: int, data_dict: dict) -> None:
    """
    Update specific columns in a row by matching column headers.

    Args:
        sheet_url: Full URL to the Google Sheet.
        row_index: 1-based row number to update.
        data_dict: Dict mapping column headers to new values.
                   e.g., {"Status": "Complete", "video_link": "https://..."}
    """
    client = _get_gspread_client()
    sheet = client.open_by_url(sheet_url).sheet1

    # Get headers from first row
    headers = sheet.row_values(1)

    # Build list of cell updates
    cells_to_update = []
    for col_name, value in data_dict.items():
        if col_name not in headers:
            continue
        col_index = headers.index(col_name) + 1  # 1-based
        cells_to_update.append(gspread.Cell(row_index, col_index, value))

    if cells_to_update:
        sheet.update_cells(cells_to_update)
