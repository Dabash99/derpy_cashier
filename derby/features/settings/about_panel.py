"""The "عن البرنامج" (About) settings tab: logo, app name, version, data
folder path, and font/icon license notes -- Part A3 of the brand/UI
refresh. No business logic; pure read-only display.
"""
from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QVBoxLayout, QWidget

import derby
from derby.core.i18n import ar
from derby.core.theme import icons
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

        layout.addStretch(1)
