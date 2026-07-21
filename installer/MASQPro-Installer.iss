;=============================================================================
; MASQPro Installer (Minimal Bootstrap)
;=============================================================================

#define MyAppName "MASQPro"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Masquerena's Club"
#define MyAppURL "https://github.com/zedja123/MASQPro"
#define MyAppExeName "MASQPro.exe"

[Setup]

AppId={{A38A94F4-B0A6-43A8-8A5F-9F25A9B0F7B1}

AppName={#MyAppName}
AppVersion={#MyAppVersion}

AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={sd}\MASQPro
DefaultGroupName=MASQPro

OutputDir=Output
OutputBaseFilename=MASQProSetup

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

PrivilegesRequired=admin

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

SetupIconFile=masqpro.ico
UninstallDisplayIcon={app}\MASQPro.exe

CloseApplications=yes
CloseApplicationsFilter=MASQPro.exe

DisableProgramGroupPage=yes

UsePreviousAppDir=yes
UsePreviousLanguage=yes
UsePreviousTasks=yes

[Languages]

Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]

Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

[Dirs]

Name: "{app}"
Name: "{app}\config"
Name: "{app}\textures"
Name: "{app}\fonts"

[Files]

;=====================================================
; Release
;=====================================================

Source: "..\bin\release\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]

Name: "{group}\MASQPro"; Filename: "{app}\MASQPro.exe"

Name: "{autodesktop}\MASQPro"; Filename: "{app}\MASQPro.exe"; Tasks: desktopicon

[Run]

Filename: "{app}\MASQPro.exe"; \
Description: "Executar MASQPro"; \
Flags: postinstall nowait skipifsilent