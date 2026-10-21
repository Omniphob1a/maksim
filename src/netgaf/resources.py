"""Installed user guide and optional packaged demonstration data."""

import sys
from pathlib import Path


def user_guide() -> Path:
    return Path(__file__).resolve().parent / "assets" / "user-guide.html"


def find_demo_directory() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "artifacts" / "installer-resources" / "demo",
        root / "artifacts" / "scenarios",
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys._MEIPASS) / "demo")
    for candidate in candidates:
        if all(
            (candidate / name).is_file() for name in ("model.ngaf", "normal.pcap", "mixed.pcap")
        ):
            return candidate
    return None
