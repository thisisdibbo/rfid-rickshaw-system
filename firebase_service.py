import os
import sys
import base64
import io
import uuid
import copy
import threading
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, db, auth
from PIL import Image, ImageOps


if getattr(sys, "frozen", False):
    BASE_DIR = getattr(
        sys,
        "_MEIPASS",
        os.path.dirname(sys.executable)
    )
else:
    BASE_DIR = os.path.dirname(
        os.path.abspath(__file__)
    )
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials", "firebase-adminsdk.json")
DATABASE_URL = "https://rfid-rickshaw-system-default-rtdb.asia-southeast1.firebasedatabase.app"

# Firebase Admin defaults to a 120 second HTTP timeout. Session network
# operations now run outside the Qt GUI thread, so use a moderate timeout:
# long enough for slower mobile/broadband links, but short enough for retries.
FIREBASE_HTTP_TIMEOUT = 20

_firebase_initialized = False


class SessionConflictError(RuntimeError):
    """Raised when a rickshaw already has a different active session."""

    def __init__(self, message, current_session=None):
        super().__init__(message)
        self.current_session = (
            copy.deepcopy(current_session)
            if isinstance(current_session, dict)
            else None
        )


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def safe_value(value, default=""):
    return default if value is None else value


def normalize_uid(uid):
    return str(uid or "").strip().upper()


def _same_id(left, right):
    if left in (None, "") or right in (None, ""):
        return False
    return str(left).strip() == str(right).strip()


def _same_started_at(left, right):
    """Compare session start times while tolerating harmless formatting."""
    if not left or not right:
        return True

    left_text = str(left).strip()
    right_text = str(right).strip()
    if left_text == right_text:
        return True

    try:
        left_dt = datetime.fromisoformat(left_text.replace("Z", "+00:00"))
        right_dt = datetime.fromisoformat(right_text.replace("Z", "+00:00"))

        # Treat naive timestamps as local values. Both desktop-created values
        # normally use the same local ISO representation, so this branch is
        # mainly for mobile values that include an offset.
        if left_dt.tzinfo is None and right_dt.tzinfo is None:
            return abs((left_dt - right_dt).total_seconds()) <= 3

        if left_dt.tzinfo is None or right_dt.tzinfo is None:
            return False

        return abs((left_dt - right_dt).total_seconds()) <= 3
    except Exception:
        return False


def _matches_expected_session(
    current,
    expected_owner_id=None,
    expected_puller_id=None,
    expected_started_at=None,
):
    if not isinstance(current, dict):
        return False

    if expected_owner_id not in (None, ""):
        if not _same_id(current.get("owner_id"), expected_owner_id):
            return False

    if expected_puller_id not in (None, ""):
        if not _same_id(current.get("puller_id"), expected_puller_id):
            return False

    if expected_started_at:
        if not _same_started_at(current.get("started_at"), expected_started_at):
            return False

    return True


def firebase_key(value):
    """Create a Firebase-safe key for values such as RFID UIDs."""
    raw = str(value or "").encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") or "EMPTY"


def initialize_firebase():
    global _firebase_initialized

    if _firebase_initialized:
        return True

    try:
        # Reuse an application initialized elsewhere in the process.
        firebase_admin.get_app()
        _firebase_initialized = True
        return True
    except ValueError:
        pass

    if not os.path.exists(CREDENTIALS_FILE):
        print("[FIREBASE] Credentials not found:", CREDENTIALS_FILE)
        return False

    try:
        cred = credentials.Certificate(CREDENTIALS_FILE)
        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": DATABASE_URL,
                "httpTimeout": FIREBASE_HTTP_TIMEOUT,
            }
        )
        _firebase_initialized = True
        print("[FIREBASE] Realtime Database initialized.")
        return True
    except Exception as exc:
        print("[FIREBASE INIT ERROR]", repr(exc))
        return False


def photo_to_base64(local_file_path):
    """
    Convert a puller photo to a small browser-ready JPEG data URL.

    Realtime Database should not carry multi-megabyte phone photos. Large
    Base64 values slow desktop sync, mobile reads and the public QR page.
    Images are therefore auto-oriented, resized to a maximum of 640x640 and
    compressed as JPEG before upload.
    """
    if not local_file_path:
        return ""

    try:
        # Existing Base64 values from older rows are normalized too, so one
        # old large photo cannot continue slowing every sync.
        if isinstance(local_file_path, str) and local_file_path.startswith("data:image/"):
            marker = ";base64,"
            if marker not in local_file_path:
                return ""
            raw = base64.b64decode(local_file_path.split(marker, 1)[1])
            source = io.BytesIO(raw)
        else:
            if not os.path.exists(local_file_path):
                return ""
            source = local_file_path

        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)

            # JPEG has no alpha channel. Put transparent images on white.
            if image.mode in ("RGBA", "LA"):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")

            image.thumbnail((640, 640), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=76,
                optimize=True
            )
            image_bytes = output.getvalue()

        if not image_bytes:
            return ""

        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return "data:image/jpeg;base64," + encoded

    except Exception as exc:
        print("[PHOTO BASE64 ERROR]", repr(exc))
        return ""


def get_puller_photo_base64(photo_path):
    return photo_to_base64(photo_path)


def upload_puller_photo(local_file_path, slave_uid):
    # Kept for compatibility with the current desktop app.
    if not initialize_firebase() or not slave_uid:
        return ""
    return photo_to_base64(local_file_path)


def delete_puller_photo(photo_url=""):
    # Photos are stored as Base64 data in RTDB, not Firebase Storage.
    return True


def _replace_node(path, value):
    """Replace a Firebase node; delete it when the new collection is empty."""
    ref = db.reference(path)
    if value:
        ref.set(value)
    else:
        ref.delete()


def _owner_payload(owner):
    return {
        "db_id": int(owner["id"]),
        "name": safe_value(owner.get("name")),
        "owner_code": safe_value(owner.get("owner_id")),
        "phone": safe_value(owner.get("phone")),
        "garage_name": safe_value(owner.get("garage_name")),
        "garage_location": safe_value(owner.get("garage_location")),
        "master_uid": normalize_uid(owner.get("master_uid")),
        "active": bool(owner.get("active", 1)),
        "updated_at": now_iso(),
    }


def _puller_payload(puller):
    existing_photo = puller.get("photo_url") or ""
    if isinstance(existing_photo, str) and existing_photo.startswith("data:image/"):
        photo_data = existing_photo
    else:
        photo_data = photo_to_base64(puller.get("photo_path") or "")

    return {
        "db_id": int(puller["id"]),
        "name": safe_value(puller.get("name")),
        "puller_code": safe_value(puller.get("puller_id")),
        "phone": safe_value(puller.get("phone")),
        "slave_uid": normalize_uid(puller.get("slave_uid")),
        "photo": photo_data,
        "active": bool(puller.get("active", 1)),
        "updated_at": now_iso(),
    }


def _rickshaw_payload(rickshaw):
    owner_id = rickshaw.get("owner_id")
    try:
        owner_id = int(owner_id) if owner_id not in (None, "") else None
    except (TypeError, ValueError):
        owner_id = None

    return {
        "db_id": int(rickshaw["id"]),
        "rickshaw_number": safe_value(rickshaw.get("rickshaw_number")),
        "registration_number": safe_value(rickshaw.get("registration_number")),
        "garage_name": safe_value(rickshaw.get("garage_name")),
        "garage_location": safe_value(rickshaw.get("garage_location")),
        "owner_id": owner_id,
        "owner_name": safe_value(rickshaw.get("owner_name")),
        "owner_code": safe_value(rickshaw.get("owner_code")),
        "owner_phone": safe_value(rickshaw.get("owner_phone")),
        "qr_token": safe_value(rickshaw.get("qr_token")),
        "active": bool(rickshaw.get("active", 1)),
        "updated_at": now_iso(),
    }


def sync_master_data(owners, pullers, rickshaws):
    """
    Desktop-only master-data synchronization.

    Performance note:
    The previous implementation performed multiple full Firebase writes plus
    two full reads of /live/rickshaws and /public/by_token. On a slow link,
    that could compete with the operator's Start/End session requests.

    This version builds one multi-location update and does not read the live
    tree first. Base rickshaw/public fields are updated individually so active
    session fields such as status, puller and started_at are preserved.
    """
    if not initialize_firebase():
        return False

    try:
        owner_lookup = {
    int(owner["id"]): owner
    for owner in owners
    if owner.get("id") is not None
}
        owner_node = {}
        mobile_owner_node = {}
        mobile_access_node = {}
        master_index = {}
        for owner in owners:
            payload = _owner_payload(owner)
            owner_key = str(owner["id"])
            owner_node[owner_key] = payload
            mobile_owner_node[owner_key] = {
                "db_id": payload["db_id"],
                "name": payload["name"],
                "owner_code": payload["owner_code"],
                "phone": payload["phone"],
                "garage_name": payload["garage_name"],
                "garage_location": payload["garage_location"],
                "mobile_email": str(owner.get("mobile_email") or "").strip().lower(),
                "mobile_login_enabled": bool(owner.get("mobile_login_enabled", 0)),
                "active": payload["active"],
                "updated_at": payload["updated_at"],
            }

            # Keep existing Firebase mobile permission mapping synchronized
            # when owner profile data changes.
            firebase_uid = str(owner.get("firebase_uid") or "").strip()
            if firebase_uid:
                mobile_access_node[firebase_uid] = {
                    "uid": firebase_uid,
                    "owner_id": payload["db_id"],
                    "owner_id_key": str(payload["db_id"]),
                    "owner_name": payload["name"],
                    "owner_code": payload["owner_code"],
                    "email": str(owner.get("mobile_email") or "").strip().lower(),
                    "active": bool(owner.get("mobile_login_enabled", 0)),
                    "updated_at": payload["updated_at"],
                }
            uid = normalize_uid(owner.get("master_uid"))
            if uid:
                master_index[firebase_key(uid)] = {
                    "uid": uid,
                    "owner_id": int(owner["id"]),
                }

        puller_node = {}
        mobile_puller_node = {}
        slave_index = {}
        for puller in pullers:
            payload = _puller_payload(puller)
            puller_key = str(puller["id"])
            puller_node[puller_key] = payload
            mobile_puller_node[puller_key] = {
                "db_id": payload["db_id"],
                "name": payload["name"],
                "puller_code": payload["puller_code"],
                "phone": payload["phone"],
                "photo": payload["photo"],
                "active": payload["active"],
                "updated_at": payload["updated_at"],
            }
            uid = normalize_uid(puller.get("slave_uid"))
            if uid:
                slave_index[firebase_key(uid)] = {
                    "uid": uid,
                    "puller_id": int(puller["id"]),
                }

        rickshaw_node = {}
        owner_rickshaw_access = {}
        owner_token_access = {}

        for rickshaw in rickshaws:
            payload = _rickshaw_payload(rickshaw)
            owner_id = payload.get("owner_id")

            owner_record = owner_lookup.get(owner_id)

            if owner_record:

              # Use owner's garage name if Rickshaw garage is empty
              if not str(
                payload.get("garage_name") or ""
                ).strip():

                payload["garage_name"] = safe_value(
                owner_record.get("garage_name")
                )

              # Use owner's garage location if Rickshaw location is empty
              if not str(
               payload.get("garage_location") or ""
                ).strip():

               payload["garage_location"] = safe_value(
                owner_record.get("garage_location")
                )
            else:
               # Rickshaw without owner
               payload["owner_name"] = ""
               payload["owner_code"] = ""
               payload["owner_phone"] = ""
               

            rid = str(rickshaw["id"])
            rickshaw_node[rid] = payload

            # Mobile authorization projections.
            # These nodes contain only booleans and are never readable by the
            # mobile client. Realtime Database Security Rules use them to
            # authorize an owner to operate only rickshaws currently assigned
            # to that owner and to update only those public QR tokens.
            owner_id = payload.get("owner_id")
            if owner_id not in (None, ""):
                owner_key = str(owner_id)
                owner_rickshaw_access.setdefault(owner_key, {})[rid] = True

                token = payload.get("qr_token") or ""
                if token:
                    owner_token_access.setdefault(owner_key, {})[str(token)] = True

        # One request for the complete master/index/access snapshot.
        updates = {
            "master/owners": owner_node or None,
            "master/pullers": puller_node or None,
            "master/rickshaws": rickshaw_node or None,
            "mobile/owners": mobile_owner_node or None,
            "mobile/pullers": mobile_puller_node or None,
            "indexes/master_cards": master_index or None,
            "indexes/slave_cards": slave_index or None,
            "access/owner_rickshaws": owner_rickshaw_access or None,
            "access/owner_tokens": owner_token_access or None,
        }

        # Refresh public/live identity fields without touching live session
        # status. New records can omit status because the webpage treats a
        # missing status as IDLE until a session is created.
        public_fields = (
            "rickshaw_id",
            "rickshaw_number",
            "registration_number",
            "garage_name",
            "garage_location",
            "owner_name",
        )

        for rickshaw in rickshaws:
            rid = str(rickshaw["id"])
            master = rickshaw_node[rid]

            live_base = {
                **master,
            }

            for key, value in live_base.items():
                updates[f"live/rickshaws/{rid}/{key}"] = value

            token = master.get("qr_token")
            if token:
                public_base = {
                    "rickshaw_id": master["db_id"],
                    "rickshaw_number": master.get("rickshaw_number", ""),
                    "registration_number": master.get("registration_number", ""),
                    "garage_name": master.get("garage_name", ""),
                    "garage_location": master.get("garage_location", ""),
                    "owner_name": master.get("owner_name", ""),
                    "updated_at": now_iso(),
                }
                for key, value in public_base.items():
                    updates[f"public/by_token/{token}/{key}"] = value

        db.reference().update(updates)

        print(
            "[FIREBASE] Fast master sync:",
            len(owner_node), "owners,",
            len(puller_node), "pullers,",
            len(rickshaw_node), "rickshaws"
        )
        return True
    except Exception as exc:
        print("[FIREBASE MASTER SYNC ERROR]", repr(exc))
        return False


def generate_session_id():
    return "sess_" + uuid.uuid4().hex


def _session_payload(
    rickshaw,
    owner,
    puller,
    master_uid,
    slave_uid,
    cloud_id,
    source="DESKTOP",
    local_session_id=None,
    started_at=None,
):
    started_at = started_at or now_iso()
    # Keep the atomic active-session claim intentionally small. Puller photos
    # are synchronized only after the critical ACTIVE state has been written.
    # This prevents a large Base64 photo from delaying or breaking session start.
    return {
        "cloud_session_id": cloud_id,
        "local_session_id": local_session_id,
        "rickshaw_id": int(rickshaw["id"]),
        "rickshaw_number": safe_value(rickshaw.get("rickshaw_number")),
        "registration_number": safe_value(rickshaw.get("registration_number")),
        "qr_token": safe_value(rickshaw.get("qr_token")),
        "owner_id": int(owner["id"]),
        "owner_name": safe_value(owner.get("name")),
        "owner_code": safe_value(owner.get("owner_id")),
        "puller_id": int(puller["id"]),
        "puller_name": safe_value(puller.get("name")),
        "puller_code": safe_value(puller.get("puller_id")),
        "puller_phone": safe_value(puller.get("phone")),
        "puller_photo": "",
        "master_uid": normalize_uid(master_uid),
        "slave_uid": normalize_uid(slave_uid),
        "started_at": started_at,
        "ended_at": None,
        "status": "ACTIVE",
        "source": str(source or "DESKTOP").upper(),
        "updated_at": now_iso(),
    }


def _active_live_payload(rickshaw, owner, puller, session):
    return {
        **_rickshaw_payload(rickshaw),
        "status": "ACTIVE",
        "cloud_session_id": session["cloud_session_id"],
        "puller_id": int(puller["id"]),
        "puller_name": safe_value(puller.get("name")),
        "puller_code": safe_value(puller.get("puller_id")),
        "puller_phone": safe_value(puller.get("phone")),
        "puller_photo": session.get("puller_photo", ""),
        "started_at": session.get("started_at"),
        "ended_at": None,
        "updated_at": now_iso(),
    }


def _idle_live_payload(rickshaw, ended_at=None):
    return {
        **_rickshaw_payload(rickshaw),
        "status": "IDLE",
        "cloud_session_id": None,
        "puller_id": None,
        "puller_name": "",
        "puller_code": "",
        "puller_phone": "",
        "puller_photo": "",
        "started_at": None,
        "ended_at": ended_at,
        "updated_at": now_iso(),
    }


def _public_from_live(rickshaw, live):
    return {
        "rickshaw_id": int(rickshaw["id"]),
        "rickshaw_number": safe_value(rickshaw.get("rickshaw_number")),
        "registration_number": safe_value(rickshaw.get("registration_number")),
        "garage_name": safe_value(
            rickshaw.get("garage_name") or rickshaw.get("owner_garage_name")
        ),
        "garage_location": safe_value(
            rickshaw.get("garage_location") or rickshaw.get("owner_garage_location")
        ),
        "owner_name": safe_value(rickshaw.get("owner_name")),
        "status": live.get("status", "IDLE"),
        "cloud_session_id": live.get("cloud_session_id"),
        "puller_id": live.get("puller_id"),
        "puller_name": live.get("puller_name", ""),
        "puller_code": live.get("puller_code", ""),
        "puller_phone": live.get("puller_phone", ""),
        "puller_photo": live.get("puller_photo", ""),
        "started_at": live.get("started_at"),
        "ended_at": live.get("ended_at"),
        "updated_at": now_iso(),
    }


def repair_active_projection(rickshaw, session):
    """Repair /live/rickshaws and /public/by_token from an active session.

    This is used when /live/active_sessions is correct but a previous network
    timeout prevented the public website projection from being updated.
    """
    if not initialize_firebase() or not isinstance(session, dict):
        return False

    try:
        rid = str(rickshaw["id"])
        live = {
            **_rickshaw_payload(rickshaw),
            "status": "ACTIVE",
            "cloud_session_id": (
                session.get("cloud_session_id")
                or session.get("cloud_id")
            ),
            "puller_id": session.get("puller_id"),
            "puller_name": safe_value(session.get("puller_name")),
            "puller_code": safe_value(session.get("puller_code")),
            "puller_phone": safe_value(session.get("puller_phone")),
            "puller_photo": "",
            "started_at": session.get("started_at"),
            "ended_at": None,
            "updated_at": now_iso(),
        }

        updates = {f"live/rickshaws/{rid}": live}
        token = rickshaw.get("qr_token") or session.get("qr_token")
        if token:
            updates[f"public/by_token/{token}"] = _public_from_live(
                rickshaw,
                live
            )
        db.reference().update(updates)

        # Restore an existing session photo only after critical ACTIVE state.
        existing_photo = session.get("puller_photo") or ""
        if existing_photo:
            try:
                photo_updates = {
                    f"live/rickshaws/{rid}/puller_photo": existing_photo
                }
                if token:
                    photo_updates[f"public/by_token/{token}/puller_photo"] = existing_photo
                db.reference().update(photo_updates)
            except Exception as photo_exc:
                print("[FIREBASE PROJECTION PHOTO WARNING]", repr(photo_exc))

        print("[FIREBASE] Active projection repaired for rickshaw", rid)
        return True
    except Exception as exc:
        print("[FIREBASE PROJECTION REPAIR ERROR]", repr(exc))
        return False


def start_session(
    rickshaw,
    owner,
    puller,
    master_uid,
    slave_uid,
    cloud_id=None,
    local_session_id=None,
    source="DESKTOP",
    started_at=None,
    replace_cloud_ids=None,
):
    """
    Create the global active session.

    ``replace_cloud_ids`` contains cloud sessions that this desktop already
    ended locally but that are still stale in Firebase. Only those explicitly
    known stale IDs may be replaced atomically. A genuine mobile/other-device
    session still raises SessionConflictError.
    """
    if not initialize_firebase():
        raise RuntimeError("Firebase is unavailable. Session was not started.")

    cloud_id = cloud_id or generate_session_id()
    payload = _session_payload(
        rickshaw,
        owner,
        puller,
        master_uid,
        slave_uid,
        cloud_id,
        source=source,
        local_session_id=local_session_id,
        started_at=started_at,
    )

    rid = str(rickshaw["id"])
    active_ref = db.reference(f"live/active_sessions/{rid}")
    replace_cloud_ids = {
        str(value).strip()
        for value in (replace_cloud_ids or [])
        if str(value or "").strip()
    }
    replaced_session = None
    adopted_session = None

    def claim(current):
        nonlocal replaced_session, adopted_session

        if current is None or current.get("status") != "ACTIVE":
            return payload

        current_cloud_id = str(
            current.get("cloud_session_id")
            or current.get("cloud_id")
            or ""
        ).strip()

        # Idempotent retry of the same start request.
        if current_cloud_id == cloud_id:
            adopted_session = copy.deepcopy(current)
            return current

        # If Firebase already contains the exact same owner/puller assignment,
        # treat it as the same operational session rather than a destructive
        # conflict. This commonly happens after a previous response timed out
        # even though Firebase committed the write.
        same_owner = str(current.get("owner_id") or "") == str(owner.get("id") or "")
        same_puller = str(current.get("puller_id") or "") == str(puller.get("id") or "")
        current_master = normalize_uid(current.get("master_uid"))
        current_slave = normalize_uid(current.get("slave_uid"))
        requested_master = normalize_uid(master_uid)
        requested_slave = normalize_uid(slave_uid)
        same_master = not current_master or current_master == requested_master
        same_slave = not current_slave or current_slave == requested_slave

        if same_owner and same_puller and same_master and same_slave:
            adopted_session = copy.deepcopy(current)
            return current

        # A previous desktop END may already be complete in SQLite while its
        # cloud delete is still pending. Such a specifically identified stale
        # record may be replaced by the new session.
        if current_cloud_id and current_cloud_id in replace_cloud_ids:
            replaced_session = copy.deepcopy(current)
            return payload

        raise SessionConflictError(
            "This rickshaw already has an active session.",
            current_session=current,
        )

    try:
        active_ref.transaction(claim)

        # A retry may discover that Firebase already committed the same
        # assignment under an older cloud ID. Reuse that cloud record so the
        # desktop and website converge instead of creating a false conflict.
        effective_payload = (
            adopted_session
            if isinstance(adopted_session, dict)
            else payload
        )
        effective_cloud_id = str(
            effective_payload.get("cloud_session_id")
            or effective_payload.get("cloud_id")
            or cloud_id
        ).strip()

        # Write the critical website/live state first and keep it small. The
        # public ACTIVE/IDLE status must not depend on a Base64 photo upload.
        live = _active_live_payload(rickshaw, owner, puller, effective_payload)
        history = {
            key: value
            for key, value in effective_payload.items()
            if key != "puller_photo"
        }
        history["cloud_session_id"] = effective_cloud_id
        history["history_status"] = "ACTIVE"

        updates = {
            f"history/sessions/{effective_cloud_id}": history,
            f"live/rickshaws/{rid}": live,
        }

        # Preserve the old stale session as ended history when we replace it.
        if isinstance(replaced_session, dict):
            replaced_cloud_id = str(
                replaced_session.get("cloud_session_id")
                or replaced_session.get("cloud_id")
                or ""
            ).strip()
            if replaced_cloud_id and replaced_cloud_id != effective_cloud_id:
                updates[f"history/sessions/{replaced_cloud_id}"] = {
                    **replaced_session,
                    "status": "SUPERSEDED",
                    "history_status": "SUPERSEDED",
                    "ended_at": now_iso(),
                    "ended_by": "DESKTOP",
                    "reason": "STALE_CLOUD_SESSION_REPLACED",
                    "updated_at": now_iso(),
                }

        token = rickshaw.get("qr_token")
        if token:
            updates[f"public/by_token/{token}"] = _public_from_live(rickshaw, live)

        db.reference().update(updates)

        # Photo synchronization is best-effort and deliberately non-critical.
        # Even if it times out, the website has already received ACTIVE state.
        try:
            photo_source = puller.get("photo_url") or puller.get("photo_path") or ""
            puller_photo = photo_to_base64(photo_source) if photo_source else ""
            if puller_photo:
                photo_updates = {
                    f"live/rickshaws/{rid}/puller_photo": puller_photo,
                }
                if token:
                    photo_updates[f"public/by_token/{token}/puller_photo"] = puller_photo
                db.reference().update(photo_updates)
        except Exception as photo_exc:
            print("[FIREBASE PHOTO SYNC WARNING]", repr(photo_exc))

        print("[FIREBASE] Session started:", effective_cloud_id, "rickshaw", rid)
        return effective_payload
    except SessionConflictError as conflict:
        # Even a genuine conflict should repair the public projection from the
        # session Firebase says is active. This fixes the case where the web
        # page stayed IDLE although /live/active_sessions already contained an
        # ACTIVE record.
        try:
            if isinstance(conflict.current_session, dict):
                repair_active_projection(rickshaw, conflict.current_session)
        except Exception as repair_exc:
            print("[FIREBASE CONFLICT PROJECTION WARNING]", repr(repair_exc))
        raise
    except Exception as exc:
        print("[FIREBASE START SESSION ERROR]", repr(exc))
        raise


def end_session(
    rickshaw,
    cloud_id=None,
    expected_owner_id=None,
    expected_puller_id=None,
    expected_started_at=None,
    ended_by="DESKTOP",
    status="COMPLETED",
    reason="",
    ended_at=None,
):
    """End one active session with a normal Firebase read + atomic update.

    Why this implementation intentionally does NOT use ``Reference.transaction``:
    the desktop already runs Firebase work on a background thread and the Admin
    SDK read/write path is known to work on this installation.  Transactions
    add an additional conditional-request/retry path which can fail on some
    slow/proxied connections even when ordinary authenticated reads/writes are
    healthy.

    The final multi-location ``update`` is atomic on Realtime Database: the
    active row is deleted at the same time that history, live IDLE state and
    the public QR projection are written.  Therefore the website cannot be
    left ACTIVE merely because a later projection write failed.
    """
    if not initialize_firebase():
        raise RuntimeError("Firebase is unavailable. Session was not ended.")

    rid = str(rickshaw["id"])
    active_path = f"live/active_sessions/{rid}"
    current = db.reference(active_path).get()
    ended_at = ended_at or now_iso()

    requested_cloud_id = str(cloud_id or "").strip()

    # --------------------------------------------------------
    # VALIDATE THE CURRENT CLOUD ASSIGNMENT, IF ONE EXISTS
    # --------------------------------------------------------
    if isinstance(current, dict):
        current_cloud_id = str(
            current.get("cloud_session_id")
            or current.get("cloud_id")
            or ""
        ).strip()

        # A cloud ID can legitimately differ after reconciliation.  Participant
        # identity is the deciding factor before the desktop ends the row.
        if not _matches_expected_session(
            current,
            expected_owner_id=expected_owner_id,
            expected_puller_id=expected_puller_id,
            expected_started_at=expected_started_at,
        ):
            raise SessionConflictError(
                "A different Firebase session is now active for this rickshaw.",
                current_session=current,
            )

        target_cloud_id = current_cloud_id or requested_cloud_id or generate_session_id()

        ended = {
            **current,
            "cloud_session_id": target_cloud_id,
            "ended_at": ended_at,
            "status": status,
            "history_status": status,
            "reason": reason or "",
            "ended_by": str(ended_by or "DESKTOP").upper(),
            "updated_at": now_iso(),
        }
    else:
        # Idempotent retry: an earlier END may already have deleted the active
        # row.  We still repair the live/public IDLE projection.
        target_cloud_id = requested_cloud_id
        ended = None

    # --------------------------------------------------------
    # BUILD ONE ATOMIC MULTI-PATH UPDATE
    # --------------------------------------------------------
    live = _idle_live_payload(rickshaw, ended_at)

    updates = {
        active_path: None,
        f"live/rickshaws/{rid}": live,
    }

    if ended is not None and target_cloud_id:
        updates[f"history/sessions/{target_cloud_id}"] = ended

    token = rickshaw.get("qr_token")
    if token:
        updates[f"public/by_token/{token}"] = _public_from_live(rickshaw, live)

    # One authenticated write performs DELETE + history + IDLE projection.
    # If this call fails, nothing in this multi-path update is committed and
    # the caller's existing background retry queue simply tries again.
    db.reference().update(updates)

    if ended is None:
        print("[FIREBASE] Active session already absent; IDLE state repaired for", rid)
        return None

    print("[FIREBASE] Session ended atomically:", target_cloud_id, "rickshaw", rid)
    return ended

def get_session_history():
    """Return Firebase session history for mobile/remote event synchronization."""
    if not initialize_firebase():
        return None

    try:
        data = db.reference("history/sessions").get()
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print("[FIREBASE GET HISTORY ERROR]", repr(exc))
        return None


def get_active_sessions():
    """Return the current cloud active-session map.

    Returns:
        dict: successful Firebase read (an empty dict means there really are
              no active sessions).
        None: Firebase/network read failed. Callers MUST NOT interpret this as
              an empty cloud state, because doing so could incorrectly close
              locally mirrored sessions while the network is unavailable.
    """
    if not initialize_firebase():
        return None
    try:
        data = db.reference("live/active_sessions").get()
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print("[FIREBASE GET ACTIVE ERROR]", repr(exc))
        return None


def listen_active_sessions(callback):
    """
    Listen for /live/active_sessions without performing an extra Firebase GET
    for every stream event.

    The Admin SDK listener already gives us the changed data.  Keeping a small
    in-memory snapshot here avoids unnecessary network traffic and prevents a
    slow connection from creating a backlog of listener GET requests.
    """
    if not initialize_firebase():
        return None

    ref = db.reference("live/active_sessions")
    cache = {}
    cache_lock = threading.Lock()

    def apply_event(path, value):
        nonlocal cache

        clean_path = str(path or "/").strip()

        if clean_path in ("", "/"):
            cache = value if isinstance(value, dict) else {}
            return

        parts = [part for part in clean_path.strip("/").split("/") if part]
        if not parts:
            cache = value if isinstance(value, dict) else {}
            return

        node = cache
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child

        leaf = parts[-1]
        if value is None:
            node.pop(leaf, None)
        else:
            node[leaf] = value

    def on_event(event):
        try:
            with cache_lock:
                apply_event(event.path, event.data)
                snapshot = copy.deepcopy(cache)

            callback(snapshot)

        except Exception as exc:
            print("[FIREBASE LISTENER CALLBACK ERROR]", repr(exc))

    try:
        return ref.listen(on_event)
    except Exception as exc:
        print("[FIREBASE LISTENER ERROR]", repr(exc))
        return None


def get_public_rickshaw(token):
    if not initialize_firebase() or not token:
        return None
    try:
        data = db.reference(f"public/by_token/{token}").get()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        print("[FIREBASE PUBLIC READ ERROR]", repr(exc))
        return None


def get_master_owner_by_uid(uid):
    if not initialize_firebase():
        return None
    uid = normalize_uid(uid)
    if not uid:
        return None
    try:
        index = db.reference(f"indexes/master_cards/{firebase_key(uid)}").get()
        if not index or normalize_uid(index.get("uid")) != uid:
            return None
        owner_id = index.get("owner_id")
        return db.reference(f"master/owners/{owner_id}").get()
    except Exception as exc:
        print("[FIREBASE OWNER LOOKUP ERROR]", repr(exc))
        return None


def get_master_puller_by_uid(uid):
    if not initialize_firebase():
        return None
    uid = normalize_uid(uid)
    if not uid:
        return None
    try:
        index = db.reference(f"indexes/slave_cards/{firebase_key(uid)}").get()
        if not index or normalize_uid(index.get("uid")) != uid:
            return None
        puller_id = index.get("puller_id")
        return db.reference(f"master/pullers/{puller_id}").get()
    except Exception as exc:
        print("[FIREBASE PULLER LOOKUP ERROR]", repr(exc))
        return None


def update_rickshaw_state(rickshaw, status, session=None):
    """Compatibility helper for older callers."""
    if not initialize_firebase():
        return False
    try:
        rid = str(rickshaw["id"])
        if status == "ACTIVE" and session:
            live = {
                **_rickshaw_payload(rickshaw),
                "status": "ACTIVE",
                "cloud_session_id": session.get("cloud_id") or session.get("cloud_session_id"),
                "puller_id": session.get("puller_id"),
                "puller_name": session.get("puller_name", ""),
                "puller_code": session.get("puller_code", ""),
                "puller_photo": photo_to_base64(
                    session.get("puller_photo") or session.get("photo_path") or ""
                ),
                "started_at": session.get("started_at"),
                "ended_at": None,
                "updated_at": now_iso(),
            }
        else:
            live = _idle_live_payload(rickshaw)
        updates = {f"live/rickshaws/{rid}": live}
        token = rickshaw.get("qr_token")
        if token:
            updates[f"public/by_token/{token}"] = _public_from_live(rickshaw, live)
        db.reference().update(updates)
        return True
    except Exception as exc:
        print("[FIREBASE STATE ERROR]", repr(exc))
        return False


def firebase_session_started(rickshaw, session):
    """
    Compatibility wrapper. New main.py uses start_session() directly so that
    the active-session conflict check is performed atomically.
    """
    try:
        owner = {
            "id": session.get("owner_id") or rickshaw.get("owner_id"),
            "name": session.get("owner_name") or rickshaw.get("owner_name", ""),
            "owner_id": session.get("owner_code") or rickshaw.get("owner_code", ""),
        }
        puller = {
            "id": session.get("puller_id"),
            "name": session.get("puller_name", ""),
            "puller_id": session.get("puller_code", ""),
            "phone": session.get("puller_phone", ""),
            "photo_path": session.get("puller_photo") or session.get("photo_path") or "",
        }
        start_session(
            rickshaw,
            owner,
            puller,
            session.get("master_uid", ""),
            session.get("slave_uid", ""),
            cloud_id=session.get("cloud_id") or session.get("cloud_session_id"),
            local_session_id=session.get("id"),
            source=session.get("source", "DESKTOP"),
            started_at=session.get("started_at"),
        )
        return True
    except Exception as exc:
        print("[FIREBASE SESSION START WRAPPER ERROR]", repr(exc))
        return False


def firebase_session_ended(rickshaw, session=None):
    try:
        cloud_id = None
        if session:
            cloud_id = session.get("cloud_id") or session.get("cloud_session_id")
        end_session(rickshaw, cloud_id=cloud_id)
        return True
    except Exception as exc:
        print("[FIREBASE SESSION END WRAPPER ERROR]", repr(exc))
        return False


def firebase_set_idle(rickshaw):
    try:
        end_session(rickshaw, ended_by="DESKTOP", status="COMPLETED")
        return True
    except Exception as exc:
        print("[FIREBASE SET IDLE ERROR]", repr(exc))
        return False


def firebase_set_active(rickshaw, session):
    return firebase_session_started(rickshaw, session)

# ============================================================
# MOBILE OWNER AUTHENTICATION MANAGEMENT
# ============================================================

def _normalize_email(email):
    return str(email or "").strip().lower()


def _mobile_access_matches_owner(payload, owner_id):
    if not isinstance(payload, dict):
        return False

    owner_key = str(owner_id)
    payload_key = str(
        payload.get("owner_id_key")
        or payload.get("owner_id")
        or ""
    )
    return payload_key == owner_key


def _find_mobile_access_for_owner(owner_id):
    """Return all /mobile_access records linked to one SQLite owner ID."""
    data = db.reference("mobile_access").get()
    if not isinstance(data, dict):
        return []

    matches = []
    for uid, payload in data.items():
        if _mobile_access_matches_owner(payload, owner_id):
            matches.append((str(uid), dict(payload)))
    return matches


def _get_auth_user_by_uid(uid):
    uid = str(uid or "").strip()
    if not uid:
        return None
    try:
        return auth.get_user(uid)
    except auth.UserNotFoundError:
        return None


def _get_auth_user_by_email(email):
    email = _normalize_email(email)
    if not email:
        return None
    try:
        return auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        return None


def _mobile_account_result(user, access_payload=None, duplicate_count=0):
    if user is None:
        return {
            "found": False,
            "uid": "",
            "email": "",
            "enabled": False,
            "auth_disabled": False,
            "access_active": False,
            "duplicate_count": int(duplicate_count or 0),
        }

    access_payload = access_payload if isinstance(access_payload, dict) else {}
    access_active = bool(access_payload.get("active", False))
    auth_disabled = bool(getattr(user, "disabled", False))

    return {
        "found": True,
        "uid": str(user.uid),
        "email": _normalize_email(user.email or access_payload.get("email")),
        "enabled": bool(access_active and not auth_disabled),
        "auth_disabled": auth_disabled,
        "access_active": access_active,
        "duplicate_count": int(duplicate_count or 0),
        "owner_id": access_payload.get("owner_id"),
        "owner_id_key": str(access_payload.get("owner_id_key") or ""),
    }


def get_owner_mobile_account(
    owner_id,
    known_uid="",
    known_email=""
):
    """Find the Firebase Auth account linked to a desktop owner.

    The authoritative owner-to-login link is /mobile_access/{uid}, matching the
    existing mobile app security rules and admin account-creation script.
    """
    if not initialize_firebase():
        raise RuntimeError("Firebase Admin SDK could not be initialized.")

    owner_id = int(owner_id)
    known_uid = str(known_uid or "").strip()
    known_email = _normalize_email(known_email)

    matches = _find_mobile_access_for_owner(owner_id)
    duplicate_count = max(0, len(matches) - 1)

    if known_uid:
        for uid, payload in matches:
            if uid == known_uid:
                user = _get_auth_user_by_uid(uid)
                if user:
                    return _mobile_account_result(
                        user, payload, duplicate_count
                    )

    if known_email:
        for uid, payload in matches:
            payload_email = _normalize_email(payload.get("email"))
            user = _get_auth_user_by_uid(uid)
            if user and (
                _normalize_email(user.email) == known_email
                or payload_email == known_email
            ):
                return _mobile_account_result(
                    user, payload, duplicate_count
                )

    for uid, payload in matches:
        user = _get_auth_user_by_uid(uid)
        if user:
            return _mobile_account_result(
                user, payload, duplicate_count
            )

    if known_email:
        user = _get_auth_user_by_email(known_email)
        if user:
            payload = db.reference(f"mobile_access/{user.uid}").get()
            if _mobile_access_matches_owner(payload, owner_id):
                return _mobile_account_result(
                    user, payload, duplicate_count
                )

    if matches:
        uid, payload = matches[0]
        return {
            "found": False,
            "uid": uid,
            "email": _normalize_email(payload.get("email")),
            "enabled": False,
            "auth_disabled": False,
            "access_active": bool(payload.get("active", False)),
            "stale_mapping": True,
            "duplicate_count": duplicate_count,
        }

    return _mobile_account_result(
        None,
        duplicate_count=duplicate_count
    )


def _write_mobile_access(owner, user, active=True):
    owner_id = int(owner["id"])
    email = _normalize_email(user.email)

    payload = {
        "uid": str(user.uid),
        "owner_id": owner_id,
        "owner_id_key": str(owner_id),
        "owner_name": safe_value(owner.get("name")),
        "owner_code": safe_value(owner.get("owner_id")),
        "email": email,
        "active": bool(active),
        "updated_at": now_iso(),
    }

    # Existing login permission node
    db.reference(f"mobile_access/{user.uid}").set(payload)

    # Mobile app owner profile node
    mobile_owner_payload = {
        "owner_id": owner_id,
        "name": safe_value(owner.get("name")),
        "owner_code": safe_value(owner.get("owner_id")),
        "phone": safe_value(owner.get("phone")),
        "garage_name": safe_value(owner.get("garage_name")),
        "garage_location": safe_value(owner.get("garage_location")),
        "email": email,
        "uid": str(user.uid),
        "active": bool(active),
        "updated_at": now_iso(),
    }

    db.reference(f"mobile/owners/{owner_id}").set(
        mobile_owner_payload
    )
    return payload


def create_or_update_owner_mobile_account(
    owner,
    email,
    password="",
    known_uid="",
    known_email=""
):
    """Create or update one owner's Firebase Authentication login.

    Passwords are sent directly to Firebase Authentication and are never
    written to SQLite or Realtime Database. A blank password is allowed only
    when updating an already-linked account; in that case the current password
    remains unchanged.
    """
    if not initialize_firebase():
        raise RuntimeError("Firebase Admin SDK could not be initialized.")

    if not isinstance(owner, dict) or not owner.get("id"):
        raise ValueError("A valid owner record is required.")

    owner_id = int(owner["id"])
    email = _normalize_email(email)
    password = str(password or "")

    if not email or "@" not in email:
        raise ValueError("Enter a valid email address.")

    if password and len(password) < 6:
        raise ValueError("Password must contain at least 6 characters.")

    current = get_owner_mobile_account(
        owner_id,
        known_uid=known_uid,
        known_email=known_email
    )

    user = None
    stale_uid = ""

    if current.get("found"):
        user = _get_auth_user_by_uid(current.get("uid"))
    elif current.get("stale_mapping"):
        stale_uid = str(current.get("uid") or "").strip()

    target_user = _get_auth_user_by_email(email)
    if target_user is not None:
        target_access = db.reference(
            f"mobile_access/{target_user.uid}"
        ).get()

        if isinstance(target_access, dict) and not _mobile_access_matches_owner(
            target_access, owner_id
        ):
            raise RuntimeError(
                "This email is already linked to a different rickshaw owner."
            )

        if user is not None and target_user.uid != user.uid:
            raise RuntimeError(
                "This email belongs to a different Firebase Authentication user."
            )

        if user is None:
            if not isinstance(target_access, dict) and not password:
                raise RuntimeError(
                    "This email already exists in Firebase Authentication but "
                    "is not linked to this owner. Enter a password to confirm "
                    "that you want to link and update this account."
                )
            user = target_user

    if user is None:
        if len(password) < 6:
            raise ValueError(
                "A password of at least 6 characters is required for a new login."
            )
        user = auth.create_user(
            email=email,
            password=password,
            disabled=False,
            email_verified=False,
        )
    else:
        update_kwargs = {
            "email": email,
            "disabled": False,
        }
        if password:
            update_kwargs["password"] = password
        user = auth.update_user(user.uid, **update_kwargs)

    if stale_uid and stale_uid != user.uid:
        db.reference(f"mobile_access/{stale_uid}").delete()

    access = _write_mobile_access(owner, user, active=True)

    # Enforce one effective mobile login per owner. If old duplicate mappings
    # exist, disable them instead of leaving a second credential authorized.
    for extra_uid, _extra_payload in _find_mobile_access_for_owner(owner_id):
        if extra_uid == user.uid:
            continue
        try:
            extra_user = _get_auth_user_by_uid(extra_uid)
            if extra_user is not None:
                auth.update_user(extra_uid, disabled=True)
                auth.revoke_refresh_tokens(extra_uid)
        except Exception as exc:
            print("[MOBILE AUTH DUPLICATE DISABLE WARNING]", repr(exc))
        try:
            db.reference(f"mobile_access/{extra_uid}").update({
                "active": False,
                "updated_at": now_iso(),
            })
        except Exception as exc:
            print("[MOBILE ACCESS DUPLICATE DISABLE WARNING]", repr(exc))

    refreshed = auth.get_user(user.uid)
    return _mobile_account_result(refreshed, access)


def set_owner_mobile_password(
    owner_id,
    new_password,
    known_uid="",
    known_email=""
):
    if not initialize_firebase():
        raise RuntimeError("Firebase Admin SDK could not be initialized.")

    new_password = str(new_password or "")
    if len(new_password) < 6:
        raise ValueError("Password must contain at least 6 characters.")

    account = get_owner_mobile_account(
        owner_id,
        known_uid=known_uid,
        known_email=known_email
    )
    if not account.get("found"):
        raise RuntimeError("No mobile login is linked to this owner.")

    auth.update_user(
        account["uid"],
        password=new_password
    )
    auth.revoke_refresh_tokens(account["uid"])

    return get_owner_mobile_account(
        owner_id,
        known_uid=account["uid"],
        known_email=account.get("email", "")
    )


def set_owner_mobile_enabled(
    owner_id,
    enabled,
    known_uid="",
    known_email=""
):
    """Enable/disable both Firebase Auth and the RTDB mobile-access gate."""
    if not initialize_firebase():
        raise RuntimeError("Firebase Admin SDK could not be initialized.")

    account = get_owner_mobile_account(
        owner_id,
        known_uid=known_uid,
        known_email=known_email
    )
    if not account.get("found"):
        raise RuntimeError("No mobile login is linked to this owner.")

    uid = account["uid"]
    enabled = bool(enabled)

    # Disabling an owner disables every mapping for that owner. Enabling
    # enables only the selected primary UID and keeps any duplicates disabled.
    matches = _find_mobile_access_for_owner(owner_id)
    target_uids = [item[0] for item in matches] if not enabled else [uid]

    for target_uid in target_uids:
        target_user = _get_auth_user_by_uid(target_uid)
        if target_user is not None:
            auth.update_user(target_uid, disabled=not enabled)
            if not enabled:
                auth.revoke_refresh_tokens(target_uid)
        db.reference(f"mobile_access/{target_uid}").update({
            "active": enabled,
            "updated_at": now_iso(),
        })

    if enabled:
        for extra_uid, _extra_payload in matches:
            if extra_uid == uid:
                continue
            try:
                extra_user = _get_auth_user_by_uid(extra_uid)
                if extra_user is not None:
                    auth.update_user(extra_uid, disabled=True)
                    auth.revoke_refresh_tokens(extra_uid)
            except Exception as exc:
                print("[MOBILE AUTH DUPLICATE DISABLE WARNING]", repr(exc))
            db.reference(f"mobile_access/{extra_uid}").update({
                "active": False,
                "updated_at": now_iso(),
            })

    return get_owner_mobile_account(
        owner_id,
        known_uid=uid,
        known_email=account.get("email", "")
    )


def probe_firebase():
    """Read a tiny RTDB node to verify real network/auth connectivity.

    initialize_firebase() only creates the local Admin SDK app; it does not
    prove that the network and service-account token exchange are currently
    working. This helper performs a small real request and returns (ok, msg).
    """
    if not initialize_firebase():
        return False, "Firebase Admin SDK could not be initialized."

    try:
        db.reference("system/health_probe").get()
        return True, "Firebase Realtime Database connection is working."
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        print("[FIREBASE PROBE ERROR]", message)
        return False, message


def test_firebase():
    if not initialize_firebase():
        return False
    try:
        db.reference("system/test").set({"status": "online", "updated_at": now_iso()})
        print("[FIREBASE] Test successful.")
        return True
    except Exception as exc:
        print("[FIREBASE TEST ERROR]", repr(exc))
        return False

    
def update_google_sheet_url(url):

    if not initialize_firebase():
        return False

    try:

        db.reference(
            "settings/google_sheet/api_url"
        ).set(
            str(url).strip()
        )

        print(
            "[FIREBASE] Google Sheet URL updated"
        )

        return True


    except Exception as e:

        print(
            "[FIREBASE GOOGLE URL ERROR]",
            e
        )

        return False