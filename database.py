import os
import sqlite3
import secrets

from datetime import datetime


# ============================================================
# DATABASE LOCATION
# ============================================================

APP_DATA_DIR = os.path.join(
    os.environ.get(
        "LOCALAPPDATA",
        os.path.expanduser("~")
    ),
    "RFID_Rickshaw_System"
)

os.makedirs(
    APP_DATA_DIR,
    exist_ok=True
)

DB_NAME = os.path.join(
    APP_DATA_DIR,
    "rickshaw.db"
)


# ============================================================
# CONNECTION
# ============================================================

def connect():

    conn = sqlite3.connect(
        DB_NAME,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    conn.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return conn


# ============================================================
# CURRENT TIME
# ============================================================

def now():

    return datetime.now().isoformat(
        timespec="seconds"
    )


# ============================================================
# RELEASED RFID VALUES
# ============================================================

def released_master_uid(owner_id):

    return (
        "__RELEASED_MASTER__"
        + str(owner_id)
        + "_"
        + secrets.token_hex(8)
    )


def released_slave_uid(puller_id):

    return (
        "__RELEASED_SLAVE__"
        + str(puller_id)
        + "_"
        + secrets.token_hex(8)
    )


# ============================================================
# TABLE EXISTENCE
# ============================================================

def table_exists(conn, table_name):

    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,)
    ).fetchone()

    return row is not None


# ============================================================
# FOREIGN KEY INSPECTION
# ============================================================

def get_foreign_keys(conn, table_name):

    try:

        return conn.execute(
            f"PRAGMA foreign_key_list({table_name})"
        ).fetchall()

    except Exception:

        return []


def table_has_bad_foreign_keys(
    conn,
    table_name
):

    """
    Detects foreign keys pointing to tables that no longer exist.

    This catches errors such as:

        no such table: main.owners_old
        no such table: main.pullers_old
    """

    if not table_exists(
        conn,
        table_name
    ):

        return False

    foreign_keys = get_foreign_keys(
        conn,
        table_name
    )

    for fk in foreign_keys:

        referenced_table = fk["table"]

        if not table_exists(
            conn,
            referenced_table
        ):

            print(
                "[DATABASE REPAIR] Broken foreign key:",
                table_name,
                "->",
                referenced_table
            )

            return True

    return False


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():

    conn = connect()

    try:

        cur = conn.cursor()

        # ====================================================
        # CARDS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                card_type TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        # ====================================================
        # OWNERS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS owners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner_id TEXT,
                phone TEXT,
                garage_name TEXT,
                garage_location TEXT,
                master_uid TEXT UNIQUE NOT NULL,
                mobile_email TEXT,
                firebase_uid TEXT,
                mobile_login_enabled INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        # ====================================================
        # PULLERS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS pullers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                puller_id TEXT,
                phone TEXT,
                photo_path TEXT,
                photo_url TEXT,
                slave_uid TEXT UNIQUE NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        # ====================================================
        # RICKSHAWS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS rickshaws (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rickshaw_number TEXT UNIQUE NOT NULL,
                registration_number TEXT,
                garage_name TEXT,
                garage_location TEXT,
                owner_id INTEGER,
                qr_token TEXT UNIQUE NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,

                FOREIGN KEY(owner_id)
                    REFERENCES owners(id)
                    ON DELETE SET NULL
            )
        """)

        # ====================================================
        # SESSIONS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS rickshaw_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rickshaw_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                puller_id INTEGER,
                master_uid TEXT,
                slave_uid TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL,
                cloud_id TEXT,
                source TEXT DEFAULT 'DESKTOP',

                FOREIGN KEY(rickshaw_id)
                    REFERENCES rickshaws(id),

                FOREIGN KEY(owner_id)
                    REFERENCES owners(id),

                FOREIGN KEY(puller_id)
                    REFERENCES pullers(id)
            )
        """)

        # ====================================================
        # TRANSACTIONS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                rickshaw_id INTEGER,
                owner_id INTEGER,
                puller_id INTEGER,
                master_uid TEXT,
                slave_uid TEXT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT
            )
        """)

        conn.commit()

        # ====================================================
        # REPAIR BROKEN FOREIGN KEYS
        # ====================================================

        repair_database_schema(conn)

        # ====================================================
        # NORMAL MIGRATION
        # ====================================================

        migrate_columns(
            conn,
            "cards",
            {
                "name": "TEXT",
                "card_type": "TEXT",
                "active": "INTEGER DEFAULT 1",
                "created_at": "TEXT"
            }
        )

        migrate_columns(
            conn,
            "owners",
            {
                "owner_id": "TEXT",
                "phone": "TEXT",
                "garage_name": "TEXT",
                "garage_location": "TEXT",
                "mobile_email": "TEXT",
                "firebase_uid": "TEXT",
                "mobile_login_enabled": "INTEGER DEFAULT 0",
                "active": "INTEGER DEFAULT 1",
                "created_at": "TEXT"
            }
        )

        migrate_columns(
            conn,
            "pullers",
            {
                "puller_id": "TEXT",
                "phone": "TEXT",
                "photo_path": "TEXT",
                "photo_url": "TEXT",
                "active": "INTEGER DEFAULT 1",
                "created_at": "TEXT"
            }
        )

        migrate_columns(
            conn,
            "rickshaws",
            {
                "registration_number": "TEXT",
                "garage_name": "TEXT",
                "garage_location": "TEXT",
                "owner_id": "INTEGER",
                "qr_token": "TEXT",
                "active": "INTEGER DEFAULT 1",
                "created_at": "TEXT"
            }
        )

        migrate_columns(
            conn,
            "rickshaw_sessions",
            {
                "puller_id": "INTEGER",
                "master_uid": "TEXT",
                "slave_uid": "TEXT",
                "ended_at": "TEXT",
                "status": "TEXT",
                "cloud_id": "TEXT",
                "source": "TEXT DEFAULT 'DESKTOP'"
            }
        )

        # Cloud session IDs let Firebase-created mobile sessions and
        # locally-created desktop sessions refer to the same session.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_rickshaw_sessions_cloud_id "
            "ON rickshaw_sessions(cloud_id) "
            "WHERE cloud_id IS NOT NULL AND cloud_id != ''"
        )

        migrate_columns(
            conn,
            "transactions",
            {
                "session_id": "INTEGER",
                "rickshaw_id": "INTEGER",
                "owner_id": "INTEGER",
                "puller_id": "INTEGER",
                "master_uid": "TEXT",
                "slave_uid": "TEXT",
                "timestamp": "TEXT",
                "status": "TEXT",
                "reason": "TEXT"
            }
        )

        # ====================================================
        # REPAIR MISSING QR TOKENS
        # ====================================================

        rows = conn.execute("""
            SELECT id
            FROM rickshaws
            WHERE qr_token IS NULL
               OR qr_token = ''
        """).fetchall()

        for row in rows:

            token = secrets.token_urlsafe(24)

            while conn.execute("""
                SELECT 1
                FROM rickshaws
                WHERE qr_token = ?
            """, (
                token,
            )).fetchone():

                token = secrets.token_urlsafe(24)

            conn.execute("""
                UPDATE rickshaws
                SET qr_token = ?
                WHERE id = ?
            """, (
                token,
                row["id"]
            ))

        # ====================================================
        # REPAIR ACTIVE FLAGS
        # ====================================================

        conn.execute("""
            UPDATE cards
            SET active = 1
            WHERE active IS NULL
        """)

        conn.execute("""
            UPDATE owners
            SET active = 1
            WHERE active IS NULL
        """)

        conn.execute("""
            UPDATE owners
            SET mobile_login_enabled = 0
            WHERE mobile_login_enabled IS NULL
        """)

        conn.execute("""
            UPDATE pullers
            SET active = 1
            WHERE active IS NULL
        """)

        conn.execute("""
            UPDATE rickshaws
            SET active = 1
            WHERE active IS NULL
        """)

        # ====================================================
        # REPAIR NULL CREATED_AT
        # ====================================================

        conn.execute("""
            UPDATE cards
            SET created_at = ?
            WHERE created_at IS NULL
               OR created_at = ''
        """, (
            now(),
        ))

        conn.execute("""
            UPDATE owners
            SET created_at = ?
            WHERE created_at IS NULL
               OR created_at = ''
        """, (
            now(),
        ))

        conn.execute("""
            UPDATE pullers
            SET created_at = ?
            WHERE created_at IS NULL
               OR created_at = ''
        """, (
            now(),
        ))

        conn.execute("""
            UPDATE rickshaws
            SET created_at = ?
            WHERE created_at IS NULL
               OR created_at = ''
        """, (
            now(),
        ))

        conn.commit()

        # ====================================================
        # FOREIGN KEY CHECK
        # ====================================================

        try:

            foreign_key_errors = conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

            if foreign_key_errors:

                print(
                    "[DATABASE WARNING] "
                    "Foreign key violations found:"
                )

                for error in foreign_key_errors:

                    print(
                        "   ",
                        tuple(error)
                    )

            else:

                print(
                    "[DATABASE] Foreign key check: OK"
                )

        except Exception as e:

            print(
                "[DATABASE] "
                "Foreign key check failed:",
                repr(e)
            )

        print(
            "[DATABASE] Initialization successful."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[DATABASE INIT ERROR]",
            repr(e)
        )

        raise

    finally:

        conn.close()


# ============================================================
# BROKEN SCHEMA REPAIR
# ============================================================

def repair_database_schema(conn):

    """
    Repairs databases created by older versions.

    Fixes broken foreign keys pointing to tables such as:

        owners_old
        pullers_old
    """

    print(
        "[DATABASE] Checking schema integrity..."
    )

    bad_rickshaws = table_has_bad_foreign_keys(
        conn,
        "rickshaws"
    )

    bad_sessions = table_has_bad_foreign_keys(
        conn,
        "rickshaw_sessions"
    )

    # ========================================================
    # REBUILD RICKSHAWS
    # ========================================================

    if bad_rickshaws:

        print(
            "[DATABASE REPAIR] "
            "Rebuilding rickshaws table..."
        )

        rebuild_rickshaws_table(conn)

    # ========================================================
    # REBUILD SESSIONS
    # ========================================================

    if bad_sessions:

        print(
            "[DATABASE REPAIR] "
            "Rebuilding rickshaw_sessions table..."
        )

        rebuild_sessions_table(conn)

    # ========================================================
    # CHECK AGAIN
    # ========================================================

    if (
        not table_has_bad_foreign_keys(
            conn,
            "rickshaws"
        )
        and
        not table_has_bad_foreign_keys(
            conn,
            "rickshaw_sessions"
        )
    ):

        print(
            "[DATABASE REPAIR] "
            "Schema repair complete."
        )

    conn.commit()


# ============================================================
# REBUILD RICKSHAWS
# ============================================================

def rebuild_rickshaws_table(conn):

    """
    Rebuild rickshaws using the correct owners reference.
    Existing IDs and data are preserved.
    """

    conn.execute(
        "PRAGMA foreign_keys = OFF"
    )

    try:

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(rickshaws)"
            ).fetchall()
        }

        conn.execute("""
            ALTER TABLE rickshaws
            RENAME TO rickshaws_repair_old
        """)

        conn.execute("""
            CREATE TABLE rickshaws (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rickshaw_number TEXT UNIQUE NOT NULL,
                registration_number TEXT,
                garage_name TEXT,
                garage_location TEXT,
                owner_id INTEGER,
                qr_token TEXT UNIQUE NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,

                FOREIGN KEY(owner_id)
                    REFERENCES owners(id)
                    ON DELETE SET NULL
            )
        """)

        def col(
            name,
            default="NULL"
        ):

            if name in columns:

                return name

            return default

        conn.execute(f"""
            INSERT INTO rickshaws
            (
                id,
                rickshaw_number,
                registration_number,
                garage_name,
                garage_location,
                owner_id,
                qr_token,
                active,
                created_at
            )
            SELECT
                id,
                rickshaw_number,
                {col("registration_number")},
                {col("garage_name")},
                {col("garage_location")},
                {col("owner_id")},
                {col("qr_token")},
                {col("active", "1")},
                {col("created_at", "''")}
            FROM rickshaws_repair_old
        """)

        conn.execute("""
            DROP TABLE rickshaws_repair_old
        """)

        conn.commit()

        print(
            "[DATABASE REPAIR] "
            "rickshaws rebuilt successfully."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[DATABASE REPAIR ERROR] rickshaws:",
            repr(e)
        )

        raise

    finally:

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )


# ============================================================
# REBUILD SESSIONS
# ============================================================

def rebuild_sessions_table(conn):

    """
    Rebuild rickshaw_sessions using:

        rickshaws
        owners
        pullers
    """

    conn.execute(
        "PRAGMA foreign_keys = OFF"
    )

    try:

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(rickshaw_sessions)"
            ).fetchall()
        }

        conn.execute("""
            ALTER TABLE rickshaw_sessions
            RENAME TO rickshaw_sessions_repair_old
        """)

        conn.execute("""
            CREATE TABLE rickshaw_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rickshaw_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                puller_id INTEGER,
                master_uid TEXT,
                slave_uid TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL,
                cloud_id TEXT,
                source TEXT DEFAULT 'DESKTOP',

                FOREIGN KEY(rickshaw_id)
                    REFERENCES rickshaws(id),

                FOREIGN KEY(owner_id)
                    REFERENCES owners(id),

                FOREIGN KEY(puller_id)
                    REFERENCES pullers(id)
            )
        """)

        def col(
            name,
            default="NULL"
        ):

            if name in columns:

                return name

            return default

        conn.execute(f"""
            INSERT INTO rickshaw_sessions
            (
                id,
                rickshaw_id,
                owner_id,
                puller_id,
                master_uid,
                slave_uid,
                started_at,
                ended_at,
                status,
                cloud_id,
                source
            )
            SELECT
                id,
                {col("rickshaw_id")},
                {col("owner_id")},
                {col("puller_id")},
                {col("master_uid")},
                {col("slave_uid")},
                {col("started_at", "''")},
                {col("ended_at")},
                {col("status", "'COMPLETED'")},
                {col("cloud_id")},
                {col("source", "'DESKTOP'")}
            FROM rickshaw_sessions_repair_old
        """)

        conn.execute("""
            DROP TABLE rickshaw_sessions_repair_old
        """)

        conn.commit()

        print(
            "[DATABASE REPAIR] "
            "rickshaw_sessions rebuilt successfully."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[DATABASE REPAIR ERROR] sessions:",
            repr(e)
        )

        raise

    finally:

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )


# ============================================================
# MIGRATION HELPER
# ============================================================

def migrate_columns(
    conn,
    table_name,
    columns
):

    cur = conn.cursor()

    cur.execute(
        f"PRAGMA table_info({table_name})"
    )

    existing_columns = {
        row[1]
        for row in cur.fetchall()
    }

    for column_name, column_type in columns.items():

        if column_name not in existing_columns:

            try:

                cur.execute(
                    f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN {column_name} {column_type}
                    """
                )

                print(
                    f"[MIGRATION] Added "
                    f"{table_name}.{column_name}"
                )

            except Exception as e:

                print(
                    f"[MIGRATION ERROR] "
                    f"{table_name}.{column_name}:",
                    e
                )


# ============================================================
# CARDS
# ============================================================

def add_card(
    uid,
    name,
    card_type
):

    uid = str(
        uid or ""
    ).strip().upper()

    name = str(
        name or ""
    ).strip()

    card_type = str(
        card_type or ""
    ).strip().upper()

    if not uid:

        return (
            False,
            "RFID UID cannot be empty."
        )

    conn = connect()

    try:

        existing = conn.execute("""
            SELECT id
            FROM cards
            WHERE uid = ?
            AND active = 1
            LIMIT 1
        """, (
            uid,
        )).fetchone()

        if existing:

            return (
                False,
                "This RFID card is already registered."
            )

        inactive = conn.execute("""
            SELECT id
            FROM cards
            WHERE uid = ?
            AND active = 0
            LIMIT 1
        """, (
            uid,
        )).fetchone()

        if inactive:

            conn.execute("""
                UPDATE cards
                SET
                    name = ?,
                    card_type = ?,
                    active = 1,
                    created_at = ?
                WHERE id = ?
            """, (
                name,
                card_type,
                now(),
                inactive["id"]
            ))

        else:

            conn.execute("""
                INSERT INTO cards
                (
                    uid,
                    name,
                    card_type,
                    active,
                    created_at
                )
                VALUES (?, ?, ?, 1, ?)
            """, (
                uid,
                name,
                card_type,
                now()
            ))

        conn.commit()

        return (
            True,
            "Card added successfully."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[ADD CARD ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def get_card(uid):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT *
            FROM cards
            WHERE uid = ?
            AND active = 1
        """, (
            str(
                uid or ""
            ).strip().upper(),
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_all_cards():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT *
            FROM cards
            WHERE active = 1
            ORDER BY id DESC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


def delete_card(card_id):

    conn = connect()

    try:

        result = conn.execute("""
            UPDATE cards
            SET active = 0
            WHERE id = ?
            AND active = 1
        """, (
            card_id,
        ))

        conn.commit()

        return result.rowcount > 0

    except Exception as e:

        conn.rollback()

        print(
            "[DELETE CARD ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


# ============================================================
# OWNERS
# ============================================================

def add_owner(
    name,
    owner_id,
    phone,
    garage_name,
    master_uid,
    garage_location=""
):

    master_uid = str(
        master_uid or ""
    ).strip().upper()

    if not master_uid:

        return (
            False,
            "Master RFID UID cannot be empty."
        )

    conn = connect()

    try:

        existing = conn.execute("""
            SELECT id
            FROM owners
            WHERE master_uid = ?
            AND active = 1
            LIMIT 1
        """, (
            master_uid,
        )).fetchone()

        if existing:

            return (
                False,
                "This Master RFID is already assigned "
                "to an active owner."
            )

        # Owner DB IDs are used by mobile authorization. Never reuse an
        # inactive owner ID for a different person.
        conn.execute("""
            INSERT INTO owners
            (
                name,
                owner_id,
                phone,
                garage_name,
                garage_location,
                master_uid,
                mobile_email,
                firebase_uid,
                mobile_login_enabled,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '', '', 0, 1, ?)
        """, (
            name,
            owner_id,
            phone,
            garage_name,
            garage_location,
            master_uid,
            now()
        ))

        conn.commit()

        return (
            True,
            "Owner added successfully."
        )

    except sqlite3.IntegrityError as e:

        conn.rollback()

        print(
            "[ADD OWNER DATABASE ERROR]",
            repr(e)
        )

        return (
            False,
            "This Master RFID is already assigned "
            "to another owner."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[ADD OWNER ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def get_owner(owner_id):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT *
            FROM owners
            WHERE id = ?
            AND active = 1
        """, (
            owner_id,
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_owner_by_master(uid):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT *
            FROM owners
            WHERE master_uid = ?
            AND active = 1
            LIMIT 1
        """, (
            str(
                uid or ""
            ).strip().upper(),
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_all_owners():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT *
            FROM owners
            WHERE active = 1
            ORDER BY id DESC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()

# ============================================================
# OWNER MOBILE LOGIN METADATA
# ============================================================

def set_owner_mobile_login(
    owner_id,
    email="",
    firebase_uid="",
    enabled=True
):

    """Cache Firebase Authentication linkage for one active owner.

    The password is intentionally never accepted or stored by this function.
    Firebase Authentication remains the only password store.
    """

    conn = connect()

    try:

        result = conn.execute("""
            UPDATE owners
            SET
                mobile_email = ?,
                firebase_uid = ?,
                mobile_login_enabled = ?
            WHERE id = ?
            AND active = 1
        """, (
            str(email or "").strip().lower(),
            str(firebase_uid or "").strip(),
            1 if enabled else 0,
            owner_id
        ))

        conn.commit()
        return result.rowcount > 0

    except Exception as e:

        conn.rollback()
        print("[OWNER MOBILE LOGIN SAVE ERROR]", repr(e))
        return False

    finally:

        conn.close()


def set_owner_mobile_login_enabled(owner_id, enabled):

    conn = connect()

    try:

        result = conn.execute("""
            UPDATE owners
            SET mobile_login_enabled = ?
            WHERE id = ?
        """, (
            1 if enabled else 0,
            owner_id
        ))

        conn.commit()
        return result.rowcount > 0

    except Exception as e:

        conn.rollback()
        print("[OWNER MOBILE LOGIN STATUS ERROR]", repr(e))
        return False

    finally:

        conn.close()


def update_owner(
    owner_id,
    name,
    owner_id_code,
    phone,
    garage_name,
    master_uid,
    garage_location=""
):

    master_uid = str(
        master_uid or ""
    ).strip().upper()

    if not master_uid:

        return (
            False,
            "Master RFID UID cannot be empty."
        )

    conn = connect()

    try:

        current = conn.execute("""
            SELECT id
            FROM owners
            WHERE id = ?
            AND active = 1
        """, (
            owner_id,
        )).fetchone()

        if not current:

            return (
                False,
                "Owner not found."
            )

        existing = conn.execute("""
            SELECT id
            FROM owners
            WHERE master_uid = ?
            AND active = 1
            AND id != ?
            LIMIT 1
        """, (
            master_uid,
            owner_id
        )).fetchone()

        if existing:

            return (
                False,
                "This Master RFID is already assigned "
                "to another active owner."
            )

        conn.execute("""
            UPDATE owners
            SET
                name = ?,
                owner_id = ?,
                phone = ?,
                garage_name = ?,
                garage_location = ?,
                master_uid = ?
            WHERE id = ?
        """, (
            name,
            owner_id_code,
            phone,
            garage_name,
            garage_location,
            master_uid,
            owner_id
        ))

        conn.commit()

        return (
            True,
            "Owner updated successfully."
        )

    except sqlite3.IntegrityError as e:

        conn.rollback()

        print(
            "[UPDATE OWNER DATABASE ERROR]",
            repr(e)
        )

        return (
            False,
            "This Master RFID is already assigned "
            "to another owner."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[UPDATE OWNER ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def delete_owner(owner_id):

    conn = connect()

    try:

        owner = conn.execute("""
            SELECT *
            FROM owners
            WHERE id = ?
            AND active = 1
        """, (
            owner_id,
        )).fetchone()

        if not owner:

            print(
                "[DELETE OWNER] Owner not found:",
                owner_id
            )

            return False

        old_uid = owner["master_uid"]

        released_uid = released_master_uid(
            owner_id
        )

        conn.execute("""
            UPDATE owners
            SET
                active = 0,
                master_uid = ?,
                mobile_login_enabled = 0
            WHERE id = ?
        """, (
            released_uid,
            owner_id
        ))

        conn.execute("""
            UPDATE rickshaws
            SET owner_id = NULL
            WHERE owner_id = ?
        """, (
            owner_id,
        ))

        conn.commit()

        print(
            "[OWNER DELETED]",
            owner_id,
            "| RELEASED RFID:",
            old_uid
        )

        return True

    except Exception as e:

        conn.rollback()

        print(
            "[DELETE OWNER ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


# ============================================================
# PULLERS
# ============================================================

def add_puller(
    name,
    puller_id,
    phone,
    photo_path,
    slave_uid,
    photo_url=""
):

    slave_uid = str(
        slave_uid or ""
    ).strip().upper()

    if not slave_uid:

        return (
            False,
            "Slave RFID UID cannot be empty."
        )

    conn = connect()

    try:

        existing = conn.execute("""
            SELECT id
            FROM pullers
            WHERE slave_uid = ?
            AND active = 1
            LIMIT 1
        """, (
            slave_uid,
        )).fetchone()

        if existing:

            return (
                False,
                "This Slave RFID is already assigned "
                "to an active puller."
            )

        inactive = conn.execute("""
            SELECT id
            FROM pullers
            WHERE active = 0
            ORDER BY id ASC
            LIMIT 1
        """).fetchone()

        if inactive:

            conn.execute("""
                UPDATE pullers
                SET
                    name = ?,
                    puller_id = ?,
                    phone = ?,
                    photo_path = ?,
                    photo_url = ?,
                    slave_uid = ?,
                    active = 1,
                    created_at = ?
                WHERE id = ?
            """, (
                name,
                puller_id,
                phone,
                photo_path,
                photo_url,
                slave_uid,
                now(),
                inactive["id"]
            ))

        else:

            conn.execute("""
                INSERT INTO pullers
                (
                    name,
                    puller_id,
                    phone,
                    photo_path,
                    photo_url,
                    slave_uid,
                    active,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                name,
                puller_id,
                phone,
                photo_path,
                photo_url,
                slave_uid,
                now()
            ))

        conn.commit()

        return (
            True,
            "Puller added successfully."
        )

    except sqlite3.IntegrityError as e:

        conn.rollback()

        print(
            "[ADD PULLER DATABASE ERROR]",
            repr(e)
        )

        return (
            False,
            "This Slave RFID is already assigned "
            "to another puller."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[ADD PULLER ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def get_puller_by_slave(uid):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT *
            FROM pullers
            WHERE slave_uid = ?
            AND active = 1
            LIMIT 1
        """, (
            str(
                uid or ""
            ).strip().upper(),
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_puller(puller_id):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT *
            FROM pullers
            WHERE id = ?
            AND active = 1
        """, (
            puller_id,
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_all_pullers():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT *
            FROM pullers
            WHERE active = 1
            ORDER BY id DESC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


def update_puller(
    puller_id,
    name,
    puller_id_code,
    phone,
    photo_path,
    slave_uid,
    photo_url=""
):

    slave_uid = str(
        slave_uid or ""
    ).strip().upper()

    if not slave_uid:

        return (
            False,
            "Slave RFID UID cannot be empty."
        )

    conn = connect()

    try:

        current = conn.execute("""
            SELECT *
            FROM pullers
            WHERE id = ?
            AND active = 1
        """, (
            puller_id,
        )).fetchone()

        if not current:

            return (
                False,
                "Puller not found."
            )

        existing = conn.execute("""
            SELECT id
            FROM pullers
            WHERE slave_uid = ?
            AND active = 1
            AND id != ?
            LIMIT 1
        """, (
            slave_uid,
            puller_id
        )).fetchone()

        if existing:

            return (
                False,
                "This Slave RFID is already assigned "
                "to another active puller."
            )

        # Keep the existing photo if a new one wasn't provided.
        final_photo = (
            photo_path
            if photo_path
            else current["photo_path"]
        )

        final_photo_url = (
            photo_url
            if photo_url
            else (
                current["photo_url"]
                if photo_path == current["photo_path"]
                else ""
            )
        )

        conn.execute("""
            UPDATE pullers
            SET
                name = ?,
                puller_id = ?,
                phone = ?,
                photo_path = ?,
                photo_url = ?,
                slave_uid = ?
            WHERE id = ?
        """, (
            name,
            puller_id_code,
            phone,
            final_photo,
            final_photo_url,
            slave_uid,
            puller_id
        ))

        conn.commit()

        return (
            True,
            "Puller updated successfully."
        )

    except sqlite3.IntegrityError as e:

        conn.rollback()

        print(
            "[UPDATE PULLER DATABASE ERROR]",
            repr(e)
        )

        return (
            False,
            "This Slave RFID is already assigned "
            "to another puller."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[UPDATE PULLER ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def delete_puller(puller_id):

    conn = connect()

    try:

        puller = conn.execute("""
            SELECT *
            FROM pullers
            WHERE id = ?
            AND active = 1
        """, (
            puller_id,
        )).fetchone()

        if not puller:

            print(
                "[DELETE PULLER] Puller not found:",
                puller_id
            )

            return False

        old_uid = puller["slave_uid"]

        released_uid = released_slave_uid(
            puller_id
        )

        conn.execute("""
            UPDATE pullers
            SET
                active = 0,
                slave_uid = ?
            WHERE id = ?
        """, (
            released_uid,
            puller_id
        ))

        conn.commit()

        print(
            "[PULLER DELETED]",
            puller_id,
            "| RELEASED RFID:",
            old_uid
        )

        return True

    except Exception as e:

        conn.rollback()

        print(
            "[DELETE PULLER ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


# ============================================================
# RICKSHAWS
# ============================================================

def add_rickshaw(
    rickshaw_number,
    registration_number,
    garage_name,
    owner_id,
    garage_location=""
):

    rickshaw_number = str(
        rickshaw_number or ""
    ).strip()

    registration_number = str(
        registration_number or ""
    ).strip()

    garage_name = str(
        garage_name or ""
    ).strip()

    garage_location = str(
        garage_location or ""
    ).strip()

    if not rickshaw_number:

        return (
            False,
            "Rickshaw number cannot be empty."
        )

    conn = connect()

    try:

        # ====================================================
        # VALIDATE OWNER
        # ====================================================

        owner_db_id = None

        if owner_id not in (
            None,
            "",
            0,
            "0"
        ):

            try:

                owner_db_id = int(
                    owner_id
                )

            except (
                ValueError,
                TypeError
            ):

                return (
                    False,
                    "Invalid owner ID."
                )

            owner = conn.execute("""
                SELECT id
                FROM owners
                WHERE id = ?
                AND active = 1
                LIMIT 1
            """, (
                owner_db_id,
            )).fetchone()

            if not owner:

                return (
                    False,
                    "Selected owner does not exist "
                    "or has been deleted."
                )

        # ====================================================
        # CHECK ACTIVE RICKSHAW
        # ====================================================
        #
        # IMPORTANT:
        # Only ACTIVE records should prevent a new rickshaw
        # from using the same rickshaw number.
        #
        # ====================================================

        existing_active = conn.execute("""
            SELECT id
            FROM rickshaws
            WHERE rickshaw_number = ?
            AND active = 1
            LIMIT 1
        """, (
            rickshaw_number,
        )).fetchone()

        if existing_active:

            return (
                False,
                "This rickshaw number already exists."
            )

        # ====================================================
        # CHECK DELETED / INACTIVE RICKSHAW
        # ====================================================
        #
        # If the same rickshaw number was previously deleted,
        # reuse that database record.
        #
        # This prevents the UNIQUE constraint from blocking
        # the user from registering the same rickshaw again.
        #
        # ====================================================

        deleted_rickshaw = conn.execute("""
            SELECT id
            FROM rickshaws
            WHERE rickshaw_number = ?
            AND active = 0
            ORDER BY id ASC
            LIMIT 1
        """, (
            rickshaw_number,
        )).fetchone()

        # ====================================================
        # GENERATE NEW QR TOKEN
        # ====================================================

        token = secrets.token_urlsafe(24)

        while conn.execute("""
            SELECT id
            FROM rickshaws
            WHERE qr_token = ?
            LIMIT 1
        """, (
            token,
        )).fetchone():

            token = secrets.token_urlsafe(24)

        # ====================================================
        # REACTIVATE DELETED RICKSHAW
        # ====================================================

        if deleted_rickshaw:

            conn.execute("""
                UPDATE rickshaws
                SET
                    rickshaw_number = ?,
                    registration_number = ?,
                    garage_name = ?,
                    garage_location = ?,
                    owner_id = ?,
                    qr_token = ?,
                    active = 1,
                    created_at = ?
                WHERE id = ?
            """, (
                rickshaw_number,
                registration_number,
                garage_name,
                garage_location,
                owner_db_id,
                token,
                now(),
                deleted_rickshaw["id"]
            ))

            new_id = deleted_rickshaw["id"]

            conn.commit()

            print(
                "[RICKSHAW REACTIVATED]",
                new_id,
                rickshaw_number,
                "| OWNER:",
                owner_db_id
            )

            return (
                True,
                "Rickshaw added successfully."
            )

        # ====================================================
        # CREATE NEW RICKSHAW
        # ====================================================

        cur = conn.execute("""
            INSERT INTO rickshaws
            (
                rickshaw_number,
                registration_number,
                garage_name,
                garage_location,
                owner_id,
                qr_token,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            rickshaw_number,
            registration_number,
            garage_name,
            garage_location,
            owner_db_id,
            token,
            now()
        ))

        new_id = cur.lastrowid

        conn.commit()

        print(
            "[RICKSHAW SAVED]",
            new_id,
            rickshaw_number,
            "| OWNER:",
            owner_db_id
        )

        return (
            True,
            "Rickshaw added successfully."
        )

    except sqlite3.IntegrityError as e:

        conn.rollback()

        print(
            "[ADD RICKSHAW DATABASE ERROR]",
            repr(e)
        )

        return (
            False,
            "Could not save rickshaw. "
            "Rickshaw number or QR token may already exist."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[ADD RICKSHAW ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def get_rickshaw(rickshaw_id):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT

                r.*,

                o.name AS owner_name,
                o.owner_id AS owner_code,
                o.phone AS owner_phone,
                o.garage_name AS owner_garage_name,
                o.garage_location AS owner_garage_location,
                o.master_uid AS master_uid

            FROM rickshaws r

            LEFT JOIN owners o
            ON r.owner_id = o.id

            WHERE r.id = ?
            AND r.active = 1
        """, (
            rickshaw_id,
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_rickshaw_by_token(token):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT

                r.*,

                o.name AS owner_name,
                o.owner_id AS owner_code,
                o.phone AS owner_phone,

                COALESCE(
                    NULLIF(r.garage_name, ''),
                    o.garage_name
                ) AS final_garage_name,

                COALESCE(
                    NULLIF(r.garage_location, ''),
                    o.garage_location
                ) AS final_garage_location,

                o.master_uid AS master_uid

            FROM rickshaws r

            LEFT JOIN owners o
            ON r.owner_id = o.id

            WHERE r.qr_token = ?
            AND r.active = 1
        """, (
            token,
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_rickshaws_by_owner(owner_id):

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT *
            FROM rickshaws
            WHERE owner_id = ?
            AND active = 1
            ORDER BY rickshaw_number
        """, (
            owner_id,
        )).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


def get_all_rickshaws():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT

                r.*,

                o.name AS owner_name,
                o.phone AS owner_phone,
                o.owner_id AS owner_code

            FROM rickshaws r

            LEFT JOIN owners o
            ON r.owner_id = o.id

            WHERE r.active = 1

            ORDER BY r.id DESC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


def update_rickshaw(
    rickshaw_id,
    rickshaw_number,
    registration_number,
    garage_name,
    owner_id,
    garage_location=""
):

    rickshaw_number = str(
        rickshaw_number or ""
    ).strip()

    registration_number = str(
        registration_number or ""
    ).strip()

    garage_name = str(
        garage_name or ""
    ).strip()

    garage_location = str(
        garage_location or ""
    ).strip()

    if not rickshaw_number:

        return (
            False,
            "Rickshaw number cannot be empty."
        )

    conn = connect()

    try:

        current = conn.execute("""
            SELECT id
            FROM rickshaws
            WHERE id = ?
            AND active = 1
        """, (
            rickshaw_id,
        )).fetchone()

        if not current:

            return (
                False,
                "Rickshaw not found."
            )

        # ====================================================
        # VALIDATE OWNER (None is allowed / "no owner")
        # ====================================================

        owner_db_id = None

        if owner_id not in (
            None,
            "",
            0,
            "0"
        ):

            try:

                owner_db_id = int(
                    owner_id
                )

            except (
                ValueError,
                TypeError
            ):

                return (
                    False,
                    "Invalid owner ID."
                )

            owner = conn.execute("""
                SELECT id
                FROM owners
                WHERE id = ?
                AND active = 1
                LIMIT 1
            """, (
                owner_db_id,
            )).fetchone()

            if not owner:

                return (
                    False,
                    "Selected owner does not exist "
                    "or has been deleted."
                )

        # ====================================================
        # CHECK RICKSHAW NUMBER NOT USED BY ANOTHER ACTIVE ROW
        # ====================================================

        existing_active = conn.execute("""
            SELECT id
            FROM rickshaws
            WHERE rickshaw_number = ?
            AND active = 1
            AND id != ?
            LIMIT 1
        """, (
            rickshaw_number,
            rickshaw_id
        )).fetchone()

        if existing_active:

            return (
                False,
                "This rickshaw number already exists."
            )

        conn.execute("""
            UPDATE rickshaws
            SET
                rickshaw_number = ?,
                registration_number = ?,
                garage_name = ?,
                garage_location = ?,
                owner_id = ?
            WHERE id = ?
        """, (
            rickshaw_number,
            registration_number,
            garage_name,
            garage_location,
            owner_db_id,
            rickshaw_id
        ))

        conn.commit()

        print(
            "[RICKSHAW UPDATED]",
            rickshaw_id,
            rickshaw_number,
            "| OWNER:",
            owner_db_id
        )

        return (
            True,
            "Rickshaw updated successfully."
        )

    except sqlite3.IntegrityError as e:

        conn.rollback()

        print(
            "[UPDATE RICKSHAW DATABASE ERROR]",
            repr(e)
        )

        return (
            False,
            "Could not update rickshaw. "
            "Rickshaw number may already exist."
        )

    except Exception as e:

        conn.rollback()

        print(
            "[UPDATE RICKSHAW ERROR]",
            repr(e)
        )

        return False, str(e)

    finally:

        conn.close()


def delete_rickshaw(rickshaw_id):

    conn = connect()

    try:

        result = conn.execute("""
            UPDATE rickshaws
            SET active = 0
            WHERE id = ?
            AND active = 1
        """, (
            rickshaw_id,
        ))

        if result.rowcount == 0:

            print(
                "[DELETE RICKSHAW] "
                "Rickshaw not found:",
                rickshaw_id
            )

            return False

        conn.commit()

        print(
            "[RICKSHAW DELETED]",
            rickshaw_id
        )

        return True

    except Exception as e:

        conn.rollback()

        print(
            "[DELETE RICKSHAW ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


# ============================================================
# ACTIVE SESSION
# ============================================================

def get_active_session(rickshaw_id):

    conn = connect()

    try:

        row = conn.execute("""
            SELECT

                s.*,

                o.name AS owner_name,
                o.owner_id AS owner_code,
                o.phone AS owner_phone,

                p.name AS puller_name,
                p.puller_id AS puller_code,
                p.phone AS puller_phone,
                p.photo_path AS puller_photo,
                p.photo_url AS puller_photo_url

            FROM rickshaw_sessions s

            LEFT JOIN owners o
            ON s.owner_id = o.id

            LEFT JOIN pullers p
            ON s.puller_id = p.id

            WHERE s.rickshaw_id = ?
            AND s.status = 'ACTIVE'

            ORDER BY s.id DESC

            LIMIT 1
        """, (
            rickshaw_id,
        )).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:

        conn.close()


def get_active_sessions():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT

                s.*,

                r.rickshaw_number,
                r.registration_number,
                r.garage_name,
                r.garage_location,

                o.name AS owner_name,
                o.owner_id AS owner_code,
                o.phone AS owner_phone,
                o.master_uid,

                p.name AS puller_name,
                p.puller_id AS puller_code,
                p.phone AS puller_phone,
                p.slave_uid,
                p.photo_path AS puller_photo,
                p.photo_url AS puller_photo_url

            FROM rickshaw_sessions s

            LEFT JOIN rickshaws r
            ON s.rickshaw_id = r.id

            LEFT JOIN owners o
            ON s.owner_id = o.id

            LEFT JOIN pullers p
            ON s.puller_id = p.id

            WHERE s.status = 'ACTIVE'

            ORDER BY s.id ASC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# ============================================================
# START SESSION
# ============================================================

def start_rickshaw_session(
    rickshaw_id,
    owner_id,
    puller_id,
    master_uid="",
    slave_uid="",
    cloud_id="",
    source="DESKTOP",
    started_at=None
):

    conn = connect()

    try:

        active = conn.execute("""
            SELECT id, cloud_id
            FROM rickshaw_sessions
            WHERE rickshaw_id = ?
            AND status = 'ACTIVE'
            LIMIT 1
        """, (
            rickshaw_id,
        )).fetchone()

        if active:

            # Idempotent insert: if Firebase sends the same session back
            # through the realtime listener, reuse the local session row.
            if cloud_id and active["cloud_id"] == cloud_id:
                return active["id"]

            raise ValueError(
                "This rickshaw already has an active session."
            )

        if cloud_id:
            existing_cloud = conn.execute("""
                SELECT id
                FROM rickshaw_sessions
                WHERE cloud_id = ?
                LIMIT 1
            """, (cloud_id,)).fetchone()
            if existing_cloud:
                return existing_cloud["id"]

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO rickshaw_sessions
            (
                rickshaw_id,
                owner_id,
                puller_id,
                master_uid,
                slave_uid,
                started_at,
                ended_at,
                status,
                cloud_id,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, 'ACTIVE', ?, ?)
        """, (
            rickshaw_id,
            owner_id,
            puller_id,
            str(master_uid or "").strip().upper(),
            str(slave_uid or "").strip().upper(),
            started_at or now(),
            cloud_id or None,
            str(source or "DESKTOP").upper()
        ))

        session_id = cur.lastrowid

        conn.commit()

        return session_id

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# END SESSION
# ============================================================

def end_rickshaw_session(
    session_id,
    status="COMPLETED",
    ended_at=None
):

    conn = connect()

    try:

        result = conn.execute("""
            UPDATE rickshaw_sessions
            SET
                ended_at = ?,
                status = ?
            WHERE id = ?
            AND status = 'ACTIVE'
        """, (
            ended_at or now(),
            status,
            session_id
        ))

        conn.commit()

        return result.rowcount > 0

    except Exception as e:

        conn.rollback()

        print(
            "[END SESSION ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


def auto_end_rickshaw_session(session_id):

    return end_rickshaw_session(
        session_id,
        status="AUTO_ENDED"
    )


# ============================================================
# CLOUD / FIREBASE SESSION SYNCHRONIZATION
# ============================================================

def get_session_by_cloud_id(cloud_id):

    if not cloud_id:
        return None

    conn = connect()

    try:

        row = conn.execute("""
            SELECT *
            FROM rickshaw_sessions
            WHERE cloud_id = ?
            LIMIT 1
        """, (
            cloud_id,
        )).fetchone()

        return dict(row) if row else None

    finally:

        conn.close()


def set_session_cloud_id(
    session_id,
    cloud_id,
    source="DESKTOP"
):

    if not cloud_id:
        return False

    conn = connect()

    try:

        result = conn.execute("""
            UPDATE rickshaw_sessions
            SET cloud_id = ?, source = ?
            WHERE id = ?
        """, (
            cloud_id,
            str(source or "DESKTOP").upper(),
            session_id
        ))

        conn.commit()

        return result.rowcount > 0

    except Exception as e:

        conn.rollback()
        print("[SET CLOUD ID ERROR]", repr(e))
        return False

    finally:

        conn.close()


def _to_int(value):

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert_cloud_active_session(payload):

    """
    Import one Firebase /live/active_sessions record into SQLite.

    The mobile app is never allowed to create/edit owner, puller or rickshaw
    master records, so all referenced IDs must already exist locally.
    """

    if not isinstance(payload, dict):
        return None

    cloud_id = str(
        payload.get("cloud_session_id")
        or payload.get("cloud_id")
        or ""
    ).strip()

    rickshaw_id = _to_int(payload.get("rickshaw_id"))
    owner_id = _to_int(payload.get("owner_id"))
    puller_id = _to_int(payload.get("puller_id"))

    if not cloud_id or not rickshaw_id or not owner_id or not puller_id:
        print("[CLOUD SYNC] Invalid active-session payload:", payload)
        return None

    conn = connect()

    try:

        # Master records are desktop controlled. Reject cloud sessions that
        # point to unknown/deleted local records.
        rickshaw = conn.execute("""
            SELECT id FROM rickshaws
            WHERE id = ? AND active = 1
        """, (rickshaw_id,)).fetchone()

        owner = conn.execute("""
            SELECT id FROM owners
            WHERE id = ? AND active = 1
        """, (owner_id,)).fetchone()

        puller = conn.execute("""
            SELECT id FROM pullers
            WHERE id = ? AND active = 1
        """, (puller_id,)).fetchone()

        if not rickshaw or not owner or not puller:
            print(
                "[CLOUD SYNC] Session references missing master data:",
                cloud_id
            )
            return None

        existing = conn.execute("""
            SELECT *
            FROM rickshaw_sessions
            WHERE cloud_id = ?
            LIMIT 1
        """, (cloud_id,)).fetchone()

        started_at = payload.get("started_at") or now()
        master_uid = str(payload.get("master_uid") or "").strip().upper()
        slave_uid = str(payload.get("slave_uid") or "").strip().upper()
        source = str(payload.get("source") or "MOBILE").upper()

        if existing:

            conn.execute("""
                UPDATE rickshaw_sessions
                SET
                    rickshaw_id = ?,
                    owner_id = ?,
                    puller_id = ?,
                    master_uid = ?,
                    slave_uid = ?,
                    started_at = ?,
                    ended_at = NULL,
                    status = 'ACTIVE',
                    source = ?
                WHERE id = ?
            """, (
                rickshaw_id,
                owner_id,
                puller_id,
                master_uid,
                slave_uid,
                started_at,
                source,
                existing["id"]
            ))

            conn.commit()
            return existing["id"]

        active = conn.execute("""
            SELECT *
            FROM rickshaw_sessions
            WHERE rickshaw_id = ?
            AND status = 'ACTIVE'
            LIMIT 1
        """, (rickshaw_id,)).fetchone()

        if active:

            # A legacy/local session without a cloud ID can be adopted when
            # its participants match the new Firebase session.
            if (
                not active["cloud_id"]
                and active["owner_id"] == owner_id
                and active["puller_id"] == puller_id
            ):

                conn.execute("""
                    UPDATE rickshaw_sessions
                    SET cloud_id = ?, source = ?, started_at = ?
                    WHERE id = ?
                """, (
                    cloud_id,
                    source,
                    started_at,
                    active["id"]
                ))

                conn.commit()
                return active["id"]

            # Firebase is authoritative for live state. A conflicting local
            # active row is closed before importing the cloud session.
            conn.execute("""
                UPDATE rickshaw_sessions
                SET ended_at = ?, status = 'SUPERSEDED'
                WHERE id = ?
            """, (
                now(),
                active["id"]
            ))

        cur = conn.execute("""
            INSERT INTO rickshaw_sessions
            (
                rickshaw_id,
                owner_id,
                puller_id,
                master_uid,
                slave_uid,
                started_at,
                ended_at,
                status,
                cloud_id,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, 'ACTIVE', ?, ?)
        """, (
            rickshaw_id,
            owner_id,
            puller_id,
            master_uid,
            slave_uid,
            started_at,
            cloud_id,
            source
        ))

        session_id = cur.lastrowid

        # Only mobile/remote-created sessions need a local transaction added
        # by synchronization. Desktop sessions create their own transaction.
        if source != "DESKTOP":
            conn.execute("""
                INSERT INTO transactions
                (
                    session_id,
                    rickshaw_id,
                    owner_id,
                    puller_id,
                    master_uid,
                    slave_uid,
                    timestamp,
                    status,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                rickshaw_id,
                owner_id,
                puller_id,
                master_uid,
                slave_uid,
                now(),
                "REMOTE_SESSION_STARTED",
                source
            ))

        conn.commit()
        return session_id

    except Exception as e:

        conn.rollback()
        print("[CLOUD SESSION UPSERT ERROR]", repr(e))
        return None

    finally:

        conn.close()


def reconcile_cloud_active_sessions(cloud_sessions):

    """
    Make SQLite active sessions match Firebase active sessions.

    Returns a small change summary that the GUI can use for logging/debugging.
    """

    if not isinstance(cloud_sessions, dict):
        cloud_sessions = {}

    imported = []
    active_cloud_ids = set()

    for _rickshaw_key, payload in cloud_sessions.items():

        if not isinstance(payload, dict):
            continue

        cloud_id = str(
            payload.get("cloud_session_id")
            or payload.get("cloud_id")
            or ""
        ).strip()

        if not cloud_id:
            continue

        active_cloud_ids.add(cloud_id)

        session_id = upsert_cloud_active_session(payload)

        if session_id:
            imported.append(session_id)

    conn = connect()
    ended = []

    try:

        local_cloud_active = conn.execute("""
            SELECT *
            FROM rickshaw_sessions
            WHERE status = 'ACTIVE'
            AND cloud_id IS NOT NULL
            AND cloud_id != ''
        """).fetchall()

        protected_desktop = []

        for row in local_cloud_active:

            if row["cloud_id"] in active_cloud_ids:
                continue

            source = str(row["source"] or "").upper()

            # IMPORTANT DISCONNECT SAFETY:
            # A desktop-created session is authoritative on this PC until the
            # operator explicitly ends it. A temporarily empty Firebase
            # snapshot (CDN/network flap, delayed START write, transient RTDB
            # read) must NEVER close that local session.
            #
            # Remote/mobile sessions are still mirrored from Firebase and may
            # be closed when their cloud active row disappears.
            if source == "DESKTOP":
                protected_desktop.append(row["id"])
                continue

            ended_at = now()

            conn.execute("""
                UPDATE rickshaw_sessions
                SET ended_at = ?, status = 'COMPLETED'
                WHERE id = ?
                AND status = 'ACTIVE'
            """, (
                ended_at,
                row["id"]
            ))

            conn.execute("""
                INSERT INTO transactions
                (
                    session_id,
                    rickshaw_id,
                    owner_id,
                    puller_id,
                    master_uid,
                    slave_uid,
                    timestamp,
                    status,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["id"],
                row["rickshaw_id"],
                row["owner_id"],
                row["puller_id"],
                row["master_uid"],
                row["slave_uid"],
                ended_at,
                "REMOTE_SESSION_ENDED",
                "FIREBASE_ACTIVE_SESSION_REMOVED"
            ))

            ended.append(row["id"])

        conn.commit()

    except Exception as e:

        conn.rollback()
        print("[CLOUD RECONCILE ERROR]", repr(e))

    finally:

        conn.close()

    return {
        "active": imported,
        "ended": ended,
        "protected_desktop": protected_desktop
    }


# ============================================================
# TRANSACTIONS
# ============================================================

def save_transaction(
    session_id,
    rickshaw_id,
    owner_id,
    puller_id,
    master_uid,
    slave_uid,
    status,
    reason=""
):

    conn = connect()

    try:

        conn.execute("""
            INSERT INTO transactions
            (
                session_id,
                rickshaw_id,
                owner_id,
                puller_id,
                master_uid,
                slave_uid,
                timestamp,
                status,
                reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            rickshaw_id,
            owner_id,
            puller_id,
            master_uid,
            slave_uid,
            now(),
            status,
            reason
        ))

        conn.commit()

        return True

    except Exception as e:

        conn.rollback()

        print(
            "[SAVE TRANSACTION ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


def get_transactions():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT

                t.*,

                r.rickshaw_number,

                o.name AS owner_name,
                o.phone AS owner_phone,

                p.name AS puller_name,
                p.phone AS puller_phone

            FROM transactions t

            LEFT JOIN rickshaws r
            ON t.rickshaw_id = r.id

            LEFT JOIN owners o
            ON t.owner_id = o.id

            LEFT JOIN pullers p
            ON t.puller_id = p.id

            ORDER BY t.id DESC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# ============================================================
# SESSION HISTORY
# ============================================================

def get_sessions():

    conn = connect()

    try:

        rows = conn.execute("""
            SELECT

                s.*,

                r.rickshaw_number,
                r.registration_number,
                r.garage_name,
                r.garage_location,

                o.name AS owner_name,
                o.owner_id AS owner_code,
                o.phone AS owner_phone,

                p.name AS puller_name,
                p.puller_id AS puller_code,
                p.phone AS puller_phone,
                p.photo_path AS puller_photo,
                p.photo_url AS puller_photo_url

            FROM rickshaw_sessions s

            LEFT JOIN rickshaws r
            ON s.rickshaw_id = r.id

            LEFT JOIN owners o
            ON s.owner_id = o.id

            LEFT JOIN pullers p
            ON s.puller_id = p.id

            ORDER BY s.id DESC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# ============================================================
# CLEAR HISTORY
# ============================================================

def clear_history():

    conn = connect()

    try:

        transaction_count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM transactions
        """).fetchone()["total"]

        session_count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM rickshaw_sessions
            WHERE status != 'ACTIVE'
        """).fetchone()["total"]

        # ----------------------------------------------------
        # Delete transactions
        # ----------------------------------------------------

        conn.execute("""
            DELETE FROM transactions
        """)

        # ----------------------------------------------------
        # Delete completed/auto-ended sessions
        # ----------------------------------------------------

        conn.execute("""
            DELETE FROM rickshaw_sessions
            WHERE status != 'ACTIVE'
        """)

        conn.commit()

        print(
            "[HISTORY CLEARED]",
            "| Transactions:",
            transaction_count,
            "| Sessions:",
            session_count
        )

        return True

    except Exception as e:

        conn.rollback()

        print(
            "[CLEAR HISTORY ERROR]",
            repr(e)
        )

        return False

    finally:

        conn.close()


# ============================================================
# DATABASE TEST
# ============================================================

def database_test():

    print()
    print("=" * 60)
    print("RFID RICKSHAW DATABASE TEST")
    print("=" * 60)
    print()

    print("Database:")
    print(DB_NAME)
    print()

    conn = connect()

    try:

        tables = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
        """).fetchall()

        print("Tables:")

        for table in tables:

            print(
                "  -",
                table["name"]
            )

        print()

        owners = conn.execute("""
            SELECT COUNT(*) AS total
            FROM owners
            WHERE active = 1
        """).fetchone()["total"]

        pullers = conn.execute("""
            SELECT COUNT(*) AS total
            FROM pullers
            WHERE active = 1
        """).fetchone()["total"]

        rickshaws = conn.execute("""
            SELECT COUNT(*) AS total
            FROM rickshaws
            WHERE active = 1
        """).fetchone()["total"]

        sessions = conn.execute("""
            SELECT COUNT(*) AS total
            FROM rickshaw_sessions
            WHERE status = 'ACTIVE'
        """).fetchone()["total"]

        transactions = conn.execute("""
            SELECT COUNT(*) AS total
            FROM transactions
        """).fetchone()["total"]

        print(
            "Active Owners:",
            owners
        )

        print(
            "Active Pullers:",
            pullers
        )

        print(
            "Active Rickshaws:",
            rickshaws
        )

        print(
            "Active Sessions:",
            sessions
        )

        print(
            "Transactions:",
            transactions
        )

        print()

        # ----------------------------------------------------
        # Verify foreign keys
        # ----------------------------------------------------

        print("Foreign Key Check:")

        errors = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if errors:

            print(
                "  FAILED"
            )

            for error in errors:

                print(
                    "   ",
                    tuple(error)
                )

        else:

            print(
                "  OK"
            )

        print()
        print("=" * 60)

    finally:

        conn.close()


# ============================================================
# AUTOMATIC INITIALIZATION
# ============================================================

if __name__ == "__main__":

    init_database()

    database_test()