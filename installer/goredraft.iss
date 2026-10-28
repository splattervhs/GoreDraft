; Inno Setup script for GORE DRAFT (Windows installer)
; Build:  iscc /DAppVersion=0.2.0 installer\goredraft.iss
; Expects PyInstaller output in dist\GoreDraft\

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{6E7C2F1A-9B3D-4C55-A0D2-60D2E1F0B7A1}
AppName=GORE DRAFT
AppVersion={#AppVersion}
AppVerName=GORE DRAFT {#AppVersion} beta
AppPublisher=Splatter VHS
DefaultDirName={autopf}\GORE DRAFT
DefaultGroupName=GORE DRAFT
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=GoreDraft-Setup-{#AppVersion}-beta
SetupIconFile=..\goredraft\icon.ico
UninstallDisplayIcon={app}\GoreDraft.exe
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; per-user install is allowed so testers without admin rights can install
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "assoc"; Description: "Open .goredraft projects with GORE DRAFT"; GroupDescription: "Files:"

[Files]
Source: "..\dist\GoreDraft\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\GORE DRAFT"; Filename: "{app}\GoreDraft.exe"
Name: "{group}\Uninstall GORE DRAFT"; Filename: "{uninstallexe}"
Name: "{autodesktop}\GORE DRAFT"; Filename: "{app}\GoreDraft.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.goredraft"; ValueType: string; ValueName: ""; ValueData: "GoreDraft.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GoreDraft.Project"; ValueType: string; ValueName: ""; ValueData: "GORE DRAFT Project"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GoreDraft.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\GoreDraft.exe,0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GoreDraft.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GoreDraft.exe"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\GoreDraft.exe"; Description: "Launch GORE DRAFT"; Flags: nowait postinstall skipifsilent
