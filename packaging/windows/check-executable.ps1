param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$Result
)
$ErrorActionPreference = 'Stop'
$resultParent = Split-Path $Result -Parent
New-Item -ItemType Directory -Force -Path $resultParent | Out-Null
$process = Start-Process -FilePath $Executable -ArgumentList @('--smoke-test', ('"' + $Result + '"')) -Wait -PassThru
if ($process.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $Result) { Get-Content -LiteralPath $Result -Raw | Write-Output }
    throw "Application check failed with exit code $($process.ExitCode)."
}
if (-not (Test-Path -LiteralPath $Result)) { throw 'Application did not create a current result file.' }
$report = Get-Content -LiteralPath $Result -Raw | ConvertFrom-Json
if (-not $report.ok -or -not $report.frozen -or $report.windows_analyzed -ne 39) {
    throw 'The frozen application did not complete its functional checks.'
}
Get-Content -LiteralPath $Result -Raw | Write-Output
