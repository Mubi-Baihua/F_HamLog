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
;    4. MyAppName / MyAppId 也可由 /D 注入，供 preview.yml 生成与正式版
;       共存、互不覆盖的预览安装包（F HamLog 2 Preview）
;
;  本地调试用法（在仓库根目录执行）：
;    ISCC.exe /DMyAppVersion=2.4.0 ^
;             /DOutputBaseFilename="F HamLog 2.4 setup" ^
;             /DRepoRoot="D:\F-Dev\BIG\F_HamLog" ^
;             ".github\inno\F HamLog 2.iss"
;  预览包调试用法：
;    ISCC.exe /DMyAppVersion=UTC-20260927-1835 ^
;             /DMyAppName="F HamLog 2 Preview" ^
;             /DMyAppId="{{2AF71D4C-3B58-4E6A-9A21-6E10B7F3C4D8}" ^
;             /DOutputBaseFilename="F HamLog 2 Preview UTC-20260927-1835 setup" ^
;             /DRepoRoot="D:\F-Dev\BIG\F_HamLog" ^
;             ".github\inno\F HamLog 2.iss"
; ============================================================================

; ---- 仓库根目录（本脚本位于 <RepoRoot>\.github\inno\）----------------------
#ifndef RepoRoot
  #define RepoRoot AddBackslash(SourcePath) + "..\.."
#endif

; ---- 已由命令行 /D 定义、或用户自定义的变量（无需再定义）--------------------
; MyAppName 可能由 preview.yml 以 /DMyAppName="F HamLog 2 Preview" 注入，
; ISCC 在“已定义”时执行 #ifndef 会打印编译警告，故先用 #ifdef 短路。
#ifdef MyAppName
  #define MyAppNamePreview
#endif

; ---- 可被命令行 /D 覆盖的变量 ----------------------------------------------
#ifndef MyAppVersion
  #define MyAppVersion "2.4.0"
#endif
#ifndef MyAppNamePreview
  #define MyAppName "F HamLog 2"
#endif
; 应用唯一标识：正式版与 Preview 必须不同，否则两个包会互相覆盖/共用卸载项
#ifndef MyAppId
  #define MyAppId "{{9C87FCB8-00FD-4889-8E7B-02B5789015C0}"
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
; （Preview 流程会 /DMyAppId 传入另一个 GUID，以与正式版共存、互不覆盖）
AppId={#MyAppId}
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

[INI]
; 避免重复安装时堆叠多个键：Inno 的 [INI] 写入是「追加」语义（同一文件重复运行会
; 把键再写一遍），因此用 destructive 标志让每次安装都把 version.txt 整个重建。
; {app}\file 是安装包对用户数据的“存在则保留”保护范围，version.txt 属于本包自己
; 维护的版本标识（不属用户数据），因此覆盖它是预期行为。
Filename: "{app}\file\version.txt"; Section: "version"; Key: "version"; String: "{#MyAppVersion}"; Flags: uninsdeleteentry createkeyifdoesntexist
Filename: "{app}\file\version.txt"; Section: "version"; Key: "version"; String: "{#MyAppVersion}"
