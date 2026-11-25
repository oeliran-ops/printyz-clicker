; Inno Setup script for the PRINTYZ Clicker customer edition.
; Built by "Build customer installer.bat" (needs Inno Setup 6: winget install JRSoftware.InnoSetup)
#define AppName "PRINTYZ Clicker"
#define AppVersion "1.0.0"

[Setup]
AppId={{8E3C1B52-6A1F-4C1E-9F3B-2B6A6F0C7A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PRINTYZ
DefaultDirName={autopf}\PRINTYZ Clicker
DefaultGroupName=PRINTYZ
OutputDir=output
OutputBaseFilename=PRINTYZ-Clicker-Setup-{#AppVersion}
SetupIconFile=..\src\printyz_clicker\assets\printyz.ico
UninstallDisplayIcon={app}\PRINTYZ Clicker.exe
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\PRINTYZ Clicker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PRINTYZ Clicker"; Filename: "{app}\PRINTYZ Clicker.exe"
Name: "{autodesktop}\PRINTYZ Clicker"; Filename: "{app}\PRINTYZ Clicker.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PRINTYZ Clicker.exe"; Description: "{cm:LaunchProgram,PRINTYZ Clicker}"; Flags: nowait postinstall skipifsilent
