import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .capture import CaptureStats
from .model import Detector, Result


def utc_time(nanoseconds: int):
    return datetime.fromtimestamp(nanoseconds / 1e9, timezone.utc).isoformat(
        timespec="milliseconds"
    )


def export_json(path: str | Path, results: list[Result], detector: Detector, stats: CaptureStats):
    payload = {
        "application": "NetGAF 0.1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "time_basis": "UTC; intervals [start, end)",
        "config": detector.config.to_dict(),
        "scaler": detector.scaler.to_dict(),
        "model": detector.metadata,
        "capture_stats": asdict(stats),
        "summary": {"windows": len(results), "flagged": sum(r.anomalous for r in results)},
        "results": [
            dict(
                r.to_dict(),
                start_utc=utc_time(r.window.start_ns),
                end_utc=utc_time(r.window.end_ns),
            )
            for r in results
        ],
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def export_csv(path: str | Path, results: list[Result]):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "source",
                "node",
                "start_utc",
                "end_utc",
                "mse",
                "threshold",
                "anomalous",
                "below_range_per_channel",
                "above_range_per_channel",
                "max_excess_per_channel",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    Path(result.window.source).name,
                    result.window.node,
                    utc_time(result.window.start_ns),
                    utc_time(result.window.end_ns),
                    result.score,
                    result.threshold,
                    int(result.anomalous),
                    json.dumps(result.below),
                    json.dumps(result.above),
                    json.dumps(result.excess),
                ]
            )
