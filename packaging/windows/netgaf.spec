# PyInstaller must run on Windows to produce a native Windows executable.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).resolve().parents[1]
resources = root / "artifacts" / "installer-resources"
a = Analysis(
    [str(root / "packaging" / "windows" / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=collect_data_files("netgaf") + [
        (str(resources / "demo"), "demo"),
        (str(resources / "third-party-licenses"), "third-party-licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["QtAgg"]}},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "notebook", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="NetGAF", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="NetGAF")
