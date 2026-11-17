# Downloads a copy of the live database (Render + Litestream backup in Backblaze B2) to
# backend\live-copy.sqlite3, for viewing in DB Browser for SQLite.
#
# Run from the project folder:   powershell -ExecutionPolicy Bypass -File scripts\download-live-db.ps1
#
# It asks for the same 5 values you put in Render's Environment tab. They are kept only in this
# PowerShell session, never written to a file. The copy is a snapshot: run the script again to refresh
# it. Editing the copy does not change the live app.
#
# Needs WSL: the server uses Litestream 0.3.13, which has no Windows build, so the Linux build runs
# through WSL (it is downloaded to tools\ the first time).

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw 'WSL is required. Install it with: wsl --install'
}
if (-not (Test-Path tools\litestream)) {
    Write-Host 'Downloading Litestream 0.3.13 (same version as the server)...'
    New-Item -ItemType Directory -Force tools | Out-Null
    Invoke-WebRequest 'https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz' `
        -OutFile tools\litestream.tar.gz -UseBasicParsing
    wsl -e tar -xzf tools/litestream.tar.gz -C tools
    Remove-Item tools\litestream.tar.gz
}

function Ask([string]$name, [string]$hint, [switch]$secret) {
    $current = [Environment]::GetEnvironmentVariable($name)
    if ($current) { return $current }
    if ($secret) {
        $s = Read-Host "$name ($hint)" -AsSecureString
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
    }
    return Read-Host "$name ($hint)"
}

$env:LITESTREAM_BUCKET = Ask 'LITESTREAM_BUCKET' 'bucket name'
$env:LITESTREAM_ENDPOINT = Ask 'LITESTREAM_ENDPOINT' 'e.g. s3.us-east-005.backblazeb2.com'
$env:LITESTREAM_REGION = Ask 'LITESTREAM_REGION' 'e.g. us-east-005'
$env:LITESTREAM_ACCESS_KEY_ID = Ask 'LITESTREAM_ACCESS_KEY_ID' 'keyID'
$env:LITESTREAM_SECRET_ACCESS_KEY = Ask 'LITESTREAM_SECRET_ACCESS_KEY' 'applicationKey' -secret
# Must match DATABASE_PATH on Render; it is only the name the backup is filed under.
$env:DATABASE_PATH = '/tmp/sagemaker.sqlite3'
# Pass these variables through to WSL without putting them on the command line.
$env:WSLENV = 'DATABASE_PATH/u:LITESTREAM_BUCKET/u:LITESTREAM_ENDPOINT/u:LITESTREAM_REGION/u:LITESTREAM_ACCESS_KEY_ID/u:LITESTREAM_SECRET_ACCESS_KEY/u'

$out = 'backend/live-copy.sqlite3'
Remove-Item $out, "$out-shm", "$out-wal" -ErrorAction SilentlyContinue

Write-Host 'Backups found in B2:'
wsl -e ./tools/litestream generations -config backend/litestream.yml /tmp/sagemaker.sqlite3
Write-Host 'Downloading the latest copy...'
wsl -e ./tools/litestream restore -config backend/litestream.yml -o $out /tmp/sagemaker.sqlite3
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) {
    throw 'Restore failed. Check the 5 values, and that the Render log shows Litestream replicating.'
}
Write-Host ''
Write-Host "Done: $(Resolve-Path $out)"
Write-Host 'Open it in DB Browser for SQLite (File > Open Database Read Only).'
