#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef AppSource
  #define AppSource "..\..\artifacts\frozen\NetGAF"
#endif
#ifndef OutputPath
  #define OutputPath "..\..\artifacts\windows"
#endif

[Setup]
AppId={{A56A22B1-0699-4EB5-A721-5A1B1F1DC205}
AppName=NetGAF
AppVersion={#AppVersion}
AppPublisher=NetGAF
AppPublisherURL=https://github.com/Omniphob1a/maksim
DefaultDirName={localappdata}\Programs\NetGAF
DefaultGroupName=NetGAF
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=NetGAF-Setup-{#AppVersion}-x64
Compression=lzma2/normal
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2
WizardStyle=modern
UninstallDisplayIcon={app}\NetGAF.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\src\netgaf\assets\user-guide.html"; DestDir: "{app}"; DestName: "Инструкция.html"; Flags: ignoreversion
Source: "..\..\src\netgaf\assets\user-guide.txt"; DestDir: "{app}"; DestName: "Инструкция.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\NetGAF"; Filename: "{app}\NetGAF.exe"; WorkingDir: "{userdocs}"
Name: "{group}\Инструкция"; Filename: "{app}\Инструкция.html"
Name: "{userdesktop}\NetGAF"; Filename: "{app}\NetGAF.exe"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\NetGAF.exe"; Description: "Запустить NetGAF"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Инструкция.html"; Description: "Открыть инструкцию"; Flags: shellexec postinstall skipifsilent unchecked
