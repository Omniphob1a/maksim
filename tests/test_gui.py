import shutil
import time

from PySide6.QtWidgets import QApplication

from netgaf.gui import STYLE, MainWindow
from netgaf.model import save_detector
from netgaf.resources import user_guide


def wait_job(app, window):
    deadline = time.monotonic() + 45
    while window._thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window._thread is None, "GUI job did not complete"
    app.processEvents()


def test_desktop_training_analysis_selection_and_export(monkeypatch, normal_path, tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = MainWindow()
    errors = []
    monkeypatch.setattr(window, "error", errors.append)
    window.show()
    window.files.addItem(str(normal_path))
    window.normal_confirm.setChecked(True)
    window.epochs.setValue(2)
    window.train_button.click()
    wait_job(app, window)
    assert errors == []
    assert window.detector is not None
    assert window.analyze_button.isEnabled()
    # Saved model must also work through the GUI's background loading action.
    model_path = tmp_path / "desktop.ngaf"
    save_detector(window.detector, model_path)
    monkeypatch.setattr(
        "netgaf.gui.QFileDialog.getOpenFileName", lambda *a, **k: (str(model_path), "")
    )
    window.open_model()
    wait_job(app, window)
    window.start_analysis(str(normal_path))
    wait_job(app, window)
    assert errors == []
    assert window.table_model.rowCount() > 0
    assert len(window.images_plot.figure.axes) == 6
    assert window.export_button.isEnabled()
    export_path = tmp_path / "desktop-report.json"
    monkeypatch.setattr(
        "netgaf.gui.QFileDialog.getSaveFileName", lambda *a, **k: (str(export_path), "JSON")
    )
    window.export_button.click()
    assert export_path.is_file()
    window.only_anomalies.setChecked(True)
    app.processEvents()
    assert window.proxy.rowCount() == sum(r.anomalous for r in window.results)
    window.close()
    app.processEvents()


def test_ready_example_and_installed_guide(monkeypatch, trained, normal_path, tmp_path):
    detector, _ = trained
    save_detector(detector, tmp_path / "model.ngaf")
    shutil.copyfile(normal_path, tmp_path / "normal.pcap")
    shutil.copyfile(normal_path, tmp_path / "mixed.pcap")
    monkeypatch.setattr("netgaf.gui.find_demo_directory", lambda: tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    errors = []
    monkeypatch.setattr(window, "error", errors.append)
    window.show()
    window.example_button.click()
    wait_job(app, window)
    assert not errors
    assert window.results and window.detector is not None
    assert window.normal_confirm.isChecked()
    assert window.files.count() == 1
    opened = []
    monkeypatch.setattr(
        "netgaf.gui.QDesktopServices.openUrl", lambda url: opened.append(url.toLocalFile()) or True
    )
    window.open_guide()
    assert opened == [str(user_guide())]
    assert user_guide().is_file() and user_guide().with_suffix(".txt").is_file()
    window.close()
    app.processEvents()
