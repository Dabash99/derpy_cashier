"""The "عن البرنامج" (About) settings tab: logo, app name, version, data
folder path, font/icon license notes, and a button to open the local
error-log folder (Phase 8/B1) -- opening a local folder on this machine
via os.startfile is not a network call, same category as
export_panel.py's "open containing export folder" button; see
tests/test_policy.py's ALLOWED_STARTFILE_OR_BROWSER_FILES.
"""
from __future__ import annotations

import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

import derby
from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.utils import error_log
from derby.core.utils.paths import app_data_dir


class AboutPanel(QWidget):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        logo_label = QLabel()
        logo_label.setPixmap(icons.logo_pixmap("transparent", 160))
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        name_label = QLabel(ar.ABOUT_APP_NAME)
        name_label.setProperty("role", "title")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        version_label = QLabel("{0}: {1}".format(ar.ABOUT_VERSION_LABEL, derby.__version__))
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        data_folder_label = QLabel("{0}: {1}".format(ar.ABOUT_DATA_FOLDER_LABEL, app_data_dir()))
        data_folder_label.setAlignment(Qt.AlignCenter)
        data_folder_label.setWordWrap(True)
        layout.addWidget(data_folder_label)

        licenses_title = QLabel(ar.ABOUT_LICENSES_TITLE)
        licenses_title.setProperty("role", "subtitle")
        licenses_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(licenses_title)

        licenses_text = QLabel(ar.ABOUT_LICENSES_TEXT)
        licenses_text.setAlignment(Qt.AlignCenter)
        licenses_text.setWordWrap(True)
        layout.addWidget(licenses_text)

        open_logs_button = QPushButton(ar.SETTINGS_OPEN_LOGS_FOLDER_BUTTON)
        open_logs_button.clicked.connect(self._on_open_logs_folder)
        layout.addWidget(open_logs_button)

        layout.addStretch(1)

    def _on_open_logs_folder(self) -> None:
        folder = error_log.log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # noqa: S606 -- opens Explorer on a local folder, Windows-only
