import csv
import json

import numpy as np
import pytest

from netgaf.model import analyze, load_detector, save_detector
from netgaf.reports import export_csv, export_json


def test_training_serialization_inference_and_reports(trained, tmp_path):
    detector, capture = trained
    assert detector.metadata["train_windows"] > 0
    assert detector.metadata["validation_windows"] > 0
    assert np.isfinite(detector.threshold) and detector.threshold > 0
    before = analyze(capture, detector)
    path = tmp_path / "model.ngaf"
    save_detector(detector, path)
    loaded = load_detector(path)
    after = analyze(capture, loaded)
    assert len(after) > 0
    np.testing.assert_array_equal([r.score for r in before], [r.score for r in after])
    report = tmp_path / "report.json"
    export_json(report, after, loaded, capture.stats)
    data = json.loads(report.read_text())
    assert data["summary"]["windows"] == len(after)
    assert data["results"][0]["end_ns"] > data["results"][0]["start_ns"]
    assert data["model"]["seed"] == 42
    csv_path = tmp_path / "report.csv"
    export_csv(csv_path, after)
    with csv_path.open(encoding="utf-8-sig") as output:
        assert len(list(csv.DictReader(output))) == len(after)


def test_invalid_model_is_rejected(tmp_path):
    path = tmp_path / "broken.ngaf"
    path.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="модель"):
        load_detector(path)
