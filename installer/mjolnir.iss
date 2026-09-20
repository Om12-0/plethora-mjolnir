#define MyAppName "Plethora Mjolnir"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "Plethora Labs"
#define MyAppURL "https://github.com/plethora/mjolnir"
#define MyAppExeName "mjolnir.exe"
#define MyAppIcon "..\assets\mjolnir.ico"

[Setup]
AppId={{D68F23A1-7B1A-4D4E-906A-87C2189FCB8C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\Plethora Mjolnir
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=Plethora-Mjolnir-Setup-1.0.3
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSmallImageFile=..\assets\wizard_header.bmp
WizardImageFile=..\assets\wizard_sidebar.bmp
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no

[Types]
Name: "full"; Description: "Full installation (Recommended)"
Name: "minimal"; Description: "Minimal installation (Search Core only)"
Name: "custom"; Description: "Custom selection"; Flags: iscustom

[Components]
Name: "core"; Description: "Mjolnir Core (Launcher, Hybrid Vector Indexer & UI)"; Types: full minimal custom; Flags: fixed
Name: "models"; Description: "Offline Embedding Weights (FastEmbed / BGE-small ONNX ~130MB)"; Types: full custom
Name: "clipboard"; Description: "Persistent Clipboard History Daemon & Manager"; Types: full custom
Name: "tools"; Description: "Action Panel Utilities & Sandboxed Math Evaluator"; Types: full custom

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Launch Plethora Mjolnir automatically on Windows startup"; GroupDescription: "System Integration:"

[Files]
; Core binary and foundational libraries
Source: "..\dist\mjolnir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: core
; Pre-cached embedding model weights (optional component)
Source: "..\fastembed_cache\*"; DestDir: "{app}\fastembed_cache"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist; Components: models
; Custom Icon asset
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\mjolnir.ico"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\mjolnir.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\mjolnir.ico"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "ui"; IconFilename: "{app}\assets\mjolnir.ico"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
