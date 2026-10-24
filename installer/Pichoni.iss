#ifndef AppVersion
  #error AppVersion is required
#endif

#define MyAppName "Pichoni"
#define MyAppVersion AppVersion
#define MyAppPublisher "Pichoni"

[Setup]
AppId={{C4C389B3-A8A7-4ED3-BF6C-A59DF8E2AB19}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Pichoni
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Pichoni-Setup-{#MyAppVersion}
SetupIconFile=..\ui\icono.ico
UninstallDisplayIcon={app}\Pichoni.exe
CloseApplications=force
RestartApplications=no
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\Pichoni.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Pichoni"; Filename: "{app}\Pichoni.exe"; IconFilename: "{app}\Pichoni.exe"
Name: "{autodesktop}\Pichoni"; Filename: "{app}\Pichoni.exe"; IconFilename: "{app}\Pichoni.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Pichoni.exe"; Description: "Abrir Pichoni"; Flags: postinstall nowait skipifsilent
