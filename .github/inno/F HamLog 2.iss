; ============================================================================
;  F HamLog —— GitHub Actions 发布流程专用的 Inno Setup 脚本
;
;  参考脚本：F HamLog 2 Inno Setup\F HamLog 2.iss
;  安装/升级逻辑（AppId、覆盖规则、[Files]/[Dirs]/[Icons]）与参考脚本一致，
;  区别只在“变量化”，以便在 CI 中自动注入版本号：
;    1. 路径由 RepoRoot 推导（或由 ISCC /D 传入），不写死 D:\...
;    2. MyAppVersion / OutputBaseFilename / MyAppExeName 可由 /D 注入
;       → 版本号全自动，安装包名形如 “F HamLog 2.4 setup.exe”
;    3. 中文语言文件用仓库内置的 .github\inno\ChineseSimplified.isl
;       （GitHub 托管运行器的 Inno Setup 不带非官方中文语言包）
;
;  本地调试用法（在仓库根目录执行）：
;    ISCC.exe /DMyAppVersion=2.4.0 ^
;             /DOutputBaseFilename="F HamLog 2.4 setup" ^
;             /DRepoRoot="D:\F-Dev\BIG\F_HamLog" ^
;             ".github\inno\F HamLog 2.iss"
; ============================================================================

; ---- 仓库根目录（本脚本位于 <RepoRoot>\.github\inno\）----------------------
#ifndef RepoRoot
  #define RepoRoot AddBackslash(SourcePath) + "..\.."
#endif

; ---- 可被命令行 /D 覆盖的变量 ----------------------------------------------
#ifndef MyAppVersion
  #define MyAppVersion "2.4.0"
#endif
#ifndef MyAppName
  #define MyAppName "F HamLog 2"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "F HamLog 2.exe"
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "F HamLog 2.4 setup"
#endif
#ifndef SourceDistDir
  #define SourceDistDir RepoRoot + "\main.dist"
#endif
#ifndef OutputDirPath
  #define OutputDirPath RepoRoot + "\release"
#endif
#ifndef ChineseMessagesFile
  #define ChineseMessagesFile AddBackslash(SourcePath) + "ChineseSimplified.isl"
#endif

; ---- 固定信息（与 F HamLog 2.iss 保持一致）---------------------------------
#define MyAppPublisher "木比白桦 BI8SQL"
#define MyAppURL "https://mubi-baihua.github.io/f_hamlog.html"

[Setup]
; AppId 与参考脚本相同 —— 安装包之间的升级关系依赖它，切勿修改
AppId={{9C87FCB8-00FD-4889-8E7B-02B5789015C0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir={#OutputDirPath}
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#RepoRoot}\file\F_HamLog.ico
SolidCompression=yes
WizardStyle=modern dynamic windows11

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#ChineseMessagesFile}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
;普通程序文件，每次升级正常覆盖，排除file文件夹
Source: "{#SourceDistDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "file\*"

; file目录：单文件级"存在则保留、缺失则创建（带数据）"
; 不使用 ignoreversion/recursesubdirs，改用 onlyifdoesntexist：
; 仅当目标同名文件不存在时才安装，升级时用户数据不被覆盖，新增模板会自动补回
Source: "{#SourceDistDir}\file\amateur.tle"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\F_HamLog.ico"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\main.fhl"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\m_xml.txt"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\pack_list.txt"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\sat_radio_dict.txt"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\tqsl_dict.txt"; DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\world_land.json"; DestDir: "{app}\file"; Flags: onlyifdoesntexist

[Dirs]
Name: "{app}\file"; Check: not DirExists(ExpandConstant('{app}\file'))

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
