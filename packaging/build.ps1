# Kurulum dosyasını üretir: packaging\Output\remote-subtitle-setup.exe
# Gerekenler: Python + requirements.txt, PyInstaller, Inno Setup 6 (ISCC.exe)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

python -m PyInstaller packaging\rsub.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız" }

$vendor = Join-Path $PSScriptRoot "vendor"
New-Item -ItemType Directory -Force $vendor | Out-Null
$ollama = Join-Path $vendor "OllamaSetup.exe"
if (-not (Test-Path $ollama)) {
    Write-Host "OllamaSetup.exe indiriliyor..."
    Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $ollama
}

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 bulunamadı: winget install JRSoftware.InnoSetup" }
& $iscc (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup başarısız" }
Write-Host "Hazır: packaging\Output\remote-subtitle-setup.exe"
