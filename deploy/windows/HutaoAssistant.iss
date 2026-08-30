#define AppName "HuTao Assistant"
#define AppVersion "0.2.0"
#define AppPublisher "HutaoChatCore"
#define AppExeName "HuTaoAssistant.exe"
#define SourceRoot "..\..\build\windows\app"

[Setup]
AppId={{9F04D2C2-2A09-4B34-8FC9-2C1B696CF1F3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={code:GetDefaultInstallDir}
DisableProgramGroupPage=yes
OutputDir=..\..\build\windows\installer
OutputBaseFilename=HuTaoAssistant-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.10240
PrivilegesRequired=lowest
Uninstallable=yes
CreateUninstallRegKey=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
SetupLogging=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked
Name: "startmenu"; Description: "创建开始菜单快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "data\*,models\*,personas\*,logs\*,backups\*,*.log,__pycache__\*"
Source: "{#SourceRoot}\data\persona\*"; DestDir: "{app}\data\persona"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "{#SourceRoot}\models\*"; DestDir: "{app}\models"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist uninsneveruninstall

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall
Name: "{app}\models"; Flags: uninsneveruninstall
Name: "{app}\personas"; Flags: uninsneveruninstall
Name: "{app}\logs"; Flags: uninsneveruninstall
Name: "{app}\backups"; Flags: uninsneveruninstall

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autoprograms}\{#AppName}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: startmenu
Name: "{autoprograms}\{#AppName}\卸载 {#AppName}"; Filename: "{uninstallexe}"; WorkingDir: "{app}"; Tasks: startmenu

[Run]
Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Description: "启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime-cache"

[Code]
var
  DeleteModelsOnUninstall: Boolean;
  DeleteAllDataOnUninstall: Boolean;

function GetDefaultInstallDir(Param: String): String;
var
  DriveIndex: Integer;
  Candidate: String;
begin
  for DriveIndex := Ord('D') to Ord('Z') do
  begin
    Candidate := Chr(DriveIndex) + ':\';
    if DirExists(Candidate) then
    begin
      Result := Candidate + 'HuTaoAssistant';
      Exit;
    end;
  end;
  Result := ExpandConstant('{localappdata}\Programs\HuTaoAssistant');
end;

function InitializeUninstall(): Boolean;
var
  Choice: Integer;
begin
  DeleteModelsOnUninstall := False;
  DeleteAllDataOnUninstall := False;
  if UninstallSilent then
  begin
    Result := True;
    Exit;
  end;
  Choice := MsgBox(
    '是否删除全部本地数据？' + #13#10 + #13#10 +
    '选择“是”：删除模型、聊天记录、人格、向量索引、配置、备份和日志。' + #13#10 +
    '选择“否”：继续选择是否只删除模型。' + #13#10 +
    '选择“取消”：取消卸载。',
    mbConfirmation,
    MB_YESNOCANCEL
  );
  if Choice = IDYES then
  begin
    DeleteModelsOnUninstall := True;
    DeleteAllDataOnUninstall := True;
    Result := True;
  end
  else if Choice = IDNO then
  begin
    DeleteModelsOnUninstall := MsgBox(
      '是否同时删除已安装的本地模型？' + #13#10 + #13#10 +
      '选择“否”将只卸载程序，并保留聊天记录、人格、配置和模型。',
      mbConfirmation,
      MB_YESNO
    ) = IDYES;
    Result := True;
  end
  else
    Result := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    if DeleteModelsOnUninstall then
      DelTree(ExpandConstant('{app}\models'), True, True, True);
    if DeleteAllDataOnUninstall then
    begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      DelTree(ExpandConstant('{app}\personas'), True, True, True);
      DelTree(ExpandConstant('{app}\backups'), True, True, True);
      DelTree(ExpandConstant('{app}\logs'), True, True, True);
    end;
  end;
end;
