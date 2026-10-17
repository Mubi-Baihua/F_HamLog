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
#define MyAppURL "https://mubi-baihua.pages.dev/f_hamlog.html"

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
; 显式要求管理员权限（Inno 默认值就是 admin，这里写出来是为了意图明确、防止漂移）：
;   只有「管理员安装模式」下，{autopf} 才稳定解析为 {commonpf}（C:\Program Files）。
;   若落到「非管理员安装模式」，{autopf} 会改解析为 {userpf}（%LOCALAPPDATA%\Programs），
;   Preview 的安装位置就与正式版不一致了。
; 同时不提供 PrivilegesRequiredOverridesAllowed：向导里不会出现「仅为当前用户安装」的
;   降级选项，从而保证 Preview 与正式版都装在同一处 Program Files。
PrivilegesRequired=admin
OutputDir={#OutputDirPath}
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#RepoRoot}\src\f_hamlog\file\F_HamLog.ico
SolidCompression=yes
; 130MB 的主程序 + Qt 库，用最高压缩率；LZMA 单独进程跑，避免 ISCC 进程本身吃满内存
; （本机只有 16G，跑 Blender 时更容易被 OOM 杀掉）。
Compression=lzma2/max
LZMAUseSeparateProcess=yes
WizardStyle=modern dynamic windows11

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#ChineseMessagesFile}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; ---- ① 程序本体：每次升级整体覆盖 -------------------------------------------
;    排除 file\ 整个目录 —— 它下面混着「用户数据」和「随版本更新的资源」，
;    混在一起用 ignoreversion 覆盖会冲掉用户设置，所以要拆开处理（见 ②③④）。
Source: "{#SourceDistDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "file\*"

; ---- ② file\ 下「必须跟着版本走」的只读资源：覆盖 ---------------------------
;    ⚠️ 这几个以前也写成 onlyifdoesntexist，导致**升级后用户手里还是旧字典 / 旧地图**
;       （卫星转发器表、TQSL 映射、世界地图轮廓都是随版本改进的数据）。
Source: "{#SourceDistDir}\file\F_HamLog.ico";      DestDir: "{app}\file"; Flags: ignoreversion
Source: "{#SourceDistDir}\file\sat_radio_dict.txt"; DestDir: "{app}\file"; Flags: ignoreversion
Source: "{#SourceDistDir}\file\tqsl_dict.txt";     DestDir: "{app}\file"; Flags: ignoreversion
Source: "{#SourceDistDir}\file\world_land.json";   DestDir: "{app}\file"; Flags: ignoreversion

; ---- ③ file\ 下「其余一切」：缺失则补装，已存在则保留 -----------------------
;    **用反向排除而不是逐条白名单**：以前是 8 个文件的白名单，于是给 file\ 新增
;    tle_sources.txt / sat_map_markers.txt 这类数据时忘了改脚本 → 全新安装就是缺文件。
;    现在新增数据文件会自动补装（仍然不覆盖用户已有内容，安全方向一致）。
;    排除项 = ②里已单独处理过的 + ④的种子 + 开发机残留（python-*.exe / 未保存备份）+ 运行时目录。
Source: "{#SourceDistDir}\file\*"; DestDir: "{app}\file"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs; Excludes: "F_HamLog.ico,sat_radio_dict.txt,tqsl_dict.txt,world_land.json,amateur.tle,main.fhl,m_xml.txt,tle_sources.txt,sat_map_markers.txt,python-*.exe,*backup.fhl,log\*,keys\*,remote_rooms\*,pypack\*"

; ---- ④ 用户数据 / 可写状态的「种子」 ---------------------------------------
;    全新安装才写入；升级一律保留用户现有内容。
Source: "{#SourceDistDir}\file\amateur.tle";        DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\main.fhl";           DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\m_xml.txt";          DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\tle_sources.txt";    DestDir: "{app}\file"; Flags: onlyifdoesntexist
Source: "{#SourceDistDir}\file\sat_map_markers.txt"; DestDir: "{app}\file"; Flags: onlyifdoesntexist

[Dirs]
; {app}\file 一定存在（③④ 会往里写）；这里只是把「程序会自己创建的运行时目录」
; 提前建好，省得首次启动时因为 Program Files 写权限时序问题卡一下。
; 不用 Check: not DirExists(...)：Inno 的 [Dirs] 本身就是「不存在才建」。
Name: "{app}\file"
Name: "{app}\file\log"
Name: "{app}\file\keys"
Name: "{app}\file\remote_rooms"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[INI]
; version.txt 记录「当前装的是哪个版本」，属于本包自己维护的标识。
; 这里只要一行：Inno 的 [INI] 走 WritePrivateProfileString，同 section+key 是覆盖语义，
; 重复运行不会堆叠。以前写了两行一模一样的（第二行没有 flags），纯属冗余，已删。
Filename: "{app}\file\version.txt"; Section: "version"; Key: "version"; String: "{#MyAppVersion}"; Flags: uninsdeleteentry createkeyifdoesntexist
