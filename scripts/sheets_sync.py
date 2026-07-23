"""
sheets_sync.py
--------------
Replaces verses.json with a Google Sheet as the single source of truth
for verse data. You add/delete rows straight in the Sheet — no editing
JSON or touching the repo at all.

Expected Sheet columns (row 1 = header, exact names, any order):
    id | telugu | english | reference | used | font_style | music_file

- id          : any unique text/number you like (e.g. 1, 2, 3...)
- telugu      : Telugu verse text
- english     : English verse text
- reference   : e.g. "Psalm 23:1"
- used        : TRUE / FALSE  (leave blank for "not used yet")
- font_style  : OPTIONAL per-verse override, e.g. "modern" / "elegant" / "bold"
- music_file  : OPTIONAL per-verse override, filename from assets/music/

Secrets needed in GitHub Actions:
    GOOGLE_SERVICE_ACCOUNT_JSON  -> the full JSON key file, pasted as-is
    GOOGLE_SHEET_ID              -> the long ID in the Sheet's URL
"""

import os
import json
import sys
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

REQUIRED_COLUMNS = ["id", "telugu", "english", "reference", "used"]


def _client():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        sys.exit("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON secret is not set.")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _sheet():
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        sys.exit("ERROR: GOOGLE_SHEET_ID secret is not set.")
    gc = _client()
    return gc.open_by_key(sheet_id).sheet1


def get_all_rows():
    """Returns list of dicts, one per verse row, in sheet order."""
    ws = _sheet()
    records = ws.get_all_records()
    for col in REQUIRED_COLUMNS:
        if records and col not in records[0]:
            sys.exit(f"ERROR: Sheet is missing required column '{col}'.")
    return records


def get_next_unused_verse():
    """Returns (row_number, verse_dict) for the first row where used is
    not TRUE. row_number is 1-indexed and includes the header row, so
    the first data row is row_number=2."""
    ws = _sheet()
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):
        used_val = str(row.get("used", "")).strip().upper()
        if used_val not in ("TRUE", "YES", "1"):
            return i, row
    sys.exit(
        "ERROR: No unused verses left in the Sheet. Add more rows — "
        "the workflow stops here on purpose instead of repeating one."
    )


def mark_used(row_number: int):
    ws = _sheet()
    header = ws.row_values(1)
    used_col = header.index("used") + 1
    ws.update_cell(row_number, used_col, "TRUE")


def get_row_by_id(verse_id: str):
    """Used by the edit workflow to re-fetch a specific verse by its id
    column, regardless of used status, so you can re-render an already
    posted short."""
    ws = _sheet()
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):
        if str(row.get("id", "")).strip() == str(verse_id).strip():
            return i, row
    sys.exit(f"ERROR: No row found with id='{verse_id}'.")


if __name__ == "__main__":
    row_no, verse = get_next_unused_verse()
    print(f"Next verse (row {row_no}): {verse}")
