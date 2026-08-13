#define AppName "DIGI Express Admin"
#define AppVersion "1.0.0"
#define AppPublisher "DIGI Express"
#define AppExeName "DIGI Express Admin.exe"

[Setup]
AppId={{890AE9BF-E4E0-4F14-96B1-7C93EB7ABF7C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppPublisher}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=DIGI-Express-Admin-Setup
SetupIconFile=..\assets\digi_express.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x86compatible x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Files]
Source: "staging\x64\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion; Check: IsWin64
Source: "staging\x86\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion; Check: not IsWin64
Source: "downloads\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: IsWin64 and WebView2NeedsInstall
Source: "downloads\MicrosoftEdgeWebView2RuntimeInstallerX86.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: (not IsWin64) and WebView2NeedsInstall

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; Flags: waituntilterminated; Check: IsWin64 and WebView2NeedsInstall
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX86.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; Flags: waituntilterminated; Check: (not IsWin64) and WebView2NeedsInstall
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2ClientId = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2InRoot(RootKey: Integer): Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId;
  Result := RegQueryStringValue(RootKey, Key, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2NeedsInstall: Boolean;
begin
  Result := not (
    HasWebView2InRoot(HKLM32) or
    HasWebView2InRoot(HKCU32) or
    (IsWin64 and HasWebView2InRoot(HKLM64)) or
    (IsWin64 and HasWebView2InRoot(HKCU64))
  );
end;
