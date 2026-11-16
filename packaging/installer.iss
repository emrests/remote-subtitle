; Inno Setup 6 kurulum betiği. Derleme: packaging/build.ps1
#define AppName "remote-subtitle"
#define AppVersion "0.1.0"
#define Port "8765"

[Setup]
AppId={{6B7C2E1A-5D7F-4C8E-9A1B-2F3D4E5A6B7C}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=remote-subtitle-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\remote-subtitle.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "startup"; Description: "Windows ile başlat"; GroupDescription: "Ek seçenekler:"
Name: "desktopicon"; Description: "Masaüstüne kısayol koy"; GroupDescription: "Ek seçenekler:"

[Files]
Source: "..\dist\remote-subtitle\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "vendor\OllamaSetup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not OllamaInstalled

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\remote-subtitle.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\remote-subtitle.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\remote-subtitle.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
; 1) Ollama (yerel çeviri motoru) — yoksa sessiz kurulum
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES"; \
  StatusMsg: "Çeviri motoru (Ollama) kuruluyor..."; Check: not OllamaInstalled; Flags: waituntilterminated
; 2) Windows İngilizce OCR dil paketi
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Add-WindowsCapability -Online -Name 'Language.OCR~~~en-US~0.0.1.0'"""; \
  StatusMsg: "İngilizce metin tanıma paketi yükleniyor..."; Flags: runhidden waituntilterminated
; 3) TV'nin bağlanabilmesi için güvenlik duvarı kuralı (özel ve ortak ağ; ev Wi-Fi sık sık "ortak" sayılır)
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow protocol=TCP localport={#Port} profile=private,public"; \
  StatusMsg: "Güvenlik duvarı izni ekleniyor..."; Flags: runhidden waituntilterminated
; Son sayfa
Filename: "https://github.com/chiaki-ng/chiaki-ng/releases"; Description: "chiaki-ng'yi (Remote Play) indirme sayfasını aç"; \
  Flags: postinstall shellexec skipifsilent unchecked
Filename: "{app}\remote-subtitle.exe"; Description: "remote-subtitle'ı başlat"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; RunOnceId: "fw"

[Code]
function OllamaInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
         or FileExists(ExpandConstant('{autopf}\Ollama\ollama.exe'));
end;
