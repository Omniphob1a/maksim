$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectRoot
try {
    & uv run --frozen python packaging/prepare_installer.py
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage installer resources.' }
    & uv run --frozen pyinstaller --clean --noconfirm --log-level WARN --distpath artifacts/frozen --workpath artifacts/pyinstaller packaging/windows/netgaf.spec 2>&1 | Tee-Object -FilePath artifacts/pyinstaller.log
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed. See artifacts/pyinstaller.log.' }

    # Bundle the signed, redistributable MSVC runtime app-locally.
    # A clean user PC must not depend on Visual Studio being installed.
    $runtimePattern = Join-Path ${env:ProgramFiles} 'Microsoft Visual Studio\2022\*\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT'
    $runtime = Get-ChildItem -Path $runtimePattern -Directory |
        Sort-Object { [version](Split-Path (Split-Path (Split-Path $_.FullName -Parent) -Parent) -Leaf) } -Descending |
        Select-Object -First 1
    if (-not $runtime) { throw 'The Microsoft VC143 redistributable directory was not found.' }
    foreach ($library in Get-ChildItem -LiteralPath $runtime.FullName -Filter '*.dll') {
        $signature = Get-AuthenticodeSignature -LiteralPath $library.FullName
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft*') {
            throw "Microsoft runtime signature verification failed: $($library.Name)"
        }
        Copy-Item -LiteralPath $library.FullName -Destination 'artifacts/frozen/NetGAF/_internal/' -Force
    }

    $compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    if (-not (Test-Path -LiteralPath $compiler)) {
        & choco install innosetup --yes --no-progress
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup installation failed.' }
    }
    if (-not (Test-Path -LiteralPath $compiler)) { throw 'Inno Setup compiler not found.' }
    $version = (& uv run --frozen python -c 'from netgaf import __version__; print(__version__)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot determine application version.' }
    $appSource = (Resolve-Path 'artifacts/frozen/NetGAF').Path
    $outputPath = Join-Path $projectRoot 'artifacts/windows'
    New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
    & $compiler "/DAppVersion=$version" "/DAppSource=$appSource" "/DOutputPath=$outputPath" packaging/windows/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    Copy-Item src/netgaf/assets/user-guide.html (Join-Path $outputPath 'NetGAF-Instruction.html')
    Copy-Item src/netgaf/assets/user-guide.txt (Join-Path $outputPath 'NetGAF-Instruction.txt')
}
finally {
    Pop-Location
}
