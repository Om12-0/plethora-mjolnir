#define MyAppName "Plethora Mjolnir"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Plethora Labs"
#define MyAppURL "https://github.com/Om12-0/plethora-mjolnir"
#define MyAppExeName "mjolnir.exe"

[Setup]
AppId={{9B78D14E-462B-4A47-BCE0-1F2B565860E8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=Plethora-Mjolnir-Setup-2.0.0
OutputDir=..\dist-installer
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\mjolnir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
