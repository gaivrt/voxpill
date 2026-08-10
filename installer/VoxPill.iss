#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef BundleDir
  #define BundleDir "..\dist\VoxPill"
#endif

#define AppName "VoxPill"
#define AppPublisher "GAIVR"
#define AppExeName "VoxPill.exe"

[Setup]
AppId={{A8B991A3-F44B-4FD4-BEC7-359F83B4170A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=Local\GAIVR.VoxPill
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\voxpill.ico
OutputDir=..\dist\release
OutputBaseFilename=VoxPill-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#SourcePath}\languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "登录 Windows 时自动启动 VoxPill"; GroupDescription: "启动选项："; Flags: checkedonce

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{userstartup}\VoxPill.lnk"
Type: files; Name: "{userstartup}\start-voicekey-hidden.vbs.lnk"

[Icons]
Name: "{autoprograms}\VoxPill"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "离线语音输入"
Name: "{userstartup}\VoxPill"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 VoxPill"; Flags: nowait postinstall skipifsilent
