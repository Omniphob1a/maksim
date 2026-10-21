# Windows installer build

GitHub Actions builds on Windows Server 2022 with the pinned uv.lock dependencies.
PyInstaller freezes the application, CPU PyTorch, Qt, the user guide and the
pretrained synthetic demonstration. Inno Setup makes a per-user installer,
Start Menu / desktop shortcuts and an uninstaller. No Python installation is
needed on the user's PC.

The workflow runs Windows tests, the actual frozen binary and an installed copy
in a directory with spaces and Cyrillic characters. Those checks exercise the
GUI example, all demonstration scenarios, one training epoch, model reload and
CSV/JSON exports. It also checks uninstallation before publishing a release.
Any failed check prevents release publication.

Microsoft's app-local VC143 runtime DLLs are taken from the runner's Visual Studio
redistributable directory after verifying their Microsoft Authenticode signatures.
Inno Setup download verification remains enabled if it needs installation.

To build locally on Windows with Python/uv, Visual Studio VC143 redistributables
and Inno Setup 6 available:

```powershell
uv sync --frozen --extra dev --extra build
.\packaging\windows\build.ps1
```

Installer output: `artifacts/windows/NetGAF-Setup-0.2.0-x64.exe`.
The Windows installer workflow publishes a commit-specific GitHub release after
verification, with HTML/TXT guides and SHA256SUMS.txt. The installer is unsigned.
