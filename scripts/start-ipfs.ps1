$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$env:IPFS_PATH = Join-Path $projectRoot '.data/ipfs'
$ipfsExe = Join-Path $projectRoot '.tools/kubo/ipfs.exe'
if (-not (Test-Path $ipfsExe)) { throw 'Install Kubo into .tools/kubo first; see README.md.' }
if (-not (Test-Path (Join-Path $env:IPFS_PATH 'config'))) {
    & $ipfsExe init --profile=test
    if ($LASTEXITCODE -ne 0) { throw 'IPFS initialization failed' }
    & $ipfsExe config Addresses.API /ip4/127.0.0.1/tcp/5001
    & $ipfsExe config Addresses.Gateway /ip4/127.0.0.1/tcp/8080
}
# Offline prevents connecting to public peers; this demo uses real local IPFS storage.
& $ipfsExe daemon --offline
exit $LASTEXITCODE
