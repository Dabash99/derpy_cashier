"""A reusable CSV/Excel/PDF export row: QFileDialog to pick the target
file (defaulting to Documents\\Derby\\Exports), a background QThread so
the UI never freezes, a progress label, and an "open folder" button once
the file is written. Shared by the Reports, Expenses, and Sales Log
screens so each one only has to supply its own exporter callables.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PySide2.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from derby.core.i18n import ar
from derby.core.utils.paths import default_export_dir
from derby.features.reports.export_worker import ExportWorker


class ExportPanel(QWidget):
    def __init__(self, default_filename_stem: Callable[[], str], parent: QWidget = None) -> None:
        super().__init__(parent)
        self._default_filename_stem = default_filename_stem
        self._exporters = {}  # extension -> (dialog_filter, export_fn(path))
        self._last_folder: Path = None
        self._worker: ExportWorker = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        self._csv_button = QPushButton(ar.EXPORT_CSV_BUTTON)
        self._csv_button.clicked.connect(lambda: self._on_export_clicked("csv"))
        layout.addWidget(self._csv_button)

        self._xlsx_button = QPushButton(ar.EXPORT_XLSX_BUTTON)
        self._xlsx_button.clicked.connect(lambda: self._on_export_clicked("xlsx"))
        layout.addWidget(self._xlsx_button)

        self._pdf_button = QPushButton(ar.EXPORT_PDF_BUTTON)
        self._pdf_button.clicked.connect(lambda: self._on_export_clicked("pdf"))
        layout.addWidget(self._pdf_button)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        self._open_folder_button = QPushButton(ar.EXPORT_OPEN_FOLDER_BUTTON)
        self._open_folder_button.setVisible(False)
        self._open_folder_button.clicked.connect(self._on_open_folder)
        layout.addWidget(self._open_folder_button)

    def set_exporters(self, csv_fn=None, xlsx_fn=None, pdf_fn=None) -> None:
        """Each fn takes one argument (the destination Path) and writes the file."""
        self._exporters = {"csv": csv_fn, "xlsx": xlsx_fn, "pdf": pdf_fn}

    def _on_export_clicked(self, extension: str) -> None:
        export_fn = self._exporters.get(extension)
        if export_fn is None:
            return
        export_dir = default_export_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        suggested = str(export_dir / "{0}.{1}".format(self._default_filename_stem(), extension))
        filters = {"csv": "CSV (*.csv)", "xlsx": "Excel (*.xlsx)", "pdf": "PDF (*.pdf)"}
        titles = {"csv": ar.EXPORT_CSV_BUTTON, "xlsx": ar.EXPORT_XLSX_BUTTON, "pdf": ar.EXPORT_PDF_BUTTON}
        file_path, _filter = QFileDialog.getSaveFileName(self, titles[extension], suggested, filters[extension])
        if not file_path:
            return
        self._start_export(export_fn, Path(file_path))

    def _start_export(self, export_fn, path: Path) -> None:
        self._set_buttons_enabled(False)
        self._open_folder_button.setVisible(False)
        self._status_label.setText(ar.EXPORT_IN_PROGRESS)

        def _run():
            export_fn(path)
            return path

        self._worker = ExportWorker(_run)
        self._worker.finished_ok.connect(self._on_export_done)
        self._worker.finished_error.connect(self._on_export_failed)
        self._worker.start()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._csv_button.setEnabled(enabled)
        self._xlsx_button.setEnabled(enabled)
        self._pdf_button.setEnabled(enabled)

    def _on_export_done(self, path_text: str) -> None:
        self._set_buttons_enabled(True)
        self._status_label.setText(ar.EXPORT_SUCCESS.format(path=path_text))
        self._last_folder = Path(path_text).parent
        self._open_folder_button.setVisible(True)

    def _on_export_failed(self, message: str) -> None:
        self._set_buttons_enabled(True)
        self._status_label.setText(ar.EXPORT_FAILED.format(error=message))

    def _on_open_folder(self) -> None:
        if self._last_folder is not None and hasattr(os, "startfile"):
            os.startfile(str(self._last_folder))  # noqa: S606 -- opens Explorer on a local folder, Windows-only
