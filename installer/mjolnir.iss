#define MyAppName "Plethora Mjolnir"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "Plethora Labs"
#define MyAppURL "https://github.com/Om12-0/plethora-mjolnir"
#define MyAppExeName "mjolnir.exe"

[Setup]
AppId={{9B78D14E-462B-4A47-BCE0-1F2B565860E8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=Plethora-Mjolnir-Setup-2.2.0
OutputDir=..\dist-installer
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
SetupIconFile=..\assets\icon.ico

[Files]
Source: "..\dist\mjolnir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\icon.png"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"

[Run]
; 1. Install & start the Everything Service as SYSTEM during installation
Filename: "{app}\_internal\bin\Everything.exe"; Parameters: "-install-service"; Flags: runhidden waituntilterminated
Filename: "{app}\_internal\bin\Everything.exe"; Parameters: "-start-service"; Flags: runhidden waituntilterminated

; 2. Launch Mjolnir as standard user post-install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall runascurrentuser skipifsilent

[UninstallRun]
; Stop & uninstall the service cleanly on uninstall
Filename: "{app}\_internal\bin\Everything.exe"; Parameters: "-stop-service"; Flags: runhidden waituntilterminated
Filename: "{app}\_internal\bin\Everything.exe"; Parameters: "-uninstall-service"; Flags: runhidden waituntilterminated
