# Kurulum dosyasını üretir: packaging\Output\remote-subtitle-setup.exe
# Gerekenler: Python + requirements.txt, PyInstaller, Inno Setup 6 (winget install JRSoftware.InnoSetup)
# Ollama gömülmez; kurulum sihirbazı eksikse kurulum sırasında indirir.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# TV kurulumu için sdb (Tizen'in TV aracı, Apache-2.0). Kurulu Tizen Studio'dan alınır; yoksa kurulum paketi
# TV'ye kurmayı yalnız Tizen Studio'su olan bilgisayarda yapabilir.
$sdb = "$env:SystemDrive\tizen-studio\tools\sdb.exe"
if (Test-Path $sdb) { New-Item -ItemType Directory -Force packaging\vendor\sdb | Out-Null; Copy-Item $sdb packaging\vendor\sdb\ -Force }
else { Write-Warning "sdb.exe bulunamadı ($sdb): kurulum paketi sdb içermeyecek" }

python -m PyInstaller packaging\rsub.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız" }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 bulunamadı: winget install JRSoftware.InnoSetup" }
& $iscc (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup başarısız" }
Write-Host "Hazır: packaging\Output\remote-subtitle-setup.exe"
