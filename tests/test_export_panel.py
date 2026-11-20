"""Drives the real ExportPanel widget, including its background
QThread -- waited for explicitly (worker.wait()) and then flushed with
processEvents() instead of running a real event loop."""
from __future__ import annotations

from pathlib import Path

from PySide2.QtWidgets import QApplication, QFileDialog

from derby.features.reports.export_panel import ExportPanel


def _flush_events(times=20):
    for _ in range(times):
        QApplication.processEvents()


def test_csv_export_succeeds_and_shows_open_folder_button(qapp, tmp_path, monkeypatch):
    target = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))

    written = []

    def _csv_fn(path: Path) -> None:
        path.write_text("hello", encoding="utf-8")
        written.append(path)

    panel = ExportPanel(lambda: "تقرير")
    panel.set_exporters(csv_fn=_csv_fn)
    panel._on_export_clicked("csv")

    assert panel._worker is not None
    panel._worker.wait(2000)
    _flush_events()

    assert written == [target]
    assert target.read_text(encoding="utf-8") == "hello"
    assert panel._open_folder_button.isHidden() is False
    assert "تم التصدير" in panel._status_label.text()


def test_export_failure_shows_error_message(qapp, tmp_path, monkeypatch):
    target = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))

    def _failing_fn(path: Path) -> None:
        raise ValueError("بيانات غير صالحة")

    panel = ExportPanel(lambda: "تقرير")
    panel.set_exporters(csv_fn=_failing_fn)
    panel._on_export_clicked("csv")
    panel._worker.wait(2000)
    _flush_events()

    assert "بيانات غير صالحة" in panel._status_label.text()
    assert panel._csv_button.isEnabled() is True


def test_cancelling_the_file_dialog_does_nothing(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    panel = ExportPanel(lambda: "تقرير")
    panel.set_exporters(csv_fn=lambda path: path.write_text("x"))
    panel._on_export_clicked("csv")
    assert panel._worker is None
