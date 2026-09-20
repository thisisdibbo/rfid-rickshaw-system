"""Create/link a Firebase Authentication account to one desktop owner record.

Run from the mobile_owner_app folder, for example:

    python admin_tools/create_owner_mobile_account.py --owner-id 1 \
        --email owner@example.com --password "TemporaryPass123!"

The password is sent to Firebase Authentication and is NOT stored in SQLite or
Realtime Database. The owner may later use the mobile app's Forgot Password
button to choose a new password.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import auth, credentials, db

DATABASE_URL = (
    "https://rfid-rickshaw-system-default-rtdb."
    "asia-southeast1.firebasedatabase.app"
)


def project_root_from_script() -> Path:
    # Expected location:
    # D:\RFID_Rickshaw_System\mobile_owner_app\admin_tools\this_file.py
    return Path(__file__).resolve().parents[2]


def init_admin(project_root: Path) -> None:
    credential_file = project_root / "credentials" / "firebase-adminsdk.json"
    if not credential_file.exists():
        raise FileNotFoundError(
            f"Firebase Admin credential not found: {credential_file}"
        )

    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    firebase_admin.initialize_app(
        credentials.Certificate(str(credential_file)),
        {"databaseURL": DATABASE_URL, "httpTimeout": 20},
    )


def load_owner(project_root: Path, owner_id: int) -> dict:
    sys.path.insert(0, str(project_root))
    import database  # type: ignore

    owner = database.get_owner(owner_id)
    if not owner:
        raise RuntimeError(
            f"Active owner database ID {owner_id} was not found in SQLite."
        )
    return dict(owner)


def get_or_create_user(email: str, password: str):
    try:
        user = auth.get_user_by_email(email)
        auth.update_user(
            user.uid,
            email=email,
            password=password,
            disabled=False,
        )
        print(f"Existing Firebase Auth user updated: {user.uid}")
        return auth.get_user(user.uid)
    except auth.UserNotFoundError:
        user = auth.create_user(
            email=email,
            password=password,
            disabled=False,
            email_verified=False,
        )
        print(f"Firebase Auth user created: {user.uid}")
        return user


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-id", type=int, required=True, help="SQLite owner DB ID")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--project-root",
        default=str(project_root_from_script()),
        help="Desktop project root. Defaults to two folders above this script.",
    )
    args = parser.parse_args()

    if len(args.password) < 6:
        parser.error("Password must contain at least 6 characters.")

    project_root = Path(args.project_root).resolve()
    init_admin(project_root)
    owner = load_owner(project_root, args.owner_id)

    user = get_or_create_user(args.email.strip(), args.password)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    db.reference(f"mobile_access/{user.uid}").set(
        {
            "uid": user.uid,
            "owner_id": int(owner["id"]),
            "owner_id_key": str(owner["id"]),
            "owner_name": owner.get("name") or "",
            "owner_code": owner.get("owner_id") or "",
            "email": args.email.strip().lower(),
            "active": True,
            "updated_at": now,
        }
    )

    print()
    print("Mobile account linked successfully")
    print("----------------------------------")
    print("Owner DB ID :", owner["id"])
    print("Owner name  :", owner.get("name") or "")
    print("Email       :", args.email.strip().lower())
    print("Firebase UID:", user.uid)
    print()
    print("The password was NOT saved in Realtime Database or SQLite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
