import sys
import os
import firebase_service
import json
import threading
import socket
import requests
import webbrowser

from datetime import datetime, timezone, timedelta

# ============================================================
# TIME CONVERTER
# ============================================================

def convert_firebase_time(value):

    if not value:
        return ""

    try:
        # Firebase UTC format
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        # Convert UTC to Bangladesh time
        bd_time = dt.astimezone(
            timezone(timedelta(hours=6))
        )

        return bd_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception:
        return value

from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal
)

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QMessageBox,
    QStackedWidget,
    QFrame,
    QHeaderView,
    QGroupBox,
    QSpinBox,
    QFileDialog,
    QCheckBox,
    QComboBox,
    QScrollArea
)

import database
import qr_server


# ============================================================
# APPLICATION DATA
# ============================================================

APP_DATA_DIR = os.path.join(
    os.environ.get(
        "LOCALAPPDATA",
        os.path.expanduser("~")
    ),
    "RFID_Rickshaw_System"
)

os.makedirs(APP_DATA_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(
    APP_DATA_DIR,
    "settings.json"
)


PHOTOS_DIR = os.path.join(
    APP_DATA_DIR,
    "photos",
    "pullers"
)

os.makedirs(
    PHOTOS_DIR,
    exist_ok=True
)


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_SESSION_TIME = 3600
DEFAULT_POPUP_TIME = 2
DEFAULT_SESSION_TIMEOUT_ENABLED = True


DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1L-BfSp_qJdXepvxI7A2zooE9lDOK-H_YDnDwg74BuP8/edit?gid=0#gid=0"
)


DEFAULT_GOOGLE_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbwVpM8c0NR1Dw3HcErG03YsIYnnW0myXpO1So5QHeI_vj_jxCmU36sXDI6C40w136RRRQ/"
    "exec"
)

QR_BASE_URL = (
    "https://rfid-rickshaw-system.web.app/"
    "rickshaw.html?token="
)


# ============================================================
# SETTINGS
# ============================================================

def save_settings(settings):

    try:
        os.makedirs(
            os.path.dirname(SETTINGS_FILE),
            exist_ok=True
        )

        with open(
            SETTINGS_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                settings,
                f,
                indent=4
            )

    except Exception as e:

        print(
            "[SETTINGS SAVE ERROR]",
            e
        )


def load_settings():

    defaults = {
        "session_timeout":
            DEFAULT_SESSION_TIME,

        "session_timeout_enabled":
            DEFAULT_SESSION_TIMEOUT_ENABLED,

        "popup_timeout":
            DEFAULT_POPUP_TIME,

        "google_sheets_enabled":
            True,

        "google_sheets_url":
            DEFAULT_GOOGLE_URL,

        "google_sheet_view_url":
            DEFAULT_SHEET_URL
    }

    if not os.path.exists(
        SETTINGS_FILE
    ):

        save_settings(
            defaults
        )

        return defaults

    try:

        with open(
            SETTINGS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            settings = json.load(f)

        if not isinstance(
            settings,
            dict
        ):

            settings = {}

        for key, value in defaults.items():

            if key not in settings:

                settings[key] = value
        save_settings(
            settings
        )

        return settings

    except Exception as e:

        print(
            "[SETTINGS LOAD ERROR]",
            e
        )

        save_settings(
            defaults
        )

        return defaults


# ============================================================
# LOG
# ============================================================

def log_event(
    session_id,
    rickshaw,
    owner,
    puller,
    master_uid,
    slave_uid,
    status,
    reason="",
    event_time=None
):

    # Desktop only updates Firebase/dashboard.
    # Google Sheet upload is handled by mobile app.

    print(
        "[DESKTOP EVENT]",
        {
            "session_id": session_id,
            "rickshaw": rickshaw,
            "owner": owner,
            "puller": puller,
            "status": status,
            "reason": reason
        }
    )



# ============================================================
# RFID INPUT
# ============================================================

class RFIDInput(QLineEdit):

    def __init__(
        self,
        parent=None
    ):

        super().__init__(
            parent
        )

        self.main_window = parent

        self.timer = QTimer(
            self
        )

        self.timer.setSingleShot(
            True
        )

        self.timer.timeout.connect(
            self.finish_scan
        )

        self.setPlaceholderText(
            "RFID scanner ready..."
        )

    def keyPressEvent(
        self,
        event
    ):

        if event.key() in (
            Qt.Key_Return,
            Qt.Key_Enter
        ):

            self.finish_scan()

            event.accept()

            return

        if event.text():

            super().keyPressEvent(
                event
            )

            self.timer.start(
                350
            )

            return

        super().keyPressEvent(
            event
        )

    def finish_scan(self):

        uid = self.text().strip().upper()

        if not uid:

            return

        self.clear()

        self.timer.stop()

        if self.main_window:

            self.main_window.process_rfid(
                uid
            )

        self.setFocus()


# ============================================================
# OWNER DIALOG
# ============================================================

class OwnerDialog(QDialog):

    def __init__(
        self,
        parent=None,
        owner_data=None
    ):

        super().__init__(
            parent
        )

        self.owner_data = owner_data

        self.setWindowTitle(
            "Edit Rickshaw Owner"
            if self.owner_data
            else "Add Rickshaw Owner"
        )

        self.setFixedSize(
            500,
            500
        )

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "EDIT OWNER"
            if self.owner_data
            else "ADD OWNER"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        self.name = QLineEdit()

        self.name.setPlaceholderText(
            "Owner name"
        )

        layout.addWidget(
            QLabel("Owner Name")
        )

        layout.addWidget(
            self.name
        )

        self.owner_id = QLineEdit()

        self.owner_id.setPlaceholderText(
            "Owner ID"
        )

        layout.addWidget(
            QLabel("Owner ID")
        )

        layout.addWidget(
            self.owner_id
        )

        self.phone = QLineEdit()

        self.phone.setPlaceholderText(
            "Phone"
        )

        layout.addWidget(
            QLabel("Phone")
        )

        layout.addWidget(
            self.phone
        )

        self.garage = QLineEdit()

        self.garage.setPlaceholderText(
            "Garage name"
        )

        layout.addWidget(
            QLabel("Garage")
        )

        layout.addWidget(
            self.garage
        )

        self.garage_location = QLineEdit()

        self.garage_location.setPlaceholderText(
            "Garage location"
        )

        layout.addWidget(
            QLabel("Garage Location")
        )

        layout.addWidget(
            self.garage_location
        )

        self.master_uid = QLineEdit()

        self.master_uid.setPlaceholderText(
            "Scan/type Master RFID UID"
        )

        layout.addWidget(
            QLabel("Master RFID")
        )

        layout.addWidget(
            self.master_uid
        )

        save = QPushButton(
            "UPDATE OWNER"
            if self.owner_data
            else "SAVE OWNER"
        )

        save.setObjectName(
            "primary_button"
        )

        save.clicked.connect(
            self.save
        )

        layout.addWidget(
            save
        )

        if self.owner_data:

            self.name.setText(
                str(self.owner_data.get("name") or "")
            )

            self.owner_id.setText(
                str(self.owner_data.get("owner_id") or "")
            )

            self.phone.setText(
                str(self.owner_data.get("phone") or "")
            )

            self.garage.setText(
                str(self.owner_data.get("garage_name") or "")
            )

            self.garage_location.setText(
                str(self.owner_data.get("garage_location") or "")
            )

            self.master_uid.setText(
                str(self.owner_data.get("master_uid") or "")
            )

    def save(self):

        if not self.name.text().strip():

            QMessageBox.warning(
                self,
                "Error",
                "Enter owner name."
            )

            return

        if not self.master_uid.text().strip():

            QMessageBox.warning(
                self,
                "Error",
                "Enter Master RFID UID."
            )

            return

        if self.owner_data:

            ok, message = database.update_owner(
                self.owner_data["id"],
                self.name.text().strip(),
                self.owner_id.text().strip(),
                self.phone.text().strip(),
                self.garage.text().strip(),
                self.master_uid.text().strip().upper(),
                self.garage_location.text().strip()
            )

        else:

            ok, message = database.add_owner(
                self.name.text().strip(),
                self.owner_id.text().strip(),
                self.phone.text().strip(),
                self.garage.text().strip(),
                self.master_uid.text().strip().upper(),
                self.garage_location.text().strip()
            )

        if ok:

            try:
                if self.parent() and hasattr(
                    self.parent(),
                    "main_window"
                ):
                    self.parent().main_window.sync_master_data()

            except Exception as e:
                print(
                    "[OWNER FIREBASE SYNC ERROR]",
                    e
                )

            QMessageBox.information(
                self,
                "Saved",
                message
            )

            self.accept()

        else:

            QMessageBox.warning(
                self,
                "Error",
                message
            )

# ============================================================
# OWNER MOBILE LOGIN DIALOG
# ============================================================

class MobileLoginDialog(QDialog):

    operation_finished = Signal(object)

    def __init__(
        self,
        owner_data,
        parent=None
    ):

        super().__init__(parent)

        self.owner_data = dict(owner_data or {})
        self.current_account = None
        self.busy = False

        self.setWindowTitle("Owner Mobile App Login")
        self.setFixedSize(600, 540)

        layout = QVBoxLayout(self)

        title = QLabel("MOBILE APP LOGIN")
        title.setObjectName("title")
        layout.addWidget(title)

        owner_name = str(self.owner_data.get("name") or "")
        owner_code = str(self.owner_data.get("owner_id") or "")
        owner_db_id = str(self.owner_data.get("id") or "")

        identity = QLabel(
            f"Owner: {owner_name}\n"
            f"Owner ID: {owner_code or '---'}   |   "
            f"Database ID: {owner_db_id}"
        )
        identity.setObjectName("large_text")
        identity.setWordWrap(True)
        layout.addWidget(identity)

        account_box = QGroupBox("FIREBASE AUTHENTICATION")
        account_layout = QVBoxLayout(account_box)

        self.status_label = QLabel("Status: checking...")
        self.status_label.setWordWrap(True)
        account_layout.addWidget(self.status_label)

        account_layout.addWidget(QLabel("Login Email"))
        self.email = QLineEdit()
        self.email.setPlaceholderText("owner@example.com")
        self.email.setText(
            str(self.owner_data.get("mobile_email") or "")
        )
        account_layout.addWidget(self.email)

        account_layout.addWidget(QLabel("Password / New Password"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText(
            "At least 6 characters (leave blank to keep existing password)"
        )
        account_layout.addWidget(self.password)

        self.show_password = QCheckBox("Show password")
        self.show_password.toggled.connect(self.toggle_password_visibility)
        account_layout.addWidget(self.show_password)

        security_note = QLabel(
            "The password is sent directly to Firebase Authentication. "
            "It is never saved in SQLite or Realtime Database."
        )
        security_note.setWordWrap(True)
        account_layout.addWidget(security_note)

        layout.addWidget(account_box)

        self.save_button = QPushButton("CREATE / UPDATE LOGIN")
        self.save_button.setObjectName("primary_button")
        self.save_button.clicked.connect(self.save_login)
        layout.addWidget(self.save_button)

        action_row = QHBoxLayout()

        self.password_button = QPushButton("SET NEW PASSWORD")
        self.password_button.clicked.connect(self.set_new_password)
        action_row.addWidget(self.password_button)

        self.access_button = QPushButton("DISABLE ACCESS")
        self.access_button.setObjectName("danger_button")
        self.access_button.clicked.connect(self.toggle_access)
        action_row.addWidget(self.access_button)

        layout.addLayout(action_row)

        bottom_row = QHBoxLayout()

        self.refresh_button = QPushButton("REFRESH STATUS")
        self.refresh_button.clicked.connect(self.refresh_status)
        bottom_row.addWidget(self.refresh_button)

        bottom_row.addStretch()

        close_button = QPushButton("CLOSE")
        close_button.clicked.connect(self.accept)
        bottom_row.addWidget(close_button)

        layout.addLayout(bottom_row)

        self.operation_finished.connect(self.on_operation_finished)

        QTimer.singleShot(100, self.refresh_status)

    def toggle_password_visibility(self, checked):

        self.password.setEchoMode(
            QLineEdit.Normal
            if checked
            else QLineEdit.Password
        )

    def set_busy(self, busy, message=""):

        self.busy = bool(busy)

        for widget in (
            self.save_button,
            self.password_button,
            self.access_button,
            self.refresh_button,
            self.email,
            self.password
        ):
            widget.setEnabled(not self.busy)

        if self.busy:
            self.status_label.setText(
                "Status: " + (message or "Contacting Firebase...")
            )

    def _known_uid(self):
        if isinstance(self.current_account, dict):
            uid = self.current_account.get("uid")
            if uid:
                return str(uid)
        return str(self.owner_data.get("firebase_uid") or "")

    def _known_email(self):
        value = self.email.text().strip().lower()
        if value:
            return value
        if isinstance(self.current_account, dict):
            value = str(
                self.current_account.get("email") or ""
            ).strip().lower()
            if value:
                return value
        return str(
            self.owner_data.get("mobile_email") or ""
        ).strip().lower()

    def run_operation(self, action, message, function):

        if self.busy:
            return

        self.set_busy(True, message)

        def worker():
            try:
                account = function()
                result = {
                    "ok": True,
                    "action": action,
                    "account": account
                }
            except Exception as e:
                result = {
                    "ok": False,
                    "action": action,
                    "error": str(e)
                }

            self.operation_finished.emit(result)

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def refresh_status(self):

        owner_id = self.owner_data.get("id")
        known_uid = self._known_uid()
        known_email = self._known_email()

        self.run_operation(
            "refresh",
            "Checking Firebase login...",
            lambda: firebase_service.get_owner_mobile_account(
                owner_id,
                known_uid=known_uid,
                known_email=known_email
            )
        )

    def save_login(self):

        email = self.email.text().strip().lower()
        password = self.password.text()

        if not email:
            QMessageBox.warning(
                self,
                "Email Required",
                "Enter the owner's mobile login email."
            )
            return

        if password and len(password) < 6:
            QMessageBox.warning(
                self,
                "Password",
                "Password must contain at least 6 characters."
            )
            return

        owner = dict(self.owner_data)
        known_uid = self._known_uid()
        known_email = str(
            self.owner_data.get("mobile_email")
            or (self.current_account or {}).get("email")
            or ""
        ).strip().lower()

        self.run_operation(
            "save",
            "Creating/updating Firebase login...",
            lambda: firebase_service.create_or_update_owner_mobile_account(
                owner,
                email,
                password=password,
                known_uid=known_uid,
                known_email=known_email
            )
        )

    def set_new_password(self):

        password = self.password.text()

        if len(password) < 6:
            QMessageBox.warning(
                self,
                "Password",
                "Enter a new password containing at least 6 characters."
            )
            return

        owner_id = self.owner_data.get("id")
        known_uid = self._known_uid()
        known_email = self._known_email()

        self.run_operation(
            "password",
            "Changing Firebase password...",
            lambda: firebase_service.set_owner_mobile_password(
                owner_id,
                password,
                known_uid=known_uid,
                known_email=known_email
            )
        )

    def toggle_access(self):

        if (
            not isinstance(self.current_account, dict)
            or not self.current_account.get("found")
        ):
            QMessageBox.warning(
                self,
                "Mobile Login",
                "Create or link a mobile login first."
            )
            return

        new_enabled = not bool(
            self.current_account.get("enabled")
        )
        owner_id = self.owner_data.get("id")
        known_uid = self._known_uid()
        known_email = self._known_email()

        self.run_operation(
            "enable" if new_enabled else "disable",
            (
                "Enabling mobile access..."
                if new_enabled
                else "Disabling mobile access..."
            ),
            lambda: firebase_service.set_owner_mobile_enabled(
                owner_id,
                new_enabled,
                known_uid=known_uid,
                known_email=known_email
            )
        )

    def render_account(self, account):

        self.current_account = dict(account or {})

        if self.current_account.get("found"):
            self.password_button.setEnabled(True)
            self.access_button.setEnabled(True)
            email = str(
                self.current_account.get("email") or ""
            )
            uid = str(
                self.current_account.get("uid") or ""
            )
            enabled = bool(
                self.current_account.get("enabled")
            )

            if email:
                self.email.setText(email)

            status_text = "ENABLED" if enabled else "DISABLED"
            self.status_label.setText(
                f"Status: {status_text}\nFirebase UID: {uid}"
            )

            duplicate_count = int(
                self.current_account.get("duplicate_count") or 0
            )
            if duplicate_count:
                self.status_label.setText(
                    self.status_label.text()
                    + f"\nWarning: {duplicate_count} extra login mapping(s) "
                      "were found for this owner."
                )

            self.access_button.setText(
                "DISABLE ACCESS"
                if enabled
                else "ENABLE ACCESS"
            )
            self.access_button.setObjectName(
                "danger_button"
                if enabled
                else "primary_button"
            )

        elif self.current_account.get("stale_mapping"):
            self.password_button.setEnabled(False)
            self.access_button.setEnabled(False)
            self.status_label.setText(
                "Status: BROKEN LINK\n"
                "Realtime Database contains a mobile-access mapping, but "
                "the Firebase Authentication user no longer exists. "
                "Create/update the login to repair it."
            )
            stale_email = str(
                self.current_account.get("email") or ""
            )
            if stale_email and not self.email.text().strip():
                self.email.setText(stale_email)
            self.access_button.setText("DISABLE ACCESS")

        else:
            self.password_button.setEnabled(False)
            self.access_button.setEnabled(False)
            self.status_label.setText(
                "Status: NOT LINKED\n"
                "No Firebase mobile login is linked to this owner yet."
            )
            self.access_button.setText("NO LOGIN YET")

        self.access_button.style().unpolish(
            self.access_button
        )
        self.access_button.style().polish(
            self.access_button
        )

    def on_operation_finished(self, result):

        self.set_busy(False)

        if not isinstance(result, dict) or not result.get("ok"):
            error = (result or {}).get(
                "error",
                "Unknown Firebase error."
            )
            self.status_label.setText(
                "Status: ERROR\n" + str(error)
            )
            QMessageBox.warning(
                self,
                "Firebase Mobile Login",
                str(error)
            )
            return

        action = result.get("action")
        account = result.get("account") or {}

        if account.get("found"):
            database.set_owner_mobile_login(
                self.owner_data.get("id"),
                account.get("email", ""),
                account.get("uid", ""),
                bool(account.get("enabled"))
            )
        elif account.get("stale_mapping"):
            database.set_owner_mobile_login(
                self.owner_data.get("id"),
                account.get("email", ""),
                account.get("uid", ""),
                False
            )
        elif action == "refresh":
            database.set_owner_mobile_login(
                self.owner_data.get("id"),
                "",
                "",
                False
            )

        refreshed_owner = database.get_owner(
            self.owner_data.get("id")
        )
        if refreshed_owner:
            self.owner_data = dict(refreshed_owner)

        self.render_account(account)
        self.password.clear()

        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh"):
            parent.refresh()
        if parent is not None and hasattr(parent, "main_window"):
            try:
                parent.main_window.sync_master_data()
            except Exception:
                pass

        if action == "save":
            QMessageBox.information(
                self,
                "Mobile Login Saved",
                "The owner's Firebase mobile login is ready.\n\n"
                "If the phone is already signed in, sign out and sign in "
                "again if access information does not refresh immediately."
            )

        elif action == "password":
            QMessageBox.information(
                self,
                "Password Updated",
                "The Firebase Authentication password was updated successfully."
            )

        elif action == "disable":
            QMessageBox.information(
                self,
                "Mobile Access Disabled",
                "This owner's mobile login is now disabled."
            )

        elif action == "enable":
            QMessageBox.information(
                self,
                "Mobile Access Enabled",
                "This owner's mobile login is now enabled."
            )


# ============================================================
# PULLER DIALOG
# ============================================================

class PullerDialog(QDialog):

    def __init__(
        self,
        parent=None,
        puller_data=None
    ):

        super().__init__(
            parent
        )

        self.puller_data = puller_data

        self.photo_path = ""

        self.setWindowTitle(
            "Edit Rickshaw Puller"
            if self.puller_data
            else "Add Rickshaw Puller"
        )

        self.setFixedSize(
            500,
            500
        )

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "EDIT PULLER"
            if self.puller_data
            else "ADD PULLER"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        self.name = QLineEdit()

        self.name.setPlaceholderText(
            "Puller name"
        )

        layout.addWidget(
            QLabel("Puller Name")
        )

        layout.addWidget(
            self.name
        )

        self.puller_id = QLineEdit()

        self.puller_id.setPlaceholderText(
            "Puller ID"
        )

        layout.addWidget(
            QLabel("Puller ID")
        )

        layout.addWidget(
            self.puller_id
        )

        self.phone = QLineEdit()

        self.phone.setPlaceholderText(
            "Phone"
        )

        layout.addWidget(
            QLabel("Phone")
        )

        layout.addWidget(
            self.phone
        )

        self.slave_uid = QLineEdit()

        self.slave_uid.setPlaceholderText(
            "Slave RFID UID"
        )

        layout.addWidget(
            QLabel("Slave RFID")
        )

        layout.addWidget(
            self.slave_uid
        )

        photo_button = QPushButton(
            "SELECT PHOTO"
        )

        photo_button.clicked.connect(
            self.select_photo
        )

        layout.addWidget(
            photo_button
        )

        self.photo_label = QLabel(
            "No photo selected"
        )

        layout.addWidget(
            self.photo_label
        )

        save = QPushButton(
            "UPDATE PULLER"
            if self.puller_data
            else "SAVE PULLER"
        )

        save.setObjectName(
            "primary_button"
        )

        save.clicked.connect(
            self.save
        )

        layout.addWidget(
            save
        )

        if self.puller_data:

            self.name.setText(
                str(self.puller_data.get("name") or "")
            )

            self.puller_id.setText(
                str(self.puller_data.get("puller_id") or "")
            )

            self.phone.setText(
                str(self.puller_data.get("phone") or "")
            )

            self.slave_uid.setText(
                str(self.puller_data.get("slave_uid") or "")
            )

            existing_photo = self.puller_data.get(
                "photo_path"
            )

            if existing_photo:

                self.photo_label.setText(
                    os.path.basename(existing_photo)
                    + " (current photo, select to replace)"
                )

    def select_photo(self):

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Puller Photo",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )

        if not filename:

            return

        self.photo_path = filename

        self.photo_label.setText(
            os.path.basename(filename)
        )

    def save(self):

        if not self.name.text().strip():

            QMessageBox.warning(
                self,
                "Error",
                "Enter puller name."
            )

            return

        if not self.slave_uid.text().strip():

            QMessageBox.warning(
                self,
                "Error",
                "Enter Slave RFID UID."
            )

            return

        final_photo = ""

        if self.photo_path:

            extension = os.path.splitext(
                self.photo_path
            )[1]

            safe_name = (
                self.slave_uid.text()
                .strip()
                .upper()
                .replace(":", "_")
            )

            final_photo = os.path.join(
                PHOTOS_DIR,
                safe_name + extension
            )

            try:

                with open(
                    self.photo_path,
                    "rb"
                ) as source:

                    with open(
                        final_photo,
                        "wb"
                    ) as destination:

                        destination.write(
                            source.read()
                        )

            except Exception as e:

                QMessageBox.warning(
                    self,
                    "Photo Error",
                    str(e)
                )

                return

        if self.puller_data:

            ok, message = database.update_puller(
                self.puller_data["id"],
                self.name.text().strip(),
                self.puller_id.text().strip(),
                self.phone.text().strip(),
                final_photo,
                self.slave_uid.text().strip().upper()
            )

        else:

            ok, message = database.add_puller(
                self.name.text().strip(),
                self.puller_id.text().strip(),
                self.phone.text().strip(),
                final_photo,
                self.slave_uid.text().strip().upper()
            )

        if ok:

            QMessageBox.information(
                self,
                "Saved",
                message
            )

            self.accept()

        else:

            QMessageBox.warning(
                self,
                "Error",
                message
            )


# ============================================================
# RICKSHAW DIALOG
# ============================================================

class RickshawDialog(QDialog):

    def __init__(
        self,
        parent=None,
        rickshaw_data=None
    ):

        super().__init__(
            parent
        )

        self.rickshaw_data = rickshaw_data

        self.setWindowTitle(
            "Edit Rickshaw"
            if self.rickshaw_data
            else "Add Rickshaw"
        )

        self.setFixedSize(
            500,
            420
        )

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "EDIT RICKSHAW"
            if self.rickshaw_data
            else "ADD RICKSHAW"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        self.number = QLineEdit()

        self.number.setPlaceholderText(
            "Rickshaw 001"
        )

        layout.addWidget(
            QLabel("Rickshaw Number")
        )

        layout.addWidget(
            self.number
        )

        self.registration = QLineEdit()

        self.registration.setPlaceholderText(
            "Registration number"
        )

        layout.addWidget(
            QLabel("Registration Number")
        )

        layout.addWidget(
            self.registration
        )

        self.garage = QLineEdit()

        self.garage.setPlaceholderText(
            "Garage name"
        )

        layout.addWidget(
            QLabel("Garage")
        )

        layout.addWidget(
            self.garage
        )

        self.owner_combo = QComboBox()

        self.owner_combo.addItem(
            "None (no owner)",
            None
        )

        owners = database.get_all_owners()

        for owner in owners:

            self.owner_combo.addItem(
                (
                    f"{owner['name']} "
                    f"({owner['owner_id'] or 'No ID'})"
                ),
                owner["id"]
            )

        layout.addWidget(
            QLabel("Owner")
        )

        layout.addWidget(
            self.owner_combo
        )

        save = QPushButton(
            "UPDATE RICKSHAW"
            if self.rickshaw_data
            else "SAVE RICKSHAW"
        )

        save.setObjectName(
            "primary_button"
        )

        save.clicked.connect(
            self.save
        )

        layout.addWidget(
            save
        )

        if self.rickshaw_data:

            self.number.setText(
                str(self.rickshaw_data.get("rickshaw_number") or "")
            )

            self.registration.setText(
                str(self.rickshaw_data.get("registration_number") or "")
            )

            self.garage.setText(
                str(self.rickshaw_data.get("garage_name") or "")
            )

            current_owner_id = self.rickshaw_data.get("owner_id")

            index = self.owner_combo.findData(
                current_owner_id
            )

            if index >= 0:

                self.owner_combo.setCurrentIndex(
                    index
                )

    def save(self):

        if not self.number.text().strip():

            QMessageBox.warning(
                self,
                "Error",
                "Enter rickshaw number."
            )

            return

        if self.rickshaw_data:

            ok, message = database.update_rickshaw(
                self.rickshaw_data["id"],
                self.number.text().strip(),
                self.registration.text().strip(),
                self.garage.text().strip(),
                self.owner_combo.currentData(),
            )

        else:

            ok, message = database.add_rickshaw(
                self.number.text().strip(),
                self.registration.text().strip(),
                self.garage.text().strip(),
                self.owner_combo.currentData()
            )

        if ok:
            try:
                self.parent().main_window.sync_master_data()
            except Exception as e:
                print("[RICKSHAW SYNC ERROR]", e)

            QMessageBox.information(
                self,
                "Saved",
                message
            )

            self.accept()

        else:

            QMessageBox.warning(
                self,
                "Error",
                message
            )


# ============================================================
# RICKSHAW SELECT DIALOG
# ============================================================

class RickshawSelectDialog(QDialog):

    def __init__(
        self,
        owner,
        parent=None
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "Select Rickshaw"
        )

        self.setFixedSize(
            520,
            330
        )

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "SELECT RICKSHAW"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        owner_label = QLabel(
            f"Owner: {owner['name']}"
        )

        owner_label.setObjectName(
            "large_text"
        )

        layout.addWidget(
            owner_label
        )

        self.combo = QComboBox()

        rickshaws = database.get_rickshaws_by_owner(
            owner["id"]
        )

        for rickshaw in rickshaws:

            self.combo.addItem(
                (
                    f"{rickshaw['rickshaw_number']} "
                    f"- "
                    f"{rickshaw['registration_number'] or 'No Registration'}"
                ),
                rickshaw["id"]
            )

        layout.addWidget(
            QLabel(
                "Choose the rickshaw for this event:"
            )
        )

        layout.addWidget(
            self.combo
        )

        select = QPushButton(
            "SELECT RICKSHAW"
        )

        select.setObjectName(
            "primary_button"
        )

        select.clicked.connect(
            self.accept
        )

        layout.addWidget(
            select
        )

        cancel = QPushButton(
            "CANCEL"
        )

        cancel.clicked.connect(
            self.reject
        )

        layout.addWidget(
            cancel
        )

    def get_rickshaw_id(self):

        return self.combo.currentData()


# ============================================================
# EVENT CARD
# ============================================================

class EventCard(QFrame):

    end_requested = Signal(int)

    def __init__(
        self,
        event_data,
        parent=None
    ):

        super().__init__(
            parent
        )

        self.event_data = event_data

        self.setObjectName(
            "event_card"
        )

        layout = QVBoxLayout(
            self
        )

        header = QHBoxLayout()

        title = QLabel(
            f"EVENT #{event_data['session_id']}"
        )

        title.setObjectName(
            "event_title"
        )

        header.addWidget(
            title
        )

        header.addStretch()

        status = QLabel(
            "● ACTIVE"
        )

        status.setObjectName(
            "event_active"
        )

        header.addWidget(
            status
        )

        layout.addLayout(
            header
        )

        info = QGridLayout()

        labels = [
            (
                "Owner",
                event_data["owner"]["name"]
            ),
            (
                "Rickshaw",
                event_data["rickshaw"]["rickshaw_number"]
            ),
            (
                "Puller",
                event_data["puller"]["name"]
            ),
            (
                "Master RFID",
                event_data["master_uid"]
            ),
            (
                "Slave RFID",
                event_data["slave_uid"]
            ),
            (
                "Started",
                event_data["started_at"]
            )
        ]

        for index, (name, value) in enumerate(
            labels
        ):

            row = index // 2
            col = (index % 2) * 2

            name_label = QLabel(
                name + ":"
            )

            name_label.setObjectName(
                "event_label"
            )

            value_label = QLabel(
                str(value)
            )

            value_label.setObjectName(
                "event_value"
            )

            value_label.setWordWrap(
                True
            )

            info.addWidget(
                name_label,
                row,
                col
            )

            info.addWidget(
                value_label,
                row,
                col + 1
            )

        layout.addLayout(
            info
        )

        self.time_label = QLabel(
            "Time remaining: --"
        )

        self.time_label.setObjectName(
            "event_time"
        )

        layout.addWidget(
            self.time_label
        )

        self.end_button = QPushButton(
            "END RICKSHAW SESSION"
        )

        self.end_button.setObjectName(
            "danger_button"
        )

        self.end_button.clicked.connect(
            lambda: self.end_requested.emit(
                self.event_data["session_id"]
            )
        )

        layout.addWidget(
            self.end_button
        )

    def update_time(
        self,
        remaining,
        timeout_enabled
    ):

        if not timeout_enabled:

            self.time_label.setText(
                "Time remaining: UNLIMITED"
            )

            return

        if remaining <= 0:

            self.time_label.setText(
                "Time remaining: EXPIRED"
            )

            return

        minutes = int(
            remaining // 60
        )

        seconds = int(
            remaining % 60
        )

        self.time_label.setText(
            f"Time remaining: "
            f"{minutes:02d}:{seconds:02d}"
        )


# ============================================================
# DASHBOARD
# ============================================================

class Dashboard(QWidget):

    def __init__(
        self,
        main_window
    ):

        super().__init__()

        self.main_window = main_window

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "RICKSHAW RFID CONTROL"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        scanner_box = QGroupBox(
            "RFID SCANNER"
        )

        scanner_layout = QVBoxLayout(
            scanner_box
        )

        self.scanner_instruction = QLabel(
            "SCAN MASTER RFID"
        )

        self.scanner_instruction.setObjectName(
            "scanner_instruction"
        )

        self.scanner_instruction.setAlignment(
            Qt.AlignCenter
        )

        scanner_layout.addWidget(
            self.scanner_instruction
        )

        self.rfid_input = RFIDInput(
            main_window
        )

        self.rfid_input.setMinimumHeight(
            55
        )

        scanner_layout.addWidget(
            self.rfid_input
        )

        self.scanner_state = QLabel(
            "Ready for Owner Master card"
        )

        self.scanner_state.setObjectName(
            "scanner_state"
        )

        self.scanner_state.setAlignment(
            Qt.AlignCenter
        )

        scanner_layout.addWidget(
            self.scanner_state
        )

        layout.addWidget(
            scanner_box
        )

        self.event_count = QLabel(
            "ACTIVE EVENTS: 0"
        )

        self.event_count.setObjectName(
            "event_count"
        )

        self.event_count.setAlignment(
            Qt.AlignCenter
        )

        layout.addWidget(
            self.event_count
        )

        assignment_box = QGroupBox(
            "CURRENT ASSIGNMENTS"
        )

        assignment_layout = QVBoxLayout(
            assignment_box
        )

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setFrameShape(
            QFrame.NoFrame
        )

        self.events_container = QWidget()

        self.events_layout = QVBoxLayout(
            self.events_container
        )

        self.events_layout.setAlignment(
            Qt.AlignTop
        )

        self.scroll.setWidget(
            self.events_container
        )

        assignment_layout.addWidget(
            self.scroll
        )

        layout.addWidget(
            assignment_box,
            1
        )

    def set_scan_master_state(self):

        self.scanner_instruction.setText(
            "SCAN MASTER RFID"
        )

        self.scanner_state.setText(
            "Ready for Owner Master card"
        )

        self.rfid_input.setPlaceholderText(
            "Scan Master RFID..."
        )

        self.rfid_input.setFocus()

    def set_scan_slave_state(
        self,
        owner,
        rickshaw
    ):

        self.scanner_instruction.setText(
            "SCAN SLAVE RFID"
        )

        self.scanner_state.setText(
            (
                f"Owner: {owner['name']}   |   "
                f"Rickshaw: "
                f"{rickshaw['rickshaw_number']}"
            )
        )

        self.rfid_input.setPlaceholderText(
            "Scan Puller Slave RFID..."
        )

        self.rfid_input.setFocus()

    def refresh_events(self):

        while self.events_layout.count():

            item = self.events_layout.takeAt(
                0
            )

            widget = item.widget()

            if widget:

                widget.deleteLater()

        active_events = (
            self.main_window.active_events
        )

        self.event_count.setText(
            f"ACTIVE EVENTS: "
            f"{len(active_events)}"
        )

        if not active_events:

            empty = QLabel(
                "No active events.\n\n"
                "Scan a Master RFID to create an event."
            )

            empty.setObjectName(
                "empty_events"
            )

            empty.setAlignment(
                Qt.AlignCenter
            )

            self.events_layout.addWidget(
                empty
            )

            return

        for session_id in sorted(
            active_events.keys(),
            reverse=True
        ):

            event_data = active_events[
                session_id
            ]

            card = EventCard(
                event_data
            )

            card.end_requested.connect(
                self.main_window.end_event
            )

            self.events_layout.addWidget(
                card
            )

            event_data["card"] = card

    def update_event_timers(self):

        now = datetime.now()

        for session_id in list(
            self.main_window.active_events.keys()
        ):

            event_data = (
                self.main_window.active_events[
                    session_id
                ]
            )

            started_at = event_data[
                "started_datetime"
            ]

            elapsed = (
                now - started_at
            ).total_seconds()

            remaining = (
                self.main_window.session_timeout
                - elapsed
            )

            card = event_data.get(
                "card"
            )

            if card:

                card.update_time(
                    remaining,
                    self.main_window.session_timeout_enabled
                )


# ============================================================
# OWNERS PAGE
# ============================================================

class OwnersPage(QWidget):

    def __init__(
        self,
        main_window
    ):

        super().__init__()

        self.main_window = main_window

        layout = QVBoxLayout(
            self
        )

        header = QHBoxLayout()

        title = QLabel(
            "OWNERS"
        )

        title.setObjectName(
            "title"
        )

        add = QPushButton(
            "+ ADD OWNER"
        )

        add.setObjectName(
            "primary_button"
        )

        add.clicked.connect(
            self.add_owner
        )

        header.addWidget(
            title
        )

        header.addStretch()

        header.addWidget(
            add
        )

        layout.addLayout(
            header
        )

        self.table = QTableWidget()

        self.table.setColumnCount(
            11
        )

        self.table.setHorizontalHeaderLabels([
            "ID",
            "OWNER",
            "OWNER ID",
            "PHONE",
            "GARAGE",
            "GARAGE LOCATION",
            "MASTER RFID",
            "MOBILE EMAIL",
            "MOBILE ACCESS",
            "EDIT",
            "DELETE"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        layout.addWidget(
            self.table
        )

        self.refresh()

    def add_owner(self):

        dialog = OwnerDialog(
            self
        )

        if dialog.exec() == QDialog.Accepted:

            self.refresh()

            self.main_window.rickshaws_page.refresh()
            self.main_window.sync_master_data()

    def edit_owner(
        self,
        owner
    ):

        dialog = OwnerDialog(
            self,
            owner_data=owner
        )

        if dialog.exec() == QDialog.Accepted:

            self.refresh()

            self.main_window.rickshaws_page.refresh()
            self.main_window.sync_master_data()

    def manage_mobile_login(
        self,
        owner
    ):

        latest = database.get_owner(
            owner.get("id")
        )

        dialog = MobileLoginDialog(
            latest or owner,
            self
        )

        dialog.exec()

        self.refresh()
        self.main_window.sync_master_data()

    def delete_owner(
        self,
        owner
    ):

        owner_id = owner.get("id")
        owner_name = owner.get("name") or ""

        answer = QMessageBox.question(
            self,
            "Delete Owner",
            (
                f"Delete owner '{owner_name}'?\n\n"
                "The owner will be removed from the active "
                "owner list. Historical events will remain.\n\n"
                "Any linked mobile login will also be disabled."
            ),
            QMessageBox.Yes | QMessageBox.No
        )

        if answer != QMessageBox.Yes:

            return

        known_uid = str(owner.get("firebase_uid") or "")
        known_email = str(owner.get("mobile_email") or "")

        database.delete_owner(
            owner_id
        )

        def disable_mobile_login():
            try:
                firebase_service.set_owner_mobile_enabled(
                    owner_id,
                    False,
                    known_uid=known_uid,
                    known_email=known_email
                )
                print(
                    "[OWNER DELETE] Mobile login disabled for owner",
                    owner_id
                )
            except Exception as e:
                print(
                    "[OWNER DELETE MOBILE LOGIN WARNING]",
                    repr(e)
                )

        threading.Thread(
            target=disable_mobile_login,
            daemon=True
        ).start()

        self.refresh()

        self.main_window.rickshaws_page.refresh()
        self.main_window.sync_master_data()

        QMessageBox.information(
            self,
            "Deleted",
            "Owner deleted successfully."
        )

    def refresh(self):

        owners = database.get_all_owners()

        self.table.setRowCount(
            len(owners)
        )

        for row, owner in enumerate(
            owners
        ):

            values = [
                owner["id"],
                owner["name"],
                owner["owner_id"],
                owner["phone"],
                owner["garage_name"],
                owner["garage_location"],
                owner["master_uid"],
                owner.get("mobile_email", "")
            ]

            for col, value in enumerate(
                values
            ):

                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(
                        str(value or "")
                    )
                )

            mobile_button = QPushButton()

            has_mobile_identity = bool(
                owner.get("firebase_uid")
                or owner.get("mobile_email")
            )
            mobile_enabled = bool(
                owner.get("mobile_login_enabled")
            )

            if has_mobile_identity and mobile_enabled:
                mobile_button.setText(
                    "MANAGE - ENABLED"
                )
                mobile_button.setObjectName(
                    "primary_button"
                )
            elif has_mobile_identity:
                mobile_button.setText(
                    "MANAGE - DISABLED"
                )
            else:
                mobile_button.setText(
                    "SET LOGIN"
                )

            mobile_button.clicked.connect(
                lambda checked=False,
                data=dict(owner):
                self.manage_mobile_login(
                    data
                )
            )

            self.table.setCellWidget(
                row,
                8,
                mobile_button
            )

            edit_button = QPushButton(
                "EDIT"
            )

            edit_button.clicked.connect(
                lambda checked=False,
                data=dict(owner):
                self.edit_owner(
                    data
                )
            )

            self.table.setCellWidget(
                row,
                9,
                edit_button
            )

            delete_button = QPushButton(
                "DELETE"
            )

            delete_button.setObjectName(
                "danger_button"
            )

            delete_button.clicked.connect(
                lambda checked=False,
                data=dict(owner):
                self.delete_owner(
                    data
                )
            )

            self.table.setCellWidget(
                row,
                10,
                delete_button
            )


# ============================================================
# PULLERS PAGE
# ============================================================

class PullersPage(QWidget):

    def __init__(
        self,
        main_window
    ):

        super().__init__()

        self.main_window = main_window

        layout = QVBoxLayout(
            self
        )

        header = QHBoxLayout()

        title = QLabel(
            "PULLERS"
        )

        title.setObjectName(
            "title"
        )

        add = QPushButton(
            "+ ADD PULLER"
        )

        add.setObjectName(
            "primary_button"
        )

        add.clicked.connect(
            self.add_puller
        )

        header.addWidget(
            title
        )

        header.addStretch()

        header.addWidget(
            add
        )

        layout.addLayout(
            header
        )

        self.table = QTableWidget()

        self.table.setColumnCount(
            8
        )

        self.table.setHorizontalHeaderLabels([
            "ID",
            "NAME",
            "PULLER ID",
            "PHONE",
            "SLAVE RFID",
            "PHOTO",
            "EDIT",
            "DELETE"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        layout.addWidget(
            self.table
        )

        self.refresh()

    def add_puller(self):

        dialog = PullerDialog(
            self
        )

        if dialog.exec() == QDialog.Accepted:

            self.refresh()
            self.main_window.sync_master_data()

    def edit_puller(
        self,
        puller
    ):

        dialog = PullerDialog(
            self,
            puller_data=puller
        )

        if dialog.exec() == QDialog.Accepted:

            self.refresh()
            self.main_window.sync_master_data()

    def delete_puller(
        self,
        puller_id,
        puller_name
    ):

        answer = QMessageBox.question(
            self,
            "Delete Puller",
            (
                f"Delete puller '{puller_name}'?\n\n"
                "The puller will be removed from the active "
                "puller list. Historical events will remain."
            ),
            QMessageBox.Yes | QMessageBox.No
        )

        if answer != QMessageBox.Yes:

            return

        database.delete_puller(
            puller_id
        )

        self.refresh()
        self.main_window.sync_master_data()

        QMessageBox.information(
            self,
            "Deleted",
            "Puller deleted successfully."
        )

    def refresh(self):

        pullers = database.get_all_pullers()

        self.table.setRowCount(
            len(pullers)
        )

        for row, puller in enumerate(
            pullers
        ):

            values = [
                puller["id"],
                puller["name"],
                puller["puller_id"],
                puller["phone"],
                puller["slave_uid"],
                (
                    os.path.basename(
                        puller["photo_path"]
                    )
                    if puller["photo_path"]
                    else ""
                )
            ]

            for col, value in enumerate(
                values
            ):

                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(
                        str(value or "")
                    )
                )

            edit_button = QPushButton(
                "EDIT"
            )

            edit_button.clicked.connect(
                lambda checked=False,
                data=dict(puller):
                self.edit_puller(
                    data
                )
            )

            self.table.setCellWidget(
                row,
                6,
                edit_button
            )

            delete_button = QPushButton(
                "DELETE"
            )

            delete_button.setObjectName(
                "danger_button"
            )

            delete_button.clicked.connect(
                lambda checked=False,
                pid=puller["id"],
                name=puller["name"]:
                self.delete_puller(
                    pid,
                    name
                )
            )

            self.table.setCellWidget(
                row,
                7,
                delete_button
            )


# ============================================================
# RICKSHAWS PAGE
# ============================================================

class RickshawsPage(QWidget):

    def __init__(
        self,
        main_window
    ):

        super().__init__()

        self.main_window = main_window

        layout = QVBoxLayout(
            self
        )

        header = QHBoxLayout()

        title = QLabel(
            "RICKSHAWS"
        )

        title.setObjectName(
            "title"
        )

        add = QPushButton(
            "+ ADD RICKSHAW"
        )

        add.setObjectName(
            "primary_button"
        )

        add.clicked.connect(
            self.add_rickshaw
        )

        header.addWidget(
            title
        )

        header.addStretch()

        header.addWidget(
            add
        )

        layout.addLayout(
            header
        )

        self.table = QTableWidget()

        self.table.setColumnCount(
            9
        )

        self.table.setHorizontalHeaderLabels([
            "ID",
            "RICKSHAW",
            "REGISTRATION",
            "GARAGE",
            "OWNER",
            "QR LINK",
            "OPEN QR",
            "EDIT",
            "DELETE"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        layout.addWidget(
            self.table
        )

        self.refresh()

    def add_rickshaw(self):

        dialog = RickshawDialog(
            self
        )

        if dialog.exec() == QDialog.Accepted:

            self.refresh()
            self.main_window.sync_master_data()

    def edit_rickshaw(
        self,
        rickshaw_id
    ):

        rickshaw = database.get_rickshaw(
            rickshaw_id
        )

        if not rickshaw:

            QMessageBox.warning(
                self,
                "Error",
                "Rickshaw not found."
            )

            return

        dialog = RickshawDialog(
            self,
            rickshaw_data=rickshaw
        )

        if dialog.exec() == QDialog.Accepted:

            self.refresh()
            self.main_window.sync_master_data()

    def delete_rickshaw(
        self,
        rickshaw_id,
        rickshaw_number
    ):

        answer = QMessageBox.question(
            self,
            "Delete Rickshaw",
            (
                f"Delete rickshaw '{rickshaw_number}'?\n\n"
                "The rickshaw will be removed from the active "
                "rickshaw list. Historical events will remain."
            ),
            QMessageBox.Yes | QMessageBox.No
        )

        if answer != QMessageBox.Yes:

            return

        database.delete_rickshaw(
            rickshaw_id
        )

        self.refresh()
        self.main_window.sync_master_data()

        QMessageBox.information(
            self,
            "Deleted",
            "Rickshaw deleted successfully."
        )

    def refresh(self):

        rickshaws = database.get_all_rickshaws()

        self.table.setRowCount(
            len(rickshaws)
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # QR URL is generated from the rickshaw's qr_token.
        # ----------------------------------------------------

        for row, rickshaw in enumerate(
            rickshaws
        ):

            qr_token = (
                rickshaw.get("qr_token")
                if hasattr(
                    rickshaw,
                    "get"
                )
                else None
            )

            if not qr_token:

                qr_url = "QR TOKEN NOT AVAILABLE"

            else:

                qr_url = (
                    QR_BASE_URL
                    + str(qr_token)
                )

            values = [
                rickshaw["id"],
                rickshaw["rickshaw_number"],
                rickshaw["registration_number"],
                rickshaw["garage_name"],
                rickshaw["owner_name"],
                qr_url
            ]

            for col, value in enumerate(
                values
            ):

                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(
                        str(value or "")
                    )
                )

            # ------------------------------------------------
            # OPEN QR
            # ------------------------------------------------

            open_button = QPushButton(
                "OPEN"
            )

            if qr_token:

                open_button.clicked.connect(
                    lambda checked=False,
                    url=qr_url:
                    webbrowser.open(url)
                )

            else:

                open_button.setEnabled(
                    False
                )

            self.table.setCellWidget(
                row,
                6,
                open_button
            )

            # ------------------------------------------------
            # EDIT
            # ------------------------------------------------

            edit_button = QPushButton(
                "EDIT"
            )

            edit_button.clicked.connect(
                lambda checked=False,
                rid=rickshaw["id"]:
                self.edit_rickshaw(
                    rid
                )
            )

            self.table.setCellWidget(
                row,
                7,
                edit_button
            )

            # ------------------------------------------------
            # DELETE
            # ------------------------------------------------

            delete_button = QPushButton(
                "DELETE"
            )

            delete_button.setObjectName(
                "danger_button"
            )

            delete_button.clicked.connect(
                lambda checked=False,
                rid=rickshaw["id"],
                number=rickshaw["rickshaw_number"]:
                self.delete_rickshaw(
                    rid,
                    number
                )
            )

            self.table.setCellWidget(
                row,
                8,
                delete_button
            )


# ============================================================
# EVENTS PAGE
# ============================================================

class EventsPage(QWidget):

    def __init__(
        self,
        main_window
    ):

        super().__init__()

        self.main_window = main_window

        layout = QVBoxLayout(
            self
        )

        header = QHBoxLayout()

        title = QLabel(
            "EVENT HISTORY"
        )

        title.setObjectName(
            "title"
        )

        header.addWidget(
            title
        )

        header.addStretch()

        clear = QPushButton(
            "CLEAR HISTORY"
        )

        clear.setObjectName(
            "danger_button"
        )

        clear.clicked.connect(
            self.clear_history
        )

        header.addWidget(
            clear
        )

        layout.addLayout(
            header
        )

        self.table = QTableWidget()

        self.table.setColumnCount(
            10
        )

        self.table.setHorizontalHeaderLabels([
            "TIME",
            "SESSION",
            "RICKSHAW",
            "OWNER",
            "PULLER",
            "MASTER UID",
            "SLAVE UID",
            "STATUS",
            "REASON",
            "ACTION"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        layout.addWidget(
            self.table
        )

        self.refresh()

    def clear_history(self):

        if self.main_window.active_events:

            answer = QMessageBox.question(
                self,
                "Active Events",
                (
                    "There are active events.\n\n"
                    "Clear history while keeping active "
                    "events running?"
                ),
                QMessageBox.Yes | QMessageBox.No
            )

            if answer != QMessageBox.Yes:

                return

        else:

            answer = QMessageBox.question(
                self,
                "Clear History",
                (
                    "Are you sure you want to clear "
                    "all event history?"
                ),
                QMessageBox.Yes | QMessageBox.No
            )

            if answer != QMessageBox.Yes:

                return

        database.clear_history()

        self.refresh()

        QMessageBox.information(
            self,
            "History Cleared",
            "Event history has been cleared."
        )

    def refresh(self):

        rows = database.get_transactions()

        self.table.setRowCount(
            len(rows)
        )

        for row, data in enumerate(
            rows
        ):

            values = [
                data["timestamp"],
                data["session_id"],
                data["rickshaw_number"],
                data["owner_name"],
                data["puller_name"],
                data["master_uid"],
                data["slave_uid"],
                data["status"],
                data["reason"]
            ]

            for col, value in enumerate(
                values
            ):

                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(
                        str(value or "")
                    )
                )

            action = QTableWidgetItem(
                "HISTORY"
            )

            self.table.setItem(
                row,
                9,
                action
            )


# ============================================================
# SETTINGS PAGE
# ============================================================

class SettingsPage(QWidget):

    def __init__(
        self,
        main_window
    ):

        super().__init__()

        self.main_window = main_window

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "SETTINGS"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        # ====================================================
        # MASTER SESSION
        # ====================================================

        box = QGroupBox(
            "MASTER SESSION"
        )

        session_layout = QVBoxLayout(
            box
        )

        self.session_enabled = QCheckBox(
            "Automatic Session Timeout"
        )

        self.session_enabled.setChecked(
            main_window.session_timeout_enabled
        )

        self.session_enabled.stateChanged.connect(
            self.session_enabled_changed
        )

        session_layout.addWidget(
            self.session_enabled
        )

        row = QHBoxLayout()

        self.session_spin = QSpinBox()

        self.session_spin.setRange(
            1,
            86400
        )

        self.session_spin.setValue(
            main_window.session_timeout
        )

        self.session_spin.setSuffix(
            " seconds"
        )

        row.addWidget(
            QLabel(
                "Timeout:"
            )
        )

        row.addWidget(
            self.session_spin
        )

        save = QPushButton(
            "SAVE"
        )

        save.setObjectName(
            "primary_button"
        )

        save.clicked.connect(
            self.save_session
        )

        row.addWidget(
            save
        )

        session_layout.addLayout(
            row
        )

        layout.addWidget(
            box
        )

        # ====================================================
        # POPUP
        # ====================================================

        box = QGroupBox(
            "POPUP"
        )

        row = QHBoxLayout(
            box
        )

        self.popup_spin = QSpinBox()

        self.popup_spin.setRange(
            1,
            60
        )

        self.popup_spin.setValue(
            main_window.popup_timeout
        )

        self.popup_spin.setSuffix(
            " seconds"
        )

        row.addWidget(
            QLabel(
                "Popup display time:"
            )
        )

        row.addWidget(
            self.popup_spin
        )

        save = QPushButton(
            "SAVE"
        )

        save.setObjectName(
            "primary_button"
        )

        save.clicked.connect(
            self.save_popup
        )

        row.addWidget(
            save
        )

        layout.addWidget(
            box
        )

        # ====================================================
        # GOOGLE SHEETS
        # ====================================================

        box = QGroupBox(
            "GOOGLE SHEETS"
        )

        google_layout = QVBoxLayout(
            box
        )

        self.google_enable = QCheckBox(
            "Enable Google Sheets"
        )

        self.google_enable.setChecked(
            main_window.google_enabled
        )

        google_layout.addWidget(
            self.google_enable
        )

        self.google_url = QLineEdit(
            main_window.google_url
        )

        google_layout.addWidget(
            QLabel(
                "Apps Script Web App URL"
            )
        )

        google_layout.addWidget(
            self.google_url
        )

        row = QHBoxLayout()

        test = QPushButton(
            "TEST CONNECTION"
        )

        test.clicked.connect(
            self.test_google
        )

        row.addWidget(
            test
        )

        save = QPushButton(
            "SAVE"
        )

        save.setObjectName(
            "primary_button"
        )

        save.clicked.connect(
            self.save_google
        )

        row.addWidget(
            save
        )

        google_layout.addLayout(
            row
        )

        layout.addWidget(
            box
        )

        layout.addStretch()

        self.session_enabled_changed(
            self.session_enabled.checkState()
        )

    def session_enabled_changed(
        self,
        state
    ):

        enabled = (
            state == Qt.Checked
        )

        self.session_spin.setEnabled(
            enabled
        )

    def save_session(self):

        enabled = (
            self.session_enabled.isChecked()
        )

        value = self.session_spin.value()

        self.main_window.session_timeout_enabled = (
            enabled
        )

        self.main_window.session_timeout = value

        self.main_window.settings[
            "session_timeout_enabled"
        ] = enabled

        self.main_window.settings[
            "session_timeout"
        ] = value

        save_settings(
            self.main_window.settings
        )

        QMessageBox.information(
            self,
            "Saved",
            (
                "Session settings saved.\n\n"
                +
                (
                    "Automatic timeout is ON."
                    if enabled
                    else
                    "Automatic timeout is OFF. "
                    "Events will remain active until "
                    "their END RICKSHAW SESSION button "
                    "is pressed."
                )
            )
        )

    def save_popup(self):

        value = self.popup_spin.value()

        self.main_window.popup_timeout = value

        self.main_window.settings[
            "popup_timeout"
        ] = value

        save_settings(
            self.main_window.settings
        )

        QMessageBox.information(
            self,
            "Saved",
            "Popup timeout saved."
        )
    def save_google(self):

        enabled = (
            self.google_enable.isChecked()
        )

        url = self.google_url.text().strip()

        if enabled and not url:

            QMessageBox.warning(
                self,
                "Error",
                "Enter Google Apps Script URL."
            )

            return

        self.main_window.google_enabled = enabled

        self.main_window.google_url = url

        self.main_window.settings[
            "google_sheets_enabled"
        ] = enabled

        self.main_window.settings[
            "google_sheets_url"
        ] = url

        save_settings(
            self.main_window.settings
        )


        try:
            firebase_service.update_google_sheet_url(
                url
            )
        except Exception as e:
            print(
                "[GOOGLE URL FIREBASE SYNC ERROR]",
                e
            )

        QMessageBox.information(
            self,
            "Saved",
            "Google Sheets settings saved."
        )

    def test_google(self):

        url = self.google_url.text().strip()

        if not url:

            QMessageBox.warning(
                self,
                "Error",
                "Enter URL first."
            )

            return

        try:

            response = requests.post(
                url,
                json={
                    "timestamp":
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),

                    "session_id":
                        "TEST",

                    "rickshaw":
                        "",

                    "owner":
                        "",

                    "puller":
                        "",

                    "master_uid":
                        "",

                    "slave_uid":
                        "",

                    "status":
                        "TEST",

                    "reason":
                        "CONNECTION_TEST"
                },
                timeout=30
            )

            if response.status_code == 200:

                QMessageBox.information(
                    self,
                    "Success",
                    "Google Sheets connection successful."
                )

            else:

                QMessageBox.warning(
                    self,
                    "Failed",
                    f"HTTP {response.status_code}"
                )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):

    # Firebase listener callbacks run outside the Qt GUI thread.
    # This signal safely transfers the complete cloud session snapshot
    # back to the main UI thread.
    firebase_sessions_changed = Signal(object)
    session_start_finished = Signal(object)
    session_end_finished = Signal(object)
    firebase_status_changed = Signal(str)
    google_status_changed = Signal(str)

    def __init__(
        self
    ):

        super().__init__()

        self.setWindowTitle(
            "RFID Rickshaw Management System"
        )

        self.resize(
            1450,
            900
        )

        # ----------------------------------------------------
        # DATABASE / FIREBASE
        # ----------------------------------------------------

        database.init_database()

        try:

            firebase_service.initialize_firebase()

        except Exception as e:

            print(
                "[FIREBASE INIT ERROR]",
                e
            )

        # ----------------------------------------------------
        # SETTINGS
        # ----------------------------------------------------

        self.settings = load_settings()

        self.session_timeout = int(
            self.settings[
                "session_timeout"
            ]
        )

        self.session_timeout_enabled = bool(
            self.settings.get(
                "session_timeout_enabled",
                True
            )
        )

        self.popup_timeout = int(
            self.settings[
                "popup_timeout"
            ]
        )

        self.google_enabled = bool(
            self.settings[
                "google_sheets_enabled"
            ]
        )

        self.google_url = self.settings[
            "google_sheets_url"
        ]

        # ----------------------------------------------------
        # RFID WORKFLOW
        # ----------------------------------------------------

        self.scan_mode = "MASTER"

        self.pending_owner = None

        self.pending_rickshaw = None

        self.pending_master_uid = None

        # ----------------------------------------------------
        # ACTIVE EVENTS
        # ----------------------------------------------------

        self.active_events = {}

        # ----------------------------------------------------
        # FIREBASE CLOUD SESSION SYNC
        # ----------------------------------------------------
        #
        # We intentionally do NOT rely on Firebase Admin's persistent
        # Server-Sent-Events .listen() stream on the desktop. Normal
        # authenticated RTDB reads/writes are much more reliable on Windows
        # networks and were verified by the Firebase diagnostic. A lightweight
        # background poll keeps mobile/remote sessions synchronized without
        # ever blocking the Qt GUI.

        self.firebase_listener = None  # legacy compatibility; not used
        self.firebase_poll_in_progress = False
        self.firebase_connection_ok = False
        self.google_operation_ok = True

        # Cloud events already written to Google. Prevent duplicate logs
        # when Firebase sends the same mobile session again.
     

        # ----------------------------------------------------
        # POPUPS
        # ----------------------------------------------------

        self.active_popups = []

        # ----------------------------------------------------
        # LOCAL IP
        # ----------------------------------------------------

        self.local_ip = self.get_local_ip()

        # ----------------------------------------------------
        # UI
        # ----------------------------------------------------

        self.setup_ui()

        # ----------------------------------------------------
        # REALTIME FIREBASE <-> SQLITE/UI BRIDGE
        # ----------------------------------------------------

        self.firebase_sessions_changed.connect(
            self.on_firebase_sessions_changed
        )

        self.firebase_status_changed.connect(
            self.update_firebase_status
        )

        self.google_status_changed.connect(
            self.update_google_status
        )

        self.session_start_finished.connect(
            self.on_session_start_finished
        )

        self.session_end_finished.connect(
            self.on_session_end_finished
        )

        # Network-backed session operations must never run on the Qt GUI
        # thread. These flags prevent duplicate scans/clicks while a cloud
        # transaction is still in progress.
        self.session_start_in_progress = False
        self.ending_sessions = set()

        # Session START and END are both local-first. The PC must remain usable
        # even when Firebase is slow/offline. Cloud writes are queued and retried
        # in the background; SQLite/UI state changes immediately.
        self.pending_cloud_start_jobs = {}
        self.suppressed_cloud_session_ids = set()
        # Suppress by rickshaw too. A desktop session can be ended before its
        # generated cloud_id has been adopted into the in-memory event. Without
        # this guard, the 2-second Firebase poll could re-import the stale cloud
        # row while the END write is still finishing.
        self.suppressed_cloud_rickshaw_ids = set()
        self.pending_cloud_end_jobs = {}

        # Prevent several full master-data uploads (including photo encoding)
        # from running at the same time after rapid edits.
        self.master_sync_lock = threading.Lock()

        # Restore any local active rows immediately, then reconcile with the
        # global Firebase state using short background reads.
        self.reload_active_events_from_database()

        QTimer.singleShot(7000, self.sync_master_data)
        # Start realtime Firebase active-session listener.
        # Mobile START/END changes now reach the desktop immediately instead of
        # waiting for a polling cycle.
        QTimer.singleShot(500, self.start_firebase_listener)

        # Periodic master sync is a safety net. Edits also trigger a sync
        # directly from the Owners/Pullers/Rickshaws pages.
        self.master_sync_timer = QTimer(self)
        self.master_sync_timer.timeout.connect(self.sync_master_data)
        self.master_sync_timer.start(600000)

        # Retry pending Firebase START/END writes in the background. Neither
        # timer ever blocks the Qt GUI thread.
        self.cloud_start_retry_timer = QTimer(self)
        self.cloud_start_retry_timer.timeout.connect(self.retry_pending_cloud_starts)
        self.cloud_start_retry_timer.start(10000)

        self.cloud_end_retry_timer = QTimer(self)
        self.cloud_end_retry_timer.timeout.connect(self.retry_pending_cloud_ends)
        self.cloud_end_retry_timer.start(10000)

        # ----------------------------------------------------
        # TIMER
        # ----------------------------------------------------

        self.timer = QTimer(
            self
        )

        self.timer.timeout.connect(
            self.check_event_timeouts
        )

        self.timer.start(
            500
        )

        self.dashboard.set_scan_master_state()

    # ========================================================
    # MASTER DATA -> FIREBASE
    # ========================================================

    def sync_master_data(self):

        # Never allow several complete Firebase master-data uploads to pile up.
        # Photo conversion can be CPU-heavy and overlapping sync threads were a
        # major source of sluggishness on slower PCs.
        if not self.master_sync_lock.acquire(blocking=False):
            print("[MASTER SYNC] Previous sync still running; skipped duplicate.")
            return

        # Read SQLite on the UI thread (fast), then do all Firebase/photo work
        # on a daemon thread.
        try:
            owners = database.get_all_owners()
            pullers = database.get_all_pullers()
            rickshaws = database.get_all_rickshaws()

            print("SYNC OWNERS:", owners)
            print("SYNC PULLERS:", pullers)
            print("SYNC RICKSHAWS:", rickshaws)
        except Exception as e:
            self.master_sync_lock.release()
            print("[MASTER SYNC READ ERROR]", e)
            return

        def run_sync():
            try:
                firebase_service.sync_master_data(
                    owners,
                    pullers,
                    rickshaws
                )
            except Exception as e:
                print("[MASTER SYNC ERROR]", e)
            finally:
                self.master_sync_lock.release()

        threading.Thread(
            target=run_sync,
            daemon=True
        ).start()

    # ========================================================
    # FIREBASE ACTIVE SESSION POLLING (DISABLED)
    # ========================================================
    #
    # Kept only for backward compatibility with old code paths.
    # Active sessions are now delivered by Firebase realtime listener.

    def poll_firebase_sessions(self):
        self.ensure_firebase_listener()

    # ========================================================
    # FIREBASE REALTIME LISTENER
    # ========================================================
    # ========================================================

    def start_firebase_listener(self):

        if getattr(self, "_firebase_listener_starting", False):
            return

        self._firebase_listener_starting = True

        def worker():
            try:
                old_listener = self.firebase_listener
                self.firebase_listener = None

                if old_listener is not None:
                    try:
                        old_listener.close()
                    except Exception:
                        pass

                listener = firebase_service.listen_active_sessions(
                    lambda snapshot:
                    self.firebase_sessions_changed.emit(snapshot)
                )

                self.firebase_listener = listener

                if listener is None:
                    print(
                        "[FIREBASE LISTENER] Initial connection failed; "
                        "automatic retry is enabled."
                    )
                else:
                    print("[FIREBASE LISTENER] Active-session listener started.")

            except Exception as e:
                print("[FIREBASE LISTENER START ERROR]", e)

            finally:
                self._firebase_listener_starting = False

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def ensure_firebase_listener(self):

        # Only retry when no listener is registered and another start attempt
        # is not already running. This is lightweight and never blocks Qt.
        if self.firebase_listener is None:
            self.start_firebase_listener()

    def sync_mobile_history_events(self, active_sessions):
        """
        Fast mobile event sync.
        Process only new/changed mobile sessions.
        Avoid downloading full history on every Firebase update.
        """

        try:
            if not isinstance(active_sessions, dict):
                active_sessions = {}

            for key, session in active_sessions.items():

                if not isinstance(session, dict):
                    continue

                if str(session.get("source") or "").upper() != "MOBILE":
                    continue

                cloud_id = str(
                    session.get("cloud_session_id")
                    or session.get("cloud_id")
                    or key
                    or ""
                ).strip()

                if not cloud_id:
                    continue

                status = str(
                    session.get("status")
                    or session.get("history_status")
                    or "ACTIVE"
                ).upper()

                event_id = cloud_id + ":" + status + ":" + str(
                    session.get("started_at") or ""
                )

                if event_id in self.logged_mobile_cloud_events:
                    continue

                # Desktop is the only Google Sheet writer.
                # Mobile only updates Firebase.

                database.save_transaction(
                    None,
                    session.get("rickshaw_id"),
                    session.get("owner_id"),
                    session.get("puller_id"),
                    session.get("master_uid"),
                    session.get("slave_uid"),
                    "MOBILE_SYNC",
                    "Firebase mobile session"
                )

                log_event(
                    cloud_id,

                    session.get("rickshaw_number")
                    or session.get("rickshaw")
                    or session.get("rickshaw_id")
                    or "",

                    session.get("owner_name")
                    or session.get("owner")
                    or session.get("owner_id")
                    or "",

                    session.get("puller_name")
                    or session.get("puller")
                    or session.get("puller_id")
                    or "",

                    session.get("master_uid") or "",
                    session.get("slave_uid") or "",

                    status,

                    "MOBILE",

                    convert_firebase_time(
                        session.get("started_at")
                    )
                )

                self.logged_mobile_cloud_events.add(event_id)

        except Exception as e:
            print("[MOBILE EVENT SYNC ERROR]", repr(e))


    def on_firebase_sessions_changed(self, cloud_sessions):

        try:
            # Process only changed cloud snapshots. Firebase polling may return
            # the same active session many times; unchanged sessions must not
            # trigger Google writes again.
            snapshot_hash = repr(cloud_sessions)
            if getattr(self, "_last_cloud_snapshot_hash", None) == snapshot_hash:
                return
            self._last_cloud_snapshot_hash = snapshot_hash
            # Do not run Firebase history/Google synchronization in the Qt GUI thread.
            threading.Thread(
                target=self.sync_mobile_history_events,
                args=(cloud_sessions,),
                daemon=True
            ).start()

            if not isinstance(cloud_sessions, dict):
                cloud_sessions = {}

            # Determine which cloud sessions really exist in this snapshot.
            present_cloud_ids = set()
            for payload in cloud_sessions.values():
                if not isinstance(payload, dict):
                    continue
                cloud_id = str(
                    payload.get("cloud_session_id")
                    or payload.get("cloud_id")
                    or ""
                ).strip()
                if cloud_id:
                    present_cloud_ids.add(cloud_id)

            # Track rickshaws that are still present in the cloud snapshot.
            present_rickshaw_ids = set()
            for key, payload in cloud_sessions.items():
                if not isinstance(payload, dict):
                    continue
                rid = str(payload.get("rickshaw_id") or key or "").strip()
                if rid:
                    present_rickshaw_ids.add(rid)

            # Firebase confirming that /live/active_sessions disappeared only
            # confirms the first half of END. It does NOT prove that the later
            # /live/rickshaws + /public/by_token IDLE projection succeeded.
            # Therefore never delete a pending END retry job from the poller.
            # The background END worker removes its own job only after the full
            # END operation (including public website state) succeeds.
            for cloud_id in list(self.suppressed_cloud_session_ids):
                if cloud_id not in present_cloud_ids:
                    self.suppressed_cloud_session_ids.discard(cloud_id)
                    print("[FIREBASE ACTIVE ROW REMOVED]", cloud_id)

            for rid in list(self.suppressed_cloud_rickshaw_ids):
                if rid not in present_rickshaw_ids:
                    self.suppressed_cloud_rickshaw_ids.discard(rid)
                    print("[FIREBASE RICKSHAW ACTIVE ROW REMOVED]", rid)

            # A session ended from this PC must not be re-imported just because
            # Firebase is a few seconds behind or temporarily offline. Suppress
            # both the cloud ID and the rickshaw ID while END is pending.
            filtered_sessions = {}
            for key, payload in cloud_sessions.items():
                if not isinstance(payload, dict):
                    continue
                cloud_id = str(
                    payload.get("cloud_session_id")
                    or payload.get("cloud_id")
                    or ""
                ).strip()
                rid = str(payload.get("rickshaw_id") or key or "").strip()
                if cloud_id and cloud_id in self.suppressed_cloud_session_ids:
                    continue
                if rid and rid in self.suppressed_cloud_rickshaw_ids:
                    continue
                filtered_sessions[key] = payload

            result = database.reconcile_cloud_active_sessions(
                filtered_sessions
            )

            print(
                "[FIREBASE -> SQLITE]",
                result
            )

            # Do not rebuild the dashboard inside the Firebase callback.
            # Queue the UI update so Firebase remains responsive.
            QTimer.singleShot(
                0,
                self.reload_active_events_from_database
            )

        except Exception as e:
            print("[FIREBASE RECONCILE ERROR]", e)

    # ========================================================
    # SQLITE ACTIVE SESSIONS -> GUI
    # ========================================================

    def reload_active_events_from_database(self):

        events = {}

        try:
            rows = database.get_active_sessions()
        except Exception as e:
            print("[ACTIVE SESSION LOAD ERROR]", e)
            rows = []

        for row in rows:

            session_id = row.get("id")
            if not session_id:
                continue

            rickshaw = database.get_rickshaw(
                row.get("rickshaw_id")
            )

            owner = database.get_owner(
                row.get("owner_id")
            )

            puller = database.get_puller(
                row.get("puller_id")
            )

            if not rickshaw or not owner or not puller:
                continue

            started_raw = str(
                row.get("started_at")
                or datetime.now().isoformat(timespec="seconds")
            )

            try:
                started_datetime = datetime.fromisoformat(
                    started_raw.replace("Z", "+00:00")
                )

                # Session timers in the current UI use naive local datetimes.
                # If a timezone-aware value arrives from mobile, convert it to
                # local time and remove tzinfo before calculating elapsed time.
                if started_datetime.tzinfo is not None:
                    started_datetime = (
                        started_datetime.astimezone()
                        .replace(tzinfo=None)
                    )

            except Exception:
                started_datetime = datetime.now()

            events[session_id] = {
                "session_id": session_id,
                "cloud_id": row.get("cloud_id") or "",
                "source": row.get("source") or "DESKTOP",
                "owner": owner,
                "rickshaw": rickshaw,
                "puller": puller,
                "master_uid": row.get("master_uid") or "",
                "slave_uid": row.get("slave_uid") or "",
                "started_at": started_raw,
                "started_datetime": started_datetime,
                "card": None
            }

        self.active_events = events

        # Update GUI safely through Qt event loop.
        if hasattr(self, "dashboard"):
            QTimer.singleShot(
                0,
                self.dashboard.refresh_events
            )

    # ========================================================
    # FIREBASE TEST
    # ========================================================

    def test_firebase_connection(self):
        """Run the Firebase probe outside the Qt GUI thread."""

        def worker():
            try:
                ok, message = firebase_service.probe_firebase()
                print("[FIREBASE TEST]", ok, message)

                # The regular 2-second poll will also update connection state.
                self.firebase_connection_ok = bool(ok)

            except Exception as e:
                self.firebase_connection_ok = False
                print("[FIREBASE TEST ERROR]", repr(e))

        threading.Thread(target=worker, daemon=True).start()
        return True

    # ========================================================
    # LOCAL IP
    # ========================================================

    def get_local_ip(self):

        try:

            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM
            )

            sock.connect(
                ("8.8.8.8", 80)
            )

            ip = sock.getsockname()[0]

            sock.close()

            return ip

        except Exception:

            return "127.0.0.1"

    # ========================================================
    # UI
    # ========================================================

    def setup_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        layout = QHBoxLayout(
            central
        )

        # ----------------------------------------------------
        # SIDEBAR
        # ----------------------------------------------------

        sidebar = QFrame()

        sidebar.setObjectName(
            "sidebar"
        )

        sidebar.setFixedWidth(
            230
        )

        side = QVBoxLayout(
            sidebar
        )

        logo = QLabel(
            "RICKSHAW\nCONTROL"
        )

        logo.setObjectName(
            "logo"
        )

        side.addWidget(
            logo
        )

        self.dashboard_button = QPushButton(
            "⌂   Dashboard"
        )

        self.owners_button = QPushButton(
            "♙   Owners"
        )

        self.pullers_button = QPushButton(
            "♟   Pullers"
        )

        self.rickshaws_button = QPushButton(
            "▣   Rickshaws"
        )

        self.events_button = QPushButton(
            "☷   Events"
        )

        self.settings_button = QPushButton(
            "⚙   Settings"
        )

        self.open_sheet_button = QPushButton(
            "▤   Open Google Sheet"
        )

        self.open_sheet_button.clicked.connect(
            self.open_google_sheet
        )

        for button in [
            self.dashboard_button,
            self.owners_button,
            self.pullers_button,
            self.rickshaws_button,
            self.events_button,
            self.settings_button,
            self.open_sheet_button
        ]:

            side.addWidget(
                button
            )

        side.addStretch()

        ip_label = QLabel(
            f"QR Server:\n"
            f"http://{self.local_ip}:5000"
        )

        ip_label.setObjectName(
            "reader_status"
        )

        side.addWidget(
            ip_label
        )

        layout.addWidget(
            sidebar
        )

        # ----------------------------------------------------
        # PAGES
        # ----------------------------------------------------

        self.pages = QStackedWidget()

        self.dashboard = Dashboard(
            self
        )

        self.owners_page = OwnersPage(
            self
        )

        self.pullers_page = PullersPage(
            self
        )

        self.rickshaws_page = RickshawsPage(
            self
        )

        self.events_page = EventsPage(
            self
        )

        self.settings_page = SettingsPage(
            self
        )

        for page in [
            self.dashboard,
            self.owners_page,
            self.pullers_page,
            self.rickshaws_page,
            self.events_page,
            self.settings_page
        ]:

            self.pages.addWidget(
                page
            )

        # ----------------------------------------------------
        # TOP STATUS INDICATORS
        # ----------------------------------------------------
        status_bar = QHBoxLayout()
        status_bar.addStretch()

        self.firebase_status_label = QLabel("● Firebase: Connecting")
        self.google_status_label = QLabel("● Google: Idle")

        self.firebase_status_label.setObjectName("reader_status")
        self.google_status_label.setObjectName("reader_status")

        status_bar.addWidget(self.firebase_status_label)
        status_bar.addWidget(self.google_status_label)

        status_container = QWidget()
        status_container.setLayout(status_bar)

        # keep status visible above pages
        page_container = QVBoxLayout()
        page_container.addWidget(status_container)
        page_container.addWidget(self.pages)

        wrapper = QWidget()
        wrapper.setLayout(page_container)

        layout.addWidget(wrapper)

        # ----------------------------------------------------
        # NAVIGATION
        # ----------------------------------------------------

        self.dashboard_button.clicked.connect(
            self.show_dashboard
        )

        self.owners_button.clicked.connect(
            self.show_owners
        )

        self.pullers_button.clicked.connect(
            self.show_pullers
        )

        self.rickshaws_button.clicked.connect(
            self.show_rickshaws
        )

        self.events_button.clicked.connect(
            self.show_events
        )

        self.settings_button.clicked.connect(
            self.show_settings
        )

    def update_firebase_status(self, state):
        if hasattr(self, "firebase_status_label"):
            if state == "connected":
                self.firebase_status_label.setText("● Firebase: Connected")
            elif state == "connecting":
                self.firebase_status_label.setText("● Firebase: Connecting")
            else:
                self.firebase_status_label.setText("● Firebase: Not Connected")

    def update_google_status(self, state):
        if hasattr(self, "google_status_label"):
            if state == "ok":
                self.google_status_label.setText("● Google: Synced")
            elif state == "working":
                self.google_status_label.setText("● Google: Uploading")
            else:
                self.google_status_label.setText("● Google: Failed")

    def open_google_sheet(self):
        url = "https://docs.google.com/spreadsheets/d/1L-BfSp_qJdXepvxI7A2zooE9lDOK-H_YDnDwg74BuP8/edit?gid=0#gid=0"
        webbrowser.open(url)

    # ========================================================
    # NAVIGATION
    # ========================================================

    def show_dashboard(self):

        self.pages.setCurrentWidget(
            self.dashboard
        )

        QTimer.singleShot(
            100,
            self.dashboard.rfid_input.setFocus
        )

    def show_owners(self):

        self.owners_page.refresh()

        self.pages.setCurrentWidget(
            self.owners_page
        )

    def show_pullers(self):

        self.pullers_page.refresh()

        self.pages.setCurrentWidget(
            self.pullers_page
        )

    def show_rickshaws(self):

        self.rickshaws_page.refresh()

        self.pages.setCurrentWidget(
            self.rickshaws_page
        )

    def show_events(self):

        self.events_page.refresh()

        self.pages.setCurrentWidget(
            self.events_page
        )

    def show_settings(self):

        self.settings_page.session_spin.setValue(
            self.session_timeout
        )

        self.settings_page.session_enabled.setChecked(
            self.session_timeout_enabled
        )

        self.settings_page.popup_spin.setValue(
            self.popup_timeout
        )

        self.settings_page.google_enable.setChecked(
            self.google_enabled
        )

        self.settings_page.google_url.setText(
            self.google_url
        )

        self.pages.setCurrentWidget(
            self.settings_page
        )

    # ========================================================
    # RFID PROCESSING
    # ========================================================

    def process_rfid(
        self,
        uid
    ):

        uid = uid.strip().upper()

        if not uid:

            return

        print(
            "[RFID]",
            uid,
            "| MODE:",
            self.scan_mode
        )

        # ====================================================
        # MASTER MODE
        # ====================================================

        if self.scan_mode == "MASTER":

            owner = database.get_owner_by_master(
                uid
            )

            if not owner:

                puller = database.get_puller_by_slave(
                    uid
                )

                if puller:

                    log_event(
                        None,
                        "",
                        "",
                        puller["name"],
                        "",
                        uid,
                        "REJECTED",
                        "MASTER_REQUIRED"
                    )

                    self.popup(
                        "MASTER REQUIRED",
                        (
                            "This is a Slave/Puller card.\n\n"
                            "Scan the Owner Master card first."
                        ),
                        QMessageBox.Warning
                    )

                    self.dashboard.set_scan_master_state()

                    return

                self.popup(
                    "UNKNOWN RFID",
                    (
                        f"UID: {uid}\n\n"
                        "This RFID is not registered."
                    ),
                    QMessageBox.Warning
                )

                self.dashboard.set_scan_master_state()

                return

            self.select_rickshaw_for_owner(
                owner,
                uid
            )

            return

        # ====================================================
        # SLAVE MODE
        # ====================================================

        if self.scan_mode == "SLAVE":

            puller = database.get_puller_by_slave(
                uid
            )

            if not puller:

                log_event(
                    None,
                    (
                        self.pending_rickshaw[
                            "rickshaw_number"
                        ]
                        if self.pending_rickshaw
                        else ""
                    ),
                    (
                        self.pending_owner[
                            "name"
                        ]
                        if self.pending_owner
                        else ""
                    ),
                    "",
                    self.pending_master_uid or "",
                    uid,
                    "REJECTED",
                    "UNKNOWN_SLAVE"
                )

                self.popup(
                    "UNKNOWN SLAVE",
                    (
                        f"UID: {uid}\n\n"
                        "Puller is not registered."
                    ),
                    QMessageBox.Warning
                )

                if (
                    self.pending_owner
                    and self.pending_rickshaw
                ):

                    self.dashboard.set_scan_slave_state(
                        self.pending_owner,
                        self.pending_rickshaw
                    )

                else:

                    self.dashboard.set_scan_master_state()

                return

            self.create_event(
                puller,
                uid
            )

    # ========================================================
    # SELECT RICKSHAW
    # ========================================================

    def select_rickshaw_for_owner(
        self,
        owner,
        master_uid
    ):

        rickshaws = database.get_rickshaws_by_owner(
            owner["id"]
        )

        if not rickshaws:

            self.popup(
                "NO RICKSHAW",
                (
                    f"Owner: {owner['name']}\n\n"
                    "No rickshaw is assigned to this owner."
                ),
                QMessageBox.Warning
            )

            self.dashboard.set_scan_master_state()

            return

        dialog = RickshawSelectDialog(
            owner,
            self
        )

        if dialog.exec() != QDialog.Accepted:

            self.dashboard.set_scan_master_state()

            return

        rickshaw_id = (
            dialog.get_rickshaw_id()
        )

        if not rickshaw_id:

            self.dashboard.set_scan_master_state()

            return

        rickshaw = database.get_rickshaw(
            rickshaw_id
        )

        if not rickshaw:

            self.popup(
                "ERROR",
                "Selected rickshaw could not be found.",
                QMessageBox.Critical
            )

            self.dashboard.set_scan_master_state()

            return

        self.pending_owner = owner

        self.pending_rickshaw = rickshaw

        self.pending_master_uid = master_uid

        self.scan_mode = "SLAVE"

        self.dashboard.set_scan_slave_state(
            owner,
            rickshaw
        )

    # ========================================================
    # CREATE EVENT
    # ========================================================

    def create_event(
        self,
        puller,
        slave_uid
    ):

        if self.session_start_in_progress:
            return

        if not self.pending_owner or not self.pending_rickshaw:
            self.scan_mode = "MASTER"
            self.dashboard.set_scan_master_state()
            return

        owner = dict(self.pending_owner)
        rickshaw = dict(self.pending_rickshaw)
        puller = dict(puller)
        master_uid = self.pending_master_uid or owner["master_uid"]
        slave_uid = str(slave_uid or "").strip().upper()

        cloud_id = firebase_service.generate_session_id()
        started_at = datetime.now().isoformat(timespec="seconds")

        # ----------------------------------------------------
        # 1) CREATE SQLITE SESSION FIRST
        # ----------------------------------------------------
        # Do NOT wait for Firebase here. The local dashboard should show the
        # active session immediately, even on a slow or disconnected network.
        try:
            session_id = database.start_rickshaw_session(
                rickshaw["id"],
                owner["id"],
                puller["id"],
                master_uid,
                slave_uid,
                cloud_id="",
                source="DESKTOP",
                started_at=started_at
            )

            database.save_transaction(
                session_id,
                rickshaw["id"],
                owner["id"],
                puller["id"],
                master_uid,
                slave_uid,
                "ACCEPTED",
                "DESKTOP_SESSION_STARTED_LOCAL"
            )

            log_event(
                session_id,
                rickshaw["rickshaw_number"],
                owner["name"],
                puller["name"],
                master_uid,
                slave_uid,
                "EVENT_CREATED",
                "DESKTOP_LOCAL_FIRST"
            )

        except Exception as e:
            print("[LOCAL SESSION CREATE ERROR]", e)
            self.popup(
                "SESSION NOT STARTED",
                str(e),
                QMessageBox.Critical
            )
            self.pending_owner = None
            self.pending_rickshaw = None
            self.pending_master_uid = None
            self.scan_mode = "MASTER"
            self.dashboard.set_scan_master_state()
            return

        # ----------------------------------------------------
        # 2) QUEUE FIREBASE START
        # ----------------------------------------------------
        self.pending_cloud_start_jobs[session_id] = {
            "session_id": session_id,
            "cloud_id": cloud_id,
            "owner": owner,
            "rickshaw": rickshaw,
            "puller": puller,
            "master_uid": master_uid,
            "slave_uid": slave_uid,
            "started_at": started_at,
            "in_progress": False,
            "needs_retry": True,
            "attempts": 0,
            "canceled": False,
            "replace_cloud_ids": set(),
        }

        # ----------------------------------------------------
        # 3) UPDATE UI IMMEDIATELY
        # ----------------------------------------------------
        self.pending_owner = None
        self.pending_rickshaw = None
        self.pending_master_uid = None
        self.scan_mode = "MASTER"

        self.reload_active_events_from_database()
        self.dashboard.set_scan_master_state()
        self.events_page.refresh()

        self.popup(
            "EVENT CREATION SUCCESSFUL",
            (
                f"Event created successfully.\n\n"
                f"Rickshaw: {rickshaw['rickshaw_number']}\n"
                f"Owner: {owner['name']}\n"
                f"Puller: {puller['name']}\n\n"
                f"Session ID: {session_id}\n\n"
                "Firebase synchronization is running in the background."
            ),
            QMessageBox.Information
        )

        self.start_cloud_start_job(session_id)

    # ========================================================
    # CLOUD START QUEUE
    # ========================================================

    def start_cloud_start_job(self, session_id):

        job = self.pending_cloud_start_jobs.get(session_id)
        if not job:
            return

        if job.get("in_progress") or not job.get("needs_retry", True):
            return

        if job.get("canceled"):
            self.pending_cloud_start_jobs.pop(session_id, None)
            return

        job["in_progress"] = True
        job["attempts"] = int(job.get("attempts", 0)) + 1
        attempt = job["attempts"]

        owner = dict(job["owner"])
        rickshaw = dict(job["rickshaw"])
        puller = dict(job["puller"])
        master_uid = job["master_uid"]
        slave_uid = job["slave_uid"]
        cloud_id = job["cloud_id"]
        started_at = job["started_at"]

        def worker():
            result = {
                "session_id": session_id,
                "cloud_id": cloud_id,
                "attempt": attempt,
                "ok": False,
                "conflict": False,
                "payload": None,
                "conflict_payload": None,
                "error": "",
            }

            try:
                payload = firebase_service.start_session(
                    rickshaw,
                    owner,
                    puller,
                    master_uid,
                    slave_uid,
                    cloud_id=cloud_id,
                    local_session_id=session_id,
                    source="DESKTOP",
                    started_at=started_at,
                    replace_cloud_ids=list(job.get("replace_cloud_ids") or [])
                )
                result["ok"] = True
                result["payload"] = payload
                if isinstance(payload, dict):
                    result["cloud_id"] = (
                        payload.get("cloud_session_id")
                        or payload.get("cloud_id")
                        or cloud_id
                    )

            except firebase_service.SessionConflictError as e:
                result["conflict"] = True
                result["error"] = str(e)
                result["conflict_payload"] = getattr(
                    e,
                    "current_session",
                    None
                )

            except Exception as e:
                print("[FIREBASE START BACKGROUND ERROR]", e)
                result["error"] = str(e)

            self.session_start_finished.emit(result)

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def retry_pending_cloud_starts(self):

        for session_id, job in list(self.pending_cloud_start_jobs.items()):
            if job.get("canceled"):
                if not job.get("in_progress"):
                    self.pending_cloud_start_jobs.pop(session_id, None)
                continue

            if job.get("needs_retry") and not job.get("in_progress"):
                self.start_cloud_start_job(session_id)

    def on_session_start_finished(self, result):

        session_id = result.get("session_id")
        job = self.pending_cloud_start_jobs.get(session_id)

        if not job:
            return

        job["in_progress"] = False

        # The operator may have ended the local session while the Firebase
        # START request was still in flight. If Firebase eventually accepted
        # it, immediately queue a cloud END so it cannot remain active online.
        if job.get("canceled"):
            if result.get("ok"):
                cloud_id = job.get("cloud_id")
                end_key = cloud_id or f"rickshaw:{job['rickshaw']['id']}:{session_id}"
                self.pending_cloud_end_jobs[end_key] = {
                    "job_key": end_key,
                    "session_id": session_id,
                    "cloud_id": cloud_id or None,
                    "rickshaw": dict(job["rickshaw"]),
                    "owner_id": job["owner"].get("id"),
                    "puller_id": job["puller"].get("id"),
                    "started_at": job.get("started_at"),
                    "status": "COMPLETED",
                    "reason": "LOCAL_SESSION_ENDED_DURING_CLOUD_START",
                    "in_progress": False,
                    "needs_retry": True,
                    "attempts": 0,
                }
                self.start_cloud_end_job(end_key)

            self.pending_cloud_start_jobs.pop(session_id, None)
            return

        if result.get("ok"):
            payload = result.get("payload")
            try:
                if isinstance(payload, dict):
                    database.upsert_cloud_active_session(payload)
            except Exception as e:
                print("[LOCAL CLOUD-ID ADOPT ERROR]", e)

            self.pending_cloud_start_jobs.pop(session_id, None)
            self.reload_active_events_from_database()
            print(
                "[FIREBASE START WRITE OK]",
                result.get("cloud_id"),
                "attempt",
                result.get("attempt")
            )
            return

        if result.get("conflict"):
            conflict_payload = result.get("conflict_payload")
            if not isinstance(conflict_payload, dict):
                conflict_payload = {}

            conflict_cloud_id = str(
                conflict_payload.get("cloud_session_id")
                or conflict_payload.get("cloud_id")
                or ""
            ).strip()

            # ------------------------------------------------
            # STALE CLOUD SESSION FROM A PREVIOUS LOCAL END
            # ------------------------------------------------
            # A previous PC session may already be COMPLETED in SQLite while
            # its Firebase END request is still retrying. That stale cloud row
            # must not destroy the new valid local session. Mark it replaceable
            # and retry the same Firebase START atomically.
            stale_cloud_conflict = False

            if conflict_cloud_id:
                if conflict_cloud_id in self.suppressed_cloud_session_ids:
                    stale_cloud_conflict = True
                else:
                    try:
                        previous_local = database.get_session_by_cloud_id(
                            conflict_cloud_id
                        )
                        if (
                            previous_local
                            and str(previous_local.get("status") or "").upper()
                            != "ACTIVE"
                        ):
                            stale_cloud_conflict = True
                    except Exception as e:
                        print("[STALE CLOUD CHECK ERROR]", e)

            if stale_cloud_conflict and conflict_cloud_id:
                self.suppressed_cloud_session_ids.add(conflict_cloud_id)
                replace_ids = job.setdefault("replace_cloud_ids", set())
                replace_ids.add(conflict_cloud_id)
                job["needs_retry"] = True

                print(
                    "[FIREBASE START] Replacing stale cloud session:",
                    conflict_cloud_id
                )

                # Keep the new session visible. Retry immediately; the normal
                # 10-second timer remains a backup if the network is slow.
                QTimer.singleShot(
                    100,
                    lambda sid=session_id: self.start_cloud_start_job(sid)
                )
                return

            # ------------------------------------------------
            # GENUINE REMOTE CONFLICT
            # ------------------------------------------------
            # Do not blindly delete the PC card. Import/reconcile the session
            # that Firebase says is really active. If it has the same owner and
            # puller, SQLite adopts its cloud ID; if it is truly different, the
            # remote session replaces the local provisional row and remains
            # visible on the dashboard.
            if conflict_payload:
                try:
                    database.upsert_cloud_active_session(conflict_payload)
                    self.pending_cloud_start_jobs.pop(session_id, None)
                    self.reload_active_events_from_database()
                    self.events_page.refresh()

                    self.popup(
                        "SESSION RECONCILED",
                        (
                            "Firebase already had an active session for this "
                            "rickshaw. The PC has synchronized to that active "
                            "session instead of hiding it."
                        ),
                        QMessageBox.Warning
                    )
                    return
                except Exception as e:
                    print("[CONFLICT RECONCILE ERROR]", e)

            # If Firebase did not provide enough conflict data, keep the local
            # session visible and retry later rather than deleting it.
            job["needs_retry"] = True
            print(
                "[FIREBASE START CONFLICT PENDING]",
                session_id,
                result.get("error", "")
            )
            return

        job["needs_retry"] = True
        print(
            "[FIREBASE START PENDING RETRY]",
            session_id,
            result.get("error", "")
        )

        if int(result.get("attempt") or 0) == 1:
            self.popup(
                "FIREBASE SYNC PENDING",
                (
                    "The session is ACTIVE on this PC. Firebase is currently "
                    "slow/unavailable, so cloud synchronization will retry "
                    "automatically every 10 seconds."
                ),
                QMessageBox.Warning
            )

    # ========================================================
    # END EVENT
    # ========================================================

    def end_event(
        self,
        session_id
    ):

        if session_id not in self.active_events:
            return

        if session_id in self.ending_sessions:
            return

        event_data = self.active_events[session_id]

        answer = QMessageBox.question(
            self,
            "End Rickshaw Session",
            (
                f"End this event?\n\n"
                f"Rickshaw: {event_data['rickshaw']['rickshaw_number']}\n"
                f"Owner: {event_data['owner']['name']}\n"
                f"Puller: {event_data['puller']['name']}"
            ),
            QMessageBox.Yes | QMessageBox.No
        )

        if answer != QMessageBox.Yes:
            return

        self.finish_event(
            session_id,
            "SESSION_ENDED",
            ""
        )

    # ========================================================
    # FINISH EVENT - LOCAL FIRST, CLOUD IN BACKGROUND
    # ========================================================

    def finish_event(
        self,
        session_id,
        status,
        reason
    ):

        if session_id not in self.active_events:
            return False

        if session_id in self.ending_sessions:
            return False

        event_data = self.active_events[session_id]
        event_copy = {
            **event_data,
            "owner": dict(event_data["owner"]),
            "rickshaw": dict(event_data["rickshaw"]),
            "puller": dict(event_data["puller"]),
        }

        pending_start = self.pending_cloud_start_jobs.get(session_id)
        cloud_id = str(
            event_copy.get("cloud_id")
            or (pending_start or {}).get("cloud_id")
            or ""
        ).strip()

        if pending_start:
            # Stop future START retries. If a START request is already in
            # flight, on_session_start_finished() will immediately queue END if
            # Firebase accepts it after the local session has been closed.
            pending_start["canceled"] = True
            pending_start["needs_retry"] = False

        remote_status = (
            "AUTO_ENDED"
            if status == "AUTO_SESSION_ENDED"
            else "COMPLETED"
        )

        self.ending_sessions.add(session_id)

        card = event_data.get("card")
        if card and hasattr(card, "end_button"):
            card.end_button.setEnabled(False)
            card.end_button.setText("ENDING SESSION...")

        # ----------------------------------------------------
        # 1) END SQLITE IMMEDIATELY
        # ----------------------------------------------------
        # Ending a local session does not depend on internet/Firebase. This is
        # what makes the END button reliable even during a bad connection.
        try:
            local_ok = database.end_rickshaw_session(
                session_id,
                status=remote_status
            )

            if not local_ok:
                still_active = any(
                    row.get("id") == session_id
                    for row in database.get_active_sessions()
                )
                if still_active:
                    raise RuntimeError("Local database could not end the session.")

            database.save_transaction(
                session_id,
                event_copy["rickshaw"]["id"],
                event_copy["owner"]["id"],
                event_copy["puller"]["id"],
                event_copy["master_uid"],
                event_copy["slave_uid"],
                status,
                reason
            )

            log_event(
                cloud_id or session_id,
                event_copy["rickshaw"]["rickshaw_number"],
                event_copy["owner"]["name"],
                event_copy["puller"]["name"],
                event_copy["master_uid"],
                event_copy["slave_uid"],
                status,
                reason
            )

        except Exception as e:
            print("[LOCAL END ERROR]", e)
            self.ending_sessions.discard(session_id)

            if card and hasattr(card, "end_button"):
                card.end_button.setEnabled(True)
                card.end_button.setText("END RICKSHAW SESSION")

            self.popup(
                "SESSION NOT ENDED",
                str(e),
                QMessageBox.Critical
            )
            return False

        # ----------------------------------------------------
        # 2) SUPPRESS THE STALE CLOUD COPY UNTIL CONFIRMED GONE
        # ----------------------------------------------------
        # Always suppress the rickshaw ID. The event may have been ended before
        # its cloud_id was adopted locally, and in that race a cloud-id-only
        # guard is insufficient.
        rickshaw_id_text = str(event_copy["rickshaw"]["id"]).strip()
        if rickshaw_id_text:
            self.suppressed_cloud_rickshaw_ids.add(rickshaw_id_text)

        if cloud_id:
            self.suppressed_cloud_session_ids.add(cloud_id)

        # ----------------------------------------------------
        # 3) QUEUE FIREBASE END - NEVER BLOCK THE GUI
        # ----------------------------------------------------
        # If a Firebase START is still in flight, do not race an END request
        # against it. The START completion handler will queue END if needed.
        job_key = None
        if not pending_start:
            job_key = cloud_id or f"rickshaw:{event_copy['rickshaw']['id']}:{session_id}"
            self.pending_cloud_end_jobs[job_key] = {
                "job_key": job_key,
                "session_id": session_id,
                "cloud_id": cloud_id or None,
                "rickshaw": dict(event_copy["rickshaw"]),
                "owner_id": event_copy["owner"].get("id"),
                "puller_id": event_copy["puller"].get("id"),
                "started_at": event_copy.get("started_at"),
                "status": remote_status,
                "reason": reason or status,
                "in_progress": False,
                "needs_retry": True,
                "attempts": 0,
            }

        # ----------------------------------------------------
        # 4) UPDATE PC UI NOW
        # ----------------------------------------------------
        self.ending_sessions.discard(session_id)
        self.reload_active_events_from_database()
        self.events_page.refresh()
        self.dashboard.set_scan_master_state()

        rickshaw = event_copy.get("rickshaw") or {}
        puller = event_copy.get("puller") or {}

        if status == "AUTO_SESSION_ENDED":
            self.popup(
                "SESSION TIMEOUT",
                (
                    f"Rickshaw:\n{rickshaw.get('rickshaw_number', '')}\n\n"
                    f"Puller:\n{puller.get('name', '')}\n\n"
                    "The session ended on this PC. Firebase is syncing in "
                    "the background."
                ),
                QMessageBox.Warning
            )
        else:
            self.popup(
                "SESSION ENDED",
                (
                    f"Rickshaw:\n{rickshaw.get('rickshaw_number', '')}\n\n"
                    f"Puller:\n{puller.get('name', '')}\n\n"
                    "The session ended successfully on this PC. Firebase is "
                    "syncing in the background."
                ),
                QMessageBox.Information
            )

        if job_key:
            self.start_cloud_end_job(job_key)
        return True

    # ========================================================
    # CLOUD END QUEUE
    # ========================================================

    def start_cloud_end_job(self, job_key):

        job = self.pending_cloud_end_jobs.get(job_key)
        if not job:
            return

        if job.get("in_progress") or not job.get("needs_retry", True):
            return

        job["in_progress"] = True
        job["attempts"] = int(job.get("attempts", 0)) + 1
        attempt = job["attempts"]

        rickshaw = dict(job["rickshaw"])
        cloud_id = job.get("cloud_id")
        expected_owner_id = job.get("owner_id")
        expected_puller_id = job.get("puller_id")
        expected_started_at = job.get("started_at")
        remote_status = job.get("status", "COMPLETED")
        reason = job.get("reason", "")

        def worker():
            result = {
                "job_key": job_key,
                "cloud_id": cloud_id,
                "attempt": attempt,
                "ok": False,
                "error": "",
            }

            try:
                firebase_service.end_session(
                    rickshaw,
                    cloud_id=cloud_id,
                    expected_owner_id=expected_owner_id,
                    expected_puller_id=expected_puller_id,
                    expected_started_at=expected_started_at,
                    ended_by="DESKTOP",
                    status=remote_status,
                    reason=reason
                )
                result["ok"] = True

            except firebase_service.SessionConflictError as e:
                # This is a genuine replacement session, not merely a cloud-ID
                # reconciliation mismatch. Do not end the replacement session.
                # Clear local suppression so the next poll imports the true
                # Firebase-active assignment.
                print("[FIREBASE END CONFLICT]", e)
                result["conflict"] = True
                result["current_session"] = getattr(e, "current_session", None)
                result["error"] = str(e)

            except Exception as e:
                print("[FIREBASE END BACKGROUND ERROR]", e)
                result["error"] = str(e)

            self.session_end_finished.emit(result)

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def retry_pending_cloud_ends(self):

        for job_key, job in list(self.pending_cloud_end_jobs.items()):
            if job.get("needs_retry") and not job.get("in_progress"):
                self.start_cloud_end_job(job_key)

    def on_session_end_finished(self, result):

        job_key = result.get("job_key")
        job = self.pending_cloud_end_jobs.get(job_key)

        if not job:
            return

        job["in_progress"] = False

        if result.get("ok"):
            job["needs_retry"] = False
            print(
                "[FIREBASE END WRITE OK]",
                job_key,
                "attempt",
                result.get("attempt")
            )

            # end_session() returns success only after both the active-session
            # row and the live/public IDLE projection have been written. It is
            # therefore safe to remove the retry job here. Suppression remains
            # until a following poll confirms the old active row is absent.
            self.pending_cloud_end_jobs.pop(job_key, None)
            return

        if result.get("conflict"):
            job["needs_retry"] = False
            self.pending_cloud_end_jobs.pop(job_key, None)

            cloud_id = str(job.get("cloud_id") or "").strip()
            rid = str((job.get("rickshaw") or {}).get("id") or "").strip()
            if cloud_id:
                self.suppressed_cloud_session_ids.discard(cloud_id)
            if rid:
                self.suppressed_cloud_rickshaw_ids.discard(rid)

            print(
                "[FIREBASE END] A different replacement session is active; "
                "the next poll will import it."
            )
            QTimer.singleShot(100, self.poll_firebase_sessions)
            return

        job["needs_retry"] = True
        print(
            "[FIREBASE END PENDING RETRY]",
            job_key,
            result.get("error", "")
        )

        # Notify only after the first failed attempt. The 10-second retry timer
        # continues silently afterwards, so the operator can keep using the PC.
        if int(result.get("attempt") or 0) == 1:
            self.popup(
                "FIREBASE SYNC PENDING",
                (
                    "The session is already ended on this PC. The Firebase END "
                    "write did not complete yet and will keep retrying.\n\n"
                    f"Firebase error: {result.get('error') or 'Unknown error'}"
                ),
                QMessageBox.Warning
            )

    # ========================================================
    # EVENT TIMEOUTS
    # ========================================================

    def check_event_timeouts(self):

        if not self.active_events:

            return

        self.dashboard.update_event_timers()

        if not self.session_timeout_enabled:

            return

        now = datetime.now()

        expired = []

        for session_id, event_data in (
            self.active_events.items()
        ):

            elapsed = (
                now -
                event_data["started_datetime"]
            ).total_seconds()

            if elapsed >= self.session_timeout:

                expired.append(
                    session_id
                )

        for session_id in expired:

            self.auto_end_event(
                session_id
            )

    # ========================================================
    # AUTO END EVENT
    # ========================================================

    def auto_end_event(
        self,
        session_id
    ):

        if session_id not in self.active_events:
            return

        if session_id in self.ending_sessions:
            return

        self.finish_event(
            session_id,
            "AUTO_SESSION_ENDED",
            "SESSION_TIMEOUT"
        )

    # ========================================================
    # POPUP
    # ========================================================

    def popup(
        self,
        title,
        message,
        icon
    ):

        box = QMessageBox(
            self
        )

        box.setWindowTitle(
            title
        )

        box.setText(
            message
        )

        box.setIcon(
            icon
        )

        box.setStandardButtons(
            QMessageBox.NoButton
        )

        box.setModal(
            False
        )

        self.active_popups.append(
            box
        )

        timer = QTimer(
            box
        )

        timer.setSingleShot(
            True
        )

        def close():

            if box in self.active_popups:

                self.active_popups.remove(
                    box
                )

            box.close()

            box.deleteLater()

        timer.timeout.connect(
            close
        )

        box.show()

        box.raise_()

        box.activateWindow()

        timer.start(
            self.popup_timeout * 1000
        )

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event
    ):

        # IMPORTANT FOR THE MULTI-DEVICE VERSION:
        # Closing the admin PC must NOT end mobile-created or global sessions.
        # Firebase remains authoritative and sessions continue while this PC is
        # offline. We only close this desktop client's realtime stream.
        try:
            if self.firebase_listener is not None:
                self.firebase_listener.close()
                self.firebase_listener = None
        except Exception as e:
            print("[FIREBASE LISTENER CLOSE ERROR]", e)

        event.accept()


# ============================================================
# STYLE
# ============================================================

STYLE = """

QMainWindow {
    background: #0F172A;
}

QWidget {
    color: #E5E7EB;
    font-family: "Segoe UI";
    font-size: 14px;
}

QDialog {
    background: #111827;
}

#sidebar {
    background: #0B1220;
    border-right: 1px solid #273244;
}

#logo {
    color: #60A5FA;
    font-size: 27px;
    font-weight: bold;
    padding: 20px;
}

#title {
    color: #F8FAFC;
    font-size: 26px;
    font-weight: bold;
    padding: 10px;
}

#scanner_instruction {
    color: #60A5FA;
    font-size: 25px;
    font-weight: bold;
    padding: 12px;
}

#scanner_state {
    color: #94A3B8;
    padding: 8px;
}

#event_count {
    background: #111827;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 12px;
    color: #22C55E;
    font-size: 17px;
    font-weight: bold;
}

#empty_events {
    color: #64748B;
    font-size: 17px;
    padding: 40px;
}

#event_card {
    background: #172033;
    border: 1px solid #334155;
    border-left: 5px solid #22C55E;
    border-radius: 12px;
    padding: 10px;
    margin: 5px;
}

#event_title {
    color: #F8FAFC;
    font-size: 19px;
    font-weight: bold;
}

#event_active {
    color: #22C55E;
    font-weight: bold;
}

#event_label {
    color: #94A3B8;
    font-weight: bold;
}

#event_value {
    color: #F8FAFC;
    font-weight: 600;
}

#event_time {
    color: #60A5FA;
    font-size: 16px;
    font-weight: bold;
    padding: 8px;
}

#reader_status {
    color: #22C55E;
    padding: 12px;
}

QPushButton {
    background: #1E293B;
    color: #E5E7EB;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background: #334155;
}

#primary_button {
    background: #2563EB;
    color: white;
    border: none;
}

#primary_button:hover {
    background: #3B82F6;
}

#danger_button {
    background: #991B1B;
    color: white;
    border: none;
}

#danger_button:hover {
    background: #DC2626;
}

QLineEdit {
    background: #1E293B;
    color: #F8FAFC;
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 10px;
}

QComboBox {
    background: #1E293B;
    color: #F8FAFC;
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 10px;
}

QComboBox QAbstractItemView {
    background: #1E293B;
    color: #F8FAFC;
    selection-background-color: #2563EB;
}

QSpinBox {
    background: #1E293B;
    color: #F8FAFC;
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 10px;
}

QCheckBox {
    padding: 10px;
    font-size: 15px;
}

QTableWidget {
    background: #111827;
    alternate-background-color: #172033;
    color: #E5E7EB;
    border: 1px solid #334155;
    gridline-color: #273244;
    border-radius: 8px;
}

QHeaderView::section {
    background: #1E293B;
    color: #CBD5E1;
    padding: 12px;
    border: none;
    font-weight: bold;
}

QGroupBox {
    background: #111827;
    border: 1px solid #334155;
    border-radius: 10px;
    margin-top: 12px;
    padding: 15px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 15px;
    padding: 0 8px;
    color: #60A5FA;
}

QScrollArea {
    border: none;
    background: #111827;
}

"""


# ============================================================
# START QR SERVER
# ============================================================

def start_qr_server():

    thread = threading.Thread(
        target=qr_server.run_server,
        daemon=True
    )

    thread.start()


# ============================================================
# MAIN
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "RFID Rickshaw Management System"
    )

    app.setStyleSheet(
        STYLE
    )

    database.init_database()

    start_qr_server()

    window = MainWindow()

    window.show()

    window.show_dashboard()

    sys.exit(
        app.exec()
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()