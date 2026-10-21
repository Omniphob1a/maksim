"""Functional check used on the frozen binary and the installed application."""

import json
import os
import platform
import sys
import time
from pathlib import Path


def run(output: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .capture import read_capture
    from .evaluation import evaluate_demo
    from .gui import STYLE, MainWindow
    from .model import analyze, load_detector, save_detector, train_detector
    from .reports import export_csv, export_json
    from .resources import find_demo_directory, user_guide

    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    errors = []
    window.error = errors.append
    window.show()
    try:
        window.example_button.click()
        deadline = time.monotonic() + 120
        while window._thread is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert window._thread is None, "Example loading timed out"
        assert not errors, errors
        assert window.results and len(window.results) == 39, "Bundled example did not execute"
        assert len(window.images_plot.figure.axes) == 6, "GAF/reconstruction plots missing"
        assert user_guide().is_file() and user_guide().with_suffix(".txt").is_file()
        directory = find_demo_directory()
        normal = read_capture(directory / "normal.pcap", window.detector.config)
        trained = train_detector([normal], window.detector.config, epochs=1)
        saved = output.parent / "smoke-trained.ngaf"
        save_detector(trained, saved)
        loaded = load_detector(saved)
        before = analyze(normal, trained)
        after = analyze(normal, loaded)
        np.testing.assert_array_equal([r.score for r in before], [r.score for r in after])
        export_json(
            output.parent / "smoke-report.json",
            window.results,
            window.detector,
            window.capture.stats,
        )
        export_csv(output.parent / "smoke-report.csv", window.results)
        scenarios = evaluate_demo(directory, window.detector)
        assert len(scenarios["scenarios"]) == 4
        assert all(r["windows"] == 39 for r in scenarios["scenarios"].values())
        window.grab().save(str(output.parent / "desktop.png"))
        output.write_text(
            json.dumps(
                {
                    "ok": True,
                    "version": __version__,
                    "platform": platform.platform(),
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "windows_analyzed": len(window.results),
                    "training_windows": trained.metadata["train_windows"],
                    "validation_windows": trained.metadata["validation_windows"],
                    "scenarios": scenarios["scenarios"],
                    "guide_included": True,
                    "model_reload_identical": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        window.close()
        app.processEvents()
