"""Entry point for the self-contained Windows executable."""

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path


def main():
    cache_root = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_CACHE_HOME")
        or str(Path.home() / ".cache")
    )
    cache = Path(cache_root) / "NetGAF"
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        cache = Path(tempfile.mkdtemp(prefix="netgaf-"))
    os.environ.setdefault("MPLCONFIGDIR", str(cache / "matplotlib"))
    # Windowed executables have no console streams; some dependencies expect them.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    smoke = len(sys.argv) == 3 and sys.argv[1] == "--smoke-test"
    try:
        if smoke:
            from netgaf.frozen_check import run

            run(Path(sys.argv[2]))
            return 0
        from netgaf.gui import main as desktop

        return desktop()
    except Exception:
        details = traceback.format_exc()
        (cache / "startup.log").write_text(details, encoding="utf-8")
        if smoke:
            output = Path(sys.argv[2])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"ok": False, "error": details}), encoding="utf-8")
        elif sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"Не удалось запустить NetGAF. Журнал: {cache / 'startup.log'}",
                "NetGAF",
                0x10,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
