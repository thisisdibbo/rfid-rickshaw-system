"""Disable an owner's mobile account by Firebase Auth email."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import auth, credentials, db

DATABASE_URL = (
    "https://rfid-rickshaw-system-default-rtdb."
    "asia-southeast1.firebasedatabase.app"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[2]),
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    cred = root / "credentials" / "firebase-adminsdk.json"
    if not cred.exists():
        raise FileNotFoundError(cred)

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(
            credentials.Certificate(str(cred)),
            {"databaseURL": DATABASE_URL, "httpTimeout": 20},
        )

    user = auth.get_user_by_email(args.email.strip())
    auth.update_user(user.uid, disabled=True)
    db.reference(f"mobile_access/{user.uid}/active").set(False)
    print("Disabled mobile account:", args.email, user.uid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
