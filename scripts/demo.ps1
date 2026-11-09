$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
function Invoke-Ledger {
    & $pythonExe ledger.py @args
    if ($LASTEXITCODE -ne 0) { throw 'Ledger command failed; see its JSON error above.' }
}
Invoke-Ledger doctor
if (-not (Test-Path 'keys/pipeline.key')) { Invoke-Ledger keygen }
# Authorize once with the README command before running this repeatable demo.
$runName = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$artifactPath = "artifacts/demo-$runName.zip"
$sourcePath = "artifacts/source-$runName"
New-Item -ItemType Directory -Path $sourcePath | Out-Null
Copy-Item examples/sample-app/* $sourcePath
# Distinguishes repeated demonstrations because an artifact can only be registered once.
Set-Content -LiteralPath "$sourcePath/build-id.txt" -Value $runName
Invoke-Ledger register $sourcePath --output $artifactPath --commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Invoke-Ledger verify $artifactPath
Invoke-Ledger tamper-demo $artifactPath
