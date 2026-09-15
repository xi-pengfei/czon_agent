#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "企业 AI 智能体"
#define MyAppPublisher "陕西知远驭盛科技有限公司"
#define ProjectRoot "..\.."
#define BuildRoot "..\..\.packaging-build\windows"

[Setup]
AppId={{921B8910-6EF6-4C1B-A492-467E6B447B5A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=http://www.czon.cn
DefaultDirName={code:GetDefaultDir}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputBaseFilename=czon_agent_{#MyAppVersion}_windows_x64
SetupIconFile=czon_agent.ico
UninstallDisplayIcon={app}\czon_agent.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Dirs]
Name: "{app}\data"
Name: "{app}\logs"
Name: "{app}\uploads"
Name: "{app}\workspace"
Name: "{app}\skills"
Name: "{app}\service"

[Files]
Source: "{#ProjectRoot}\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\config.yaml"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\adapters\*"; DestDir: "{app}\adapters"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,.DS_Store"
Source: "{#ProjectRoot}\core\*"; DestDir: "{app}\core"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,.DS_Store"
Source: "{#ProjectRoot}\tools_builtin\*"; DestDir: "{app}\tools_builtin"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,.DS_Store"
Source: "{#ProjectRoot}\webui\*"; DestDir: "{app}\webui"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,.DS_Store"
Source: "{#ProjectRoot}\skills\office-io\*"; DestDir: "{app}\skills\office-io"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,.DS_Store"
Source: "{#ProjectRoot}\skills\enterprise-skill-creator\*"; DestDir: "{app}\skills\enterprise-skill-creator"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,.DS_Store"
Source: "{#BuildRoot}\python-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "{#BuildRoot}\requirements-windows.txt"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "{#BuildRoot}\wheelhouse\*"; DestDir: "{tmp}\wheelhouse"; Flags: deleteafterinstall recursesubdirs createallsubdirs
Source: "{#BuildRoot}\czon_agent_service.exe"; DestDir: "{app}\service"; Flags: ignoreversion
Source: "czon_agent_service.xml"; DestDir: "{app}\service"; Flags: ignoreversion
Source: "czon_agent.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "http://127.0.0.1:8000"; IconFilename: "{app}\czon_agent.ico"; Tasks: desktopicon
Name: "{group}\打开 {#MyAppName}"; Filename: "http://127.0.0.1:8000"

[Run]
Filename: "{cmd}"; Parameters: "/C if not exist ""{app}\.env"" type nul > ""{app}\.env"""; Flags: runhidden waituntilterminated
Filename: "{tmp}\python-installer.exe"; Parameters: "/quiet InstallAllUsers=0 TargetDir=""{app}\runtime"" Include_pip=1 Include_launcher=0 PrependPath=0 Shortcuts=0 AssociateFiles=0"; StatusMsg: "正在安装独立 Python 运行环境..."; Flags: waituntilterminated
Filename: "{app}\runtime\python.exe"; Parameters: "-m pip install --disable-pip-version-check --no-index --find-links ""{tmp}\wheelhouse"" -r ""{tmp}\requirements-windows.txt"""; WorkingDir: "{app}"; StatusMsg: "正在安装程序依赖..."; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""czon_agent WebUI"" dir=in action=allow protocol=TCP localport=8000"; Flags: runhidden waituntilterminated
Filename: "{app}\service\czon_agent_service.exe"; Parameters: "install"; WorkingDir: "{app}\service"; StatusMsg: "正在注册后台服务..."; Flags: runhidden waituntilterminated
Filename: "{app}\service\czon_agent_service.exe"; Parameters: "start"; WorkingDir: "{app}\service"; StatusMsg: "正在启动企业 AI 智能体..."; Flags: runhidden waituntilterminated
Filename: "http://127.0.0.1:8000"; Description: "打开企业 AI 智能体"; Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
Filename: "{app}\service\czon_agent_service.exe"; Parameters: "stop"; WorkingDir: "{app}\service"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\service\czon_agent_service.exe"; Parameters: "uninstall"; WorkingDir: "{app}\service"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""czon_agent WebUI"""; Flags: runhidden waituntilterminated

[Code]
function GetDefaultDir(Param: String): String;
begin
  if DirExists('D:\') then
    Result := 'D:\czon_agent'
  else
    Result := 'C:\czon_agent';
end;
