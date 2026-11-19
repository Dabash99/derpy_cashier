"""The About tab must show the real app version and the real (sandboxed
in tests) data folder path -- not placeholders."""
from __future__ import annotations

from PySide2.QtWidgets import QLabel

import derby
from derby.core.utils.paths import app_data_dir
from derby.features.settings.about_panel import AboutPanel


def test_about_panel_shows_version_and_data_folder(qapp):
    panel = AboutPanel()
    labels = [label.text() for label in panel.findChildren(QLabel)]
    combined = " ".join(labels)
    assert derby.__version__ in combined
    assert str(app_data_dir()) in combined
