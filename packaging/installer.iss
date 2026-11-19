; Inno Setup 6 kurulum betiği. Derleme: packaging/build.ps1
#define AppName "Remote Subtitle (TR)"
#define AppVersion "0.3.0"
#define Port "8765"

[Setup]
AppId={{6B7C2E1A-5D7F-4C8E-9A1B-2F3D4E5A6B7C}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\remote-subtitle
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
; Uygulama açıkken güncellenirse kurulum önce kapatmasını ister (uygulamanın mutex adı)
AppMutex=remote-subtitle

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "startup"; Description: "Windows ile başlat"; GroupDescription: "Ek seçenekler:"
Name: "desktopicon"; Description: "Masaüstüne kısayol koy"; GroupDescription: "Ek seçenekler:"

[Files]
Source: "..\dist\remote-subtitle\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
; OllamaSetup.exe (~1.9 GB) gömülmez: yalnızca eksikse kurulum sırasında indirilir (aşağıda [Code])

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\remote-subtitle.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\remote-subtitle.exe"; Tasks: desktopicon
; Tüm kullanıcıların Başlangıç klasörü: kurulum başka bir yönetici hesabıyla onaylansa da çalışır, kaldırınca silinir
Name: "{commonstartup}\{#AppName}"; Filename: "{app}\remote-subtitle.exe"; Tasks: startup

[Run]
; 1) Ollama (yerel çeviri motoru) — yoksa sessiz kurulum
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES"; \
  StatusMsg: "Çeviri motoru (Ollama) kuruluyor..."; Check: not OllamaInstalled; Flags: waituntilterminated runasoriginaluser
; 2) TV'nin bağlanabilmesi için güvenlik duvarı kuralı (özel ve ortak ağ; ev Wi-Fi sık sık "ortak" sayılır)
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow protocol=TCP localport={#Port} profile=private,public"; \
  StatusMsg: "Güvenlik duvarı izni ekleniyor..."; Flags: runhidden waituntilterminated
; Son sayfa
Filename: "https://github.com/chiaki-ng/chiaki-ng/releases"; Description: "chiaki-ng'yi (Remote Play) indirme sayfasını aç"; \
  Flags: postinstall shellexec skipifsilent unchecked runasoriginaluser
Filename: "{app}\remote-subtitle.exe"; Description: "{#AppName} uygulamasını başlat"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; RunOnceId: "fw"

[Code]
function OllamaInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
         or FileExists(ExpandConstant('{autopf}\Ollama\ollama.exe'));
end;

var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Çeviri motoru indiriliyor',
    'Ollama bu bilgisayarda yok; indirilip kurulacak (yaklaşık 1,9 GB).', nil);
end;

{ OllamaSetup.exe (~1,9 GB) her kurulumda yeniden inmesin: setup'ın yanındaki ya da önbellekteki kopya kullanılır,
  indirilen kopya önbelleğe alınır. Önbellek kaldırmada silinmez (kaldırıp yeniden kurunca da işe yarasın). }
function CacheFile: String;
begin
  Result := ExpandConstant('{commonappdata}\remote-subtitle\OllamaSetup.exe');
end;

function UsableInstaller(const Path: String): Boolean;
var
  Size: Int64;
begin
  Result := FileExists(Path) and FileSize64(Path, Size) and (Size > 100 * 1024 * 1024);
end;

function CopyFromLocal: Boolean;
var
  Source: String;
begin
  Result := False;
  Source := ExpandConstant('{src}\OllamaSetup.exe');
  if not UsableInstaller(Source) then
    Source := CacheFile;
  if UsableInstaller(Source) then
    Result := CopyFile(Source, ExpandConstant('{tmp}\OllamaSetup.exe'), False);
end;

procedure SaveToCache;
begin
  ForceDirectories(ExtractFileDir(CacheFile));
  CopyFile(ExpandConstant('{tmp}\OllamaSetup.exe'), CacheFile, False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and not OllamaInstalled and not CopyFromLocal then begin
    DownloadPage.Clear;
    DownloadPage.Add('https://ollama.com/download/OllamaSetup.exe', 'OllamaSetup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        SaveToCache;
      except
        if DownloadPage.AbortedByUser then
          Result := False
        else begin
          SuppressibleMsgBox('Ollama indirilemedi: ' + GetExceptionMessage + #13#10 +
            'İnternet bağlantısını kontrol edip tekrar deneyin.', mbCriticalError, MB_OK, IDOK);
          Result := False;
        end;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
