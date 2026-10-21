"""Stage verified demo files and notices; never execute code from an archive."""

import shutil
import sys
from importlib.metadata import distribution
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "artifacts" / "installer-resources"
DEMO_FILES = (
    "normal.pcap",
    "mixed.pcap",
    "packet_burst.pcap",
    "byte_surge.pcap",
    "port_diversity.pcap",
    "labels.json",
    "model.ngaf",
    "evaluation.json",
)


def main():
    demo = STAGE / "demo"
    demo.mkdir(parents=True, exist_ok=True)
    with ZipFile(ROOT / "downloads" / "NetGAF-source.zip") as archive:
        for filename in DEMO_FILES:
            member = f"maksim/artifacts/scenarios/{filename}"
            data = archive.read(member)  # ZipFile also verifies each member's CRC.
            (demo / filename).write_bytes(data)
    notices = STAGE / "third-party-licenses"
    notices.mkdir(parents=True, exist_ok=True)
    for name in ("torch", "PySide6-Essentials", "shiboken6", "numpy", "matplotlib", "scapy"):
        installed = distribution(name)
        for entry in installed.files or []:
            if ".." in entry.parts or not any(
                "license" in part.lower() or "copying" in part.lower() for part in entry.parts
            ):
                continue
            source = Path(installed.locate_file(entry))
            if source.is_file():
                target = notices / name / Path(*entry.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    for filename in ("LICENSE.txt", "LICENSE"):
        source = Path(sys.base_prefix) / filename
        if source.is_file():
            shutil.copyfile(source, notices / "Python-LICENSE.txt")
            break
    print(f"Installer resources staged in {STAGE}")


if __name__ == "__main__":
    main()
