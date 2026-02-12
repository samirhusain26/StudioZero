"""
Google Sheets and Google Drive integration for StudioZero pipeline.
Supports OAuth user credentials (preferred for Drive uploads) and
service account fallback. Handles Base64-encoded secrets for cloud deployment.
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config

# Scopes required for Sheets and Drive access
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _decode_secret(secret_value):
    """
    Helper: Decodes a secret whether it's raw JSON or Base64 encoded.
    """
    if not secret_value:
        return None

    # Try decoding Base64 first
    try:
        decoded = base64.b64decode(secret_value).decode('utf-8')
        # Check if it looks like JSON
        if decoded.startswith('{'):
            return json.loads(decoded)
    except Exception:
        pass  # It wasn't base64, so treat it as raw string

    # Try parsing as raw JSON
    try:
        return json.loads(secret_value)
    except Exception:
        return None


def _get_credentials(scopes):
    """
    Retrieves credentials, handling Base64 encoding for Cloud deployment safety.
    """
    # 1. [CLOUD] Try User Token (OAuth) - Preferred for Drive Uploads
    token_secret = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_secret:
        user_info = _decode_secret(token_secret)
        if user_info:
            print("Using User Credentials (OAuth)")
            return Credentials.from_authorized_user_info(user_info, scopes)
        else:
            print("GOOGLE_TOKEN_JSON found but failed to decode.")

    # 2. [LOCAL] Try local token.json file
    local_token_path = "assets/creds/token.json"
    if os.path.exists(local_token_path):
        print("Using local User Credentials (token.json)")
        return Credentials.from_authorized_user_file(local_token_path, scopes)

    # 3. [FALLBACK] Service Account (Will fail for Drive Uploads)
    print("Warning: Falling back to Service Account")
    sa_secret = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if sa_secret:
        sa_info = _decode_secret(sa_secret)
        if sa_info:
            return ServiceAccountCredentials.from_service_account_info(sa_info, scopes=scopes)

    raise RuntimeError("No valid Google credentials found! Please check GitHub Secrets.")


_cached_gspread_client = None
_cached_drive_service = None


def _get_gspread_client() -> gspread.Client:
    """Get authenticated gspread client (cached)."""
    global _cached_gspread_client
    if _cached_gspread_client is None:
        creds = _get_credentials(SCOPES)
        _cached_gspread_client = gspread.authorize(creds)
    return _cached_gspread_client


def _get_drive_service():
    """Get authenticated Google Drive service (cached)."""
    global _cached_drive_service
    if _cached_drive_service is None:
        creds = _get_credentials(SCOPES)
        _cached_drive_service = build("drive", "v3", credentials=creds)
    return _cached_drive_service


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

    # Build pending list with correct row indices using enumerate
    # (records.index(row) would return wrong index for duplicate rows)
    pending = []
    for i, row in enumerate(records):
        if row.get("Status", "").strip().lower() == "pending":
            row["_row_index"] = i + 2  # +2 for 1-based index + header row
            pending.append(row)

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
