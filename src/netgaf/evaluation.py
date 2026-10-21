"""Explicitly synthetic demo evaluation; no test-time threshold selection."""

import json
from pathlib import Path

import numpy as np

from .capture import check_cancelled, read_capture
from .model import analyze

SCENARIO_NAMES = {
    "packet_burst.pcap": "Всплеск числа пакетов",
    "byte_surge.pcap": "Рост объёма передачи",
    "port_diversity.pcap": "Рост разнообразия портов",
    "mixed.pcap": "Три сценария последовательно",
}


def binary_metrics(labels, scores, threshold):
    labels = np.asarray(labels)
    scores = np.asarray(scores, dtype=float)
    if (
        labels.ndim != 1
        or scores.shape != labels.shape
        or len(labels) == 0
        or not np.isin(labels, [0, 1]).all()
        or not np.isfinite(scores).all()
        or not np.isfinite(threshold)
    ):
        raise ValueError("Нужны бинарные метки и конечные оценки одинаковой ненулевой длины.")
    labels = labels.astype(bool)
    predicted = scores > threshold
    tp = int((labels & predicted).sum())
    fp = int((~labels & predicted).sum())
    tn = int((~labels & ~predicted).sum())
    fn = int((labels & ~predicted).sum())

    def divide(a, b):
        return a / b if b else None

    metrics = {
        "windows": len(labels),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": divide(tp, tp + fp),
        "recall": divide(tp, tp + fn),
        "f1": divide(2 * tp, 2 * tp + fp + fn),
        "fpr": divide(fp, fp + tn),
        "pr_auc": None,
        "average_precision": None,
    }
    if labels.any():
        order = np.argsort(-scores, kind="stable")
        sorted_labels, sorted_scores = labels[order], scores[order]
        last = np.r_[np.flatnonzero(np.diff(sorted_scores)), len(labels) - 1]
        true_positives = np.cumsum(sorted_labels)[last]
        precision = np.r_[1.0, true_positives / (last + 1)]
        recall = np.r_[0.0, true_positives / labels.sum()]
        metrics["pr_auc"] = float(np.trapezoid(precision, recall))
        metrics["average_precision"] = float(np.sum(np.diff(recall) * precision[1:]))
    return metrics


def evaluate_demo(directory, detector, progress=lambda _: None, cancel=None):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "labels.json").read_text(encoding="utf-8"))
    if manifest.get("synthetic") is not True:
        raise ValueError("Эта команда предназначена для синтетического демонстрационного набора.")
    report = {
        "synthetic": True,
        "note": "Functional scenarios only; not evidence of quality on real network traffic.",
        "label_rule": "any positive-duration overlap; [start, end) UTC",
        "threshold": detector.threshold,
        "config": detector.config.to_dict(),
        "scenarios": {},
    }
    for filename, title in SCENARIO_NAMES.items():
        check_cancelled(cancel)
        capture = read_capture(directory / filename, detector.config, progress, cancel)
        results = analyze(capture, detector, progress, cancel)
        intervals = manifest["scenarios"][filename]
        labels = [
            int(
                r.window.node == manifest["node"]
                and any(
                    r.window.start_ns < interval["end_ns"]
                    and r.window.end_ns > interval["start_ns"]
                    for interval in intervals
                )
            )
            for r in results
        ]
        metrics = binary_metrics(labels, [r.score for r in results], detector.threshold)
        report["scenarios"][filename] = dict(metrics, title=title)
        progress(f"{title}: TP={metrics['tp']}, FP={metrics['fp']}, FN={metrics['fn']}")
    return report
