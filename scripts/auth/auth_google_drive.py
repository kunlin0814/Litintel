#!/usr/bin/env python
"""
Authenticate and verify LitIntel Google Drive access.

This script is intentionally separate from the main pipeline. It creates or
refreshes token_drive.json when needed, then verifies configured Drive IDs.
By default it only reads metadata. Use --write-smoke to append a small test
line to a Drive file.
"""

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from litintel.storage.drive import append_text_to_file, get_drive_service  # noqa: E402


DRIVE_ID_ENV_KEYS = [
    "GOOGLE_DRIVE_FOLDER_ID",
    "GOOGLE_DRIVE_PAPERS_JSONL_FILE_ID",
    "GOOGLE_DRIVE_NOTEBOOKLM_FOLDER_ID",
    "GOOGLE_DRIVE_COMP_METHODS_FOLDER_ID",
    "GOOGLE_DRIVE_PDF_FOLDER_ID",
    "GOOGLE_DRIVE_FOLDER_ID_PLASTICITY",
    "GOOGLE_DRIVE_PAPERS_JSONL_FILE_ID_PLASTICITY",
    "GOOGLE_DRIVE_NOTEBOOKLM_FOLDER_ID_PLASTICITY",
    "GOOGLE_DRIVE_COMP_METHODS_FOLDER_ID_PLASTICITY",
    "GOOGLE_DRIVE_PDF_FOLDER_ID_PLASTICITY",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Authenticate Google Drive OAuth and verify LitIntel Drive IDs.",
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="Path to .env file. Defaults to repo-root .env.",
    )
    parser.add_argument(
        "--write-smoke",
        action="store_true",
        help="Append one small smoke-test line to LitIntel_Drive_Auth_Smoke.md.",
    )
    return parser.parse_args()


def load_environment(env_file: str) -> None:
    """Load the requested env file."""
    env_path = Path(env_file).expanduser()
    if not env_path.exists():
        raise FileNotFoundError(f"Env file not found: {env_path}")
    load_dotenv(env_path)


def configured_ids() -> List[Tuple[str, str]]:
    """Return configured Drive ID env vars."""
    return [(key, os.environ[key]) for key in DRIVE_ID_ENV_KEYS if os.environ.get(key)]


def verify_drive_ids(service, ids: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    """Fetch metadata for configured Drive IDs."""
    results = []
    for key, file_id in ids:
        try:
            meta = service.files().get(
                fileId=file_id,
                fields="id,name,mimeType,parents,trashed",
                supportsAllDrives=True,
            ).execute()
            results.append(
                {
                    "key": key,
                    "id": file_id,
                    "name": meta.get("name", ""),
                    "mime_type": meta.get("mimeType", ""),
                    "trashed": str(meta.get("trashed", False)),
                    "status": "OK",
                }
            )
        except Exception as e:
            results.append(
                {
                    "key": key,
                    "id": file_id,
                    "name": "",
                    "mime_type": "",
                    "trashed": "",
                    "status": f"ERROR: {e}",
                }
            )
    return results


def print_results(results: List[Dict[str, str]]) -> None:
    """Print a compact verification table."""
    for row in results:
        if row["status"] == "OK":
            print(
                "OK",
                row["key"],
                row["name"],
                row["mime_type"],
                f"trashed={row['trashed']}",
            )
        else:
            print("ERROR", row["key"], row["id"], row["status"])


def run_write_smoke(service) -> None:
    """Append a small line to the configured root Drive folder."""
    root_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not root_folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID is required for --write-smoke")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_id = append_text_to_file(
        service=service,
        folder_id=root_folder_id,
        file_name="LitIntel_Drive_Auth_Smoke.md",
        new_text=f"Google Drive auth smoke OK at {timestamp}\n",
    )
    print(f"WRITE_SMOKE_OK {file_id}")


def main() -> None:
    """Run Drive auth and verification."""
    args = parse_args()
    load_environment(args.env_file)

    print("Authenticating Google Drive...")
    service = get_drive_service(os.environ.get("GOOGLE_CREDENTIALS_PATH"))
    print("AUTH_OK token_drive.json ready")

    ids = configured_ids()
    if not ids:
        print("No GOOGLE_DRIVE_* IDs configured to verify.")
    else:
        print("Verifying configured Drive IDs...")
        results = verify_drive_ids(service, ids)
        print_results(results)

        errors = [row for row in results if row["status"] != "OK"]
        if errors:
            raise SystemExit(1)

    if args.write_smoke:
        run_write_smoke(service)


if __name__ == "__main__":
    main()
