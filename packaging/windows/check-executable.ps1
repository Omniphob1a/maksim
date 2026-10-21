param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$Result
)
$ErrorActionPreference = 'Stop'
$resultParent = Split-Path $Result -Parent
New-Item -ItemType Directory -Force -Path $resultParent | Out-Null
$process = Start-Process -FilePath $Executable -ArgumentList @('--smoke-test', ('"' + $Result + '"')) -PassThru
if (-not $process.WaitForExit(240000)) {
    $process.Kill()
    throw 'Application check exceeded four minutes.'
}
if ($process.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $Result) {
        $details = Get-Content -LiteralPath $Result -Raw
        Write-Output $details
        $message = $details.Replace('%','%25').Replace("`r",'%0D').Replace("`n",'%0A')
        Write-Output "::error::$message"
    }
    throw "Application check failed with exit code $($process.ExitCode)."
}
if (-not (Test-Path -LiteralPath $Result)) { throw 'Application did not create a current result file.' }
$report = Get-Content -LiteralPath $Result -Raw | ConvertFrom-Json
if (-not $report.ok -or -not $report.frozen -or $report.windows_analyzed -ne 39) {
    throw 'The frozen application did not complete its functional checks.'
}
Get-Content -LiteralPath $Result -Raw | Write-Output
