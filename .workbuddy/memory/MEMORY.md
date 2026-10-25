# F HamLog 项目长期记忆

> 细节（文件结构 / 设置键 / 打包命令 / 卫星 API / 加密协议 / i18n / 离屏坑）见 `DETAILS.md`；
> 逐次改动见 `YYYY-MM-DD.md`。本文件只留**约定 / 决策 / 踩坑**，一条一句硬规则。

## 基本约定
- PySide6 + Nuitka，**src 结构**（`src/f_hamlog/`，入口 `__main__.py`）；**包内模块不加 sys.path 守卫**。
- **版本单一来源 = `__init__.py.__version__`**（pyproject `dynamic`+`attr`），禁止硬编码；i18n 用 `{}`。
- **长线程一律继承 `bg_thread.BgThread`**；`aboutToQuit` → `stop_all()`，`exec()` 后再调一次（幂等）。
  否则线程活着被析构 → Qt abort（`0xc0000409`、无 traceback）；`closeEvent` 的 `wait()` 管不了 quit / 关机。
- **依赖版本单一来源 = 根 `第三方模块.txt`**（全 `==`）：workflow 只 `pip install -r`，**禁止另写包名列表**；
  venv 缓存命中要**逐条比对版本**，别只验 import。
- **数据目录 = `F_HAMLOG_DATA_DIR` → exe 目录 → 模块目录 → cwd**（`_app_base_dir()` 只认带标记文件的候选）；
  **绝不相信 cwd**，一律 `app_path('file/…')`。
- 本机 shell：有 `ls/head/tail/wc/rm/git`，缺 `dirname/cat`；Git Bash 把 `/Dxxx` 当路径，调 ISCC 要
  `MSYS2_ARG_CONV_EXCL="*"`；venv `.venv/Scripts/python.exe`；**不主动 git commit/push**；
  分支 `main` / `develop` / `develop-English`。

## 文件格式 `.fhl` / `.fhla`
- `.fhl` = `list[dict]`；`.fhla` = `{"xml": 属性块, "project": 记录}`；读写**只走 `read_project_file` /
  `save_project_file`**（传 `(records, key, meta)`；`.fhl` 的 meta 恒 None，回写原样带回）。
- 显示名：`.fhla` = **F HamLog 项目**，`.fhl` = **F HamLog 兼容项目**；菜单动作名不改。
- **保存默认 `.fhla`**：`project_save_filters()` 首条 + `complete_project_suffix()`（Qt 不补后缀，`sel` 空也补；
  `*.fhl` 是 `*.fhla` 前缀 → **先判 `.fhla`**）。
- **打开 `.fhl` 每次都问「迁移 / 暂不迁移」**（无开关）：迁移 = 写同名 `.fhla`（读回校验条数）→ 删原 `.fhl`，
  失败不挡打开；`default_quick_project_path()` 优先 `main.fhla` → `main.fhl`。
- `encrypted` 只是声明，**以字节能否 UTF-8 解为准**；**不记「创建者 / 创建时间」这类首次编辑属性**；
  **「打开即自动保存」不算编辑**（快照比对）；属性 = `last_editor` / `last_edit_time` / `last_version` /
  `encrypted` / 自定义字段键；属性窗口 = `Alt+I`，`.fhl` 提示「不支持的格式」。
- **操作者 = 设置里的呼号**（大写去空白），没填退回系统用户名；`load_settings()` 用 `utf-8-sig` +
  `literal_eval`（BOM 会让旧 `eval` 静默读不到呼号）。

## 自定义日志字段（`.fhla` 专属）
- **只填字段名称**；键 = 首次创建时的名称（撞名 `_2`），改名只改显示名 → 记录键不动，不丢数据。
- 整表含**标准 20 行**；**该表顺序 = 新建日志行序 = 更多信息行序 = 主页列序** → 呼号大写委托**按 key 找行号**。
- 「必填」「在主页显示」**所有字段可改**，**xml 只记偏离默认的键**；落盘 `other_item` + `field_order` +
  `field_meta`；**「恢复默认」只重置表格，点保存才写盘**；**`.fhl` 一律不给**（管理窗口拒绝、录入只 20 行）。

## 主题 / 对话框 / i18n
- 浅深**一律平台原生调色板**：不建兜底色、不上全局 QSS、不用 `Fusion`；颜色走 `theme.hint_css()/warn_css()/
  link_color()/watch_theme()`，**禁止写死**；验证颜色看 `grab()` 像素。
- **抓像素必乘 DPR**：125% 下 `grab()` 是设备像素图，`pixelColor()` 传「逻辑坐标 × DPR」；行底色取「省略地址
  与右端延迟之间空白带」的众数（曾误判悬停 / 斑马纹）。
- **原生 windows11 样式两坑**：① 悬停 `Highlight` 整行填充 → QSS 必须写 `::item:hover`；② 焦点行描纯黑大框
  （`PE_FrameFocusRect`）→ 委托 copy option 后剥 `State_HasFocus`。
- **星历数据源窗口定稿**：悬停 = `blend(Window, WindowText, 0.08)`（浅 #e0e0e0 / 深 #303030），文字色不动；
  选中 = 链接色文字 + 透明底，`:hover:selected` 同选中观感；**不描黑框**（`__tle_hover_gray_smoke.py`，
  必须 `QT_QPA_PLATFORM=windows`）。
- **文件对话框一律原生静态调用**（自绘+汉化已否决）；默认桌面、文件名空（`dialog_defaults.desktop_dir()`）。
- i18n：中文是源语言，**动态文案逐段 `i18n.tr` 后再拼**；单元格固定文案用 `bind_cell_texts`；文件对话框在
  **调用处**翻；`translate()` 幂等；**窗口尺寸在 `show()` 之后量**；**词表别加重复键**；设置存
  `file/m_xml.txt`，各模块只改自己的键。
- **设置页 = 自动保存，没有「保存更改」按钮**（2026-10-25 定稿）：文本输入接 `textChanged` → 300 ms 防抖
  `QTimer` → `_save()`；开关/数字立即写。`_save()` 每次**重读整份 m_xml.txt 再 update 自己的键**（别写死整份）。
  坐标解析失败时**保留上一次有效值**（`pos_state`），不弹「请输入数字」——自动保存会在半截输入时反复触发。
- **「自动更新」复选框与「检查更新」同一行（版本号右侧）**，默认 **True** → 每次打开程序查一次；发现新版本
  照常弹窗提示（与手动同一路径 `_on_update_checked`），**只有「已是最新 / 检查失败」不打扰**；预览版开关置灰、
  `start_auto_update()` 连线程都不起。启动检查挂在 `main.py` 的 `QTimer.singleShot(1500, …)`。

## 主表格 / 大项目性能
- 勾选 /「更多」列**一律自绘委托**，**禁止逐行 `setCellWidget`**；勾选唯一权威 = `_checked_rows`。
- **不启用 `stretchLastSection`**、不强制行高；每列显式设宽（「选择」45 首列、「更多」80 末列）。
- 重建要**还原滚动位置**（`QTimer.singleShot(0, …)`）；`table_update(scroll_to_bottom=True)` 仅三处调用。
- `write_fhl_file` 必须 `json.dumps` 后一次性 `f.write`（禁止 `json.dump`）；`save()` 有未变更跳过但首次必执行。
- **内容比较一律用值快照**（`_content_snap()` + `==`），**别退回 `json.dumps` 比字符串**；**单条编辑 / 少量删除
  禁止整表重建**（`table_refresh_row` / `table_remove_rows`），但 date / time 变了必须 `table_update()`。
- 撤销点用逐条浅拷贝（别 `deepcopy`），撤销栈按「步数 + 记录总数」限流；`_fill_rows` 期间 `gc.disable()`。
- 改表格 / 保存路径前先跑 `__perf_tick_bench.py`、`__perf_long_fhl_bench.py`；**格式与落盘函数不允许因性能
  原因改动**（验证 `__inplace_edit_smoke.py`）。

## 运行日志（app_log.py）
- `__main__.py`（import main 之前）与 `main.main()` 各调一次 `setup()`（幂等）；落 `file/log/` **只留三天**，
  C 层崩溃栈单独 `F_HamLog_crash_*.log`。
- **日志不能把程序带崩**（全 try、`raiseExceptions=False`、Tee 用 `threading.local`）；**窗口版 exe 的
  `sys.stdout` 是 None**，Tee 必须支持；打包加 `--noinclude-data-files="file/log/*.log"`。

## 布局 / 尺寸（启动器）
- **`setFixedSize` 之后禁止再 `setMinimumHeight/setMaximumWidth`**（会让固定尺寸变区间 → 打开时跳一下）。
- 内容比窗口高时**别用 `addSpacing(N)` 硬撑**，改 `QSpacerItem(…, Expanding)`，末尾别加 `addStretch`。
- 验证 `__main_layout_settle_smoke.py`（**必须 `QT_QPA_PLATFORM=windows`**）。

## 提示与通知
- 所有 `.setToolTip(...)` 已整段注释（2026-09-29，47 处）→ `__sat_window_smoke` 的「提示列出数据源」必然失败。
- `show_toast()`：非模态、无边框、置顶、1 秒关、可堆叠、跟随主题；**分层窗口禁用 `QGraphicsDropShadowEffect`**
  （脏矩形越界），用 1px 边框。
- **删除日志无二次确认**（定稿）：直接删 + toast，安全网 = `snapshot_before()`；**别改回 `QMessageBox.question`**。
- **别用 `setEnabled(False)` 表示「忙」**：Qt 会立刻把焦点移交到焦点链下一个控件，设置页里就是「我的呼号」
  QLineEdit，而它因 TabFocusReason 拿焦点时会**全选文本**（＝"点检查更新自动选中呼号"）；改用改文字 +
  `isRunning()` 拦重入。回归 `tests/__update_btn_focus_smoke.py`。

## 卫星 / 过境视图
- `satellite_pred.py`（skyfield 离线）；`MAX_PREDICT_HOURS=240`、`MAX_SELECTED_SATELLITES=250`；数据源 =
  `file/tle_sources.txt` + 独立窗口（`#` 禁用、延迟探测只进 `_ROLE_DELAY`、按 NORAD 增量更新）；入口 project
  「卫星→通联预测」Ctrl+Shift+E / main「卫星过境」「通联预测」；**改卫星名匹配规则时两处同步**；选择框
  **隐藏行必须 `setRowHidden`**，超限靠 `reset_requested` + `while True` 重开。
- 过境视图 = 极坐标天空图（**素色定稿：无阴影/光晕/渐变/圆角**），**配色一律从 `QPalette` 混合**；可通联只把
  线画粗（2.4×）；**skyfield 没有 `ts.utc(jd=...)`**，JD 走 `ts.from_datetime(jd_to_datetime(jd))`。
- 「双方全部过境」用 `emphasis=(起,止)` + `auto_spans=True`，时间轴取并集；工具栏「过境视图」**有选中用选中行，
  没有就自动取最近一次**并 `selectRow()`。
- **过境 / 地图窗口都是独立顶层窗口**（父对象会变「被拥有的窗口」，最小化来源窗口就跟着最小化）。
- **经纬度 0° 是合法坐标**：不得用「均为 0 → 未设置」拦截。

## 多人日志 / 服务端
- **`remote_crypto.py` 是密码学唯一出处**（全帧加密、nonce 滑窗防重放、服务端先说话）；**退出必走
  `RemoteConnection.shutdown()`**；Qt 关窗只隐藏不触发 `destroyed`（资源在 `install_close_guard`）；独立服务端
  目录**自带两份副本 → 改协议须三份同步**；`main.py` 只留一个 `project_window`，必须保留 `_confirm_replace_session()`。
- 服务端 exe：启动即建 `keys/`、`main.fhl`、`password_xml.txt`；`_app_dir()` **不能信 `sys.executable`**；
  带 `--windows-uac-admin`，端到端验证须另打**去掉 uac-admin** 的临时包。

## 验证（离屏冒烟）
- `QT_QPA_PLATFORM=offscreen` 可真实冒烟。**四坑**：① 槽里 `sys.exit()` 终止进程；② 静态 `QFileDialog.*` /
  `QMessageBox.*` 自带模态循环；③ `os._exit()` 跳过 flush；④ **加密文件不给 `key` 会弹密钥框挂死**。
- 测试放 `tests/`（`__*_smoke.py`）；`set.py`/`project.py` 读设置用**硬编码 `file/m_xml.txt`**（只 patch 常量
  不够）；**绝不能 `git checkout -- file/…`**；`project.main()` 不触碰星历。

## 检查更新（`check_update.py` 唯一出处）
- **不 import Qt**：`check()` → `preview|error|latest|new`；`download()` 多线程分段（Range 探测 → ≥4MB 才切段，
  默认 16 线程、每段 ≥512KB，失败退回单线程）；`run_installer()` `/SILENT`；界面只有 `set.py` 版本号右侧按钮
  （线程继承 `BgThread` + **模块级强引用**）。
- **进度窗的坑**：`setValue()` 内部 `ensureDialog() → show()`，关窗后只要有进度帧就自己弹回来；用
  `state['closed']` 拦住并**先 `reset()` 再 `hide()`**；QProgressDialog **只增不减**（宽度不会自己缩）。
- **QMessageBox 没有 RejectRole 按钮时，标题栏叉号和 Esc 完全失效**（"只放两个按钮、让用户点叉取消"
  这条路在 Qt 上不通）。要自定义按钮顺序就自己用 QDialog 排；role 也救不了 —— Windows 下 Reject
  永远紧跟 Accept。
- **下载/提示窗一律不可最大化**（定稿）：`_no_maximize()` = `WindowMaximizeButtonHint=False` +
  `MSWindowsFixedSizeDialogHint=True`（顺带去掉 `WS_THICKFRAME`，拖边 / Aero Snap 都变形不了），再在
  `changeEvent` 里 `WindowStateChange && isMaximized() → showNormal()` 兜住任务栏菜单/`ShowWindow`。
  别只删最大化 hint —— 那只是把按钮画成灰的，双击标题栏 / 拖到屏幕上沿照样放大。
  进度窗还要 `WindowMinimizeButtonHint` + `Qt.NonModal` + `parent=None`（模态下最小化自己、父窗口仍被阻塞，
  更像卡死），代价是收尾时 window 可能已销毁 → `_alive()` 探活。
- **速度 / 剩余时间必须平滑**：速度用 1 s 滑动窗（`Speedometer`），剩余时间用 `EtaEstimator`（累计平均速度 +
  只降不升 + 死区/步长随 eta 缩放）。`_Meter.add()` 的**回调必须在锁内**，否则多线程下 `done` 会倒退、
  ETA 反复重置；`done` 回退当帧不重算（**别重设基准**，否则预热反复重来，ETA 一直不显示）。
- **加速**：GitHub 限**单连接** → 多开线程 + `PART_TIMEOUT=15` 断线重连 + `choose_source()` 镜像择优（2 s 测速
  窗、快 1.3 倍才换、换前确认支持 Range）；走镜像时 `_spot_check()` 与官方抽样比对；版本文件可写第三段 sha256。
- **预览版不自我更新**：版本串含 `UTC` / `Preview` 任一 → 连网都不连；`preview.yml` 改写版本号
  这一步**必须夹在 `pip install -e .` 之后（PEP 440）与 Nuitka 之前**；缓存键是改写前算的，不影响缓存。
- **预览版版本串全 ASCII、不含中文**（定稿 2026-10-25）：`Preview UTC-yyyyMMdd-HHmm 2.x.y`，
  这个串要出现在标题栏 / 设置页 / 安装包摘要里，中文在 CI 控制台与 Nuitka 字符串常量里会被转义。
- **下载前必查本地已有包**：缓存目录 `%LOCALAPPDATA%/F_HamLog/update`（`F_HAMLOG_UPDATE_DIR` 可覆盖；
  TEMP 会被清理，旧位置仅回退认）；下载成功写同名 `.json` 元数据（url/version/size/sha256/time）。
  `find_installer()` 判据从硬到软 = sha256 → 元数据（url+size）→ 仅 exe 名称；**小于 1 MB 一律不认**（挡半截文件）。
  **判「同一个包」只认 exe 文件名（`installer_name()` 归一化：小写 + 去掉空格/点/下划线/连字符），不解析版本号**
  （`F HamLog 2.9 setup.exe` vs `2.9.0` 会被旧的两向比较判成「不符」→ 无限重下）；`version` 参数只为兼容保留。
  用户在「已有安装包」里选**重新下载必须传 `force=True`**，否则 `download()` 又命中缓存、白点一次。
- 线上版本文件 `版本号 下载地址 [sha256]`；远端**不比本地新就算最新**（否则会推降级安装）。

## 打包 / 发布（命令细节见 `DETAILS.md`）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，默认分支 `main`；`main.yml` 手动发布 / `preview.yml` cron 预览 /
  `.github/inno/F HamLog 2.iss`；本机无 `gh`；**取产物脚本双位置回退**；`commit_artifacts='false'` 跳过回写分支。
- **界面改动「打包后没生效」先怀疑装到旧包**：扫 exe 字节找新代码独有字符串，**别用安装后 mtime**（Inno 会改
  成安装时刻）；锁屏下验界面 `PrintWindow(hwnd,hdc,2)` + 探针先 `SetProcessDpiAwarenessContext(-4)`
  （`tests/__pkg_ui.py`）。
- **打包必须显式给 `PYTHONPATH=<repo>/src`**，否则零告警产出「空壳 exe」；workflow 内置空包检查（找不到
  `f_hamlog.app_log` 即失败）：**「打包成功」≠ 产物可用**。
- **产出目录靠 `--output-folder-name=main` 固定**（`main.dist` / `main.build`）；`.iss`、兼容版 zip、`.gitignore`
  全按 `main.dist` 写死，别删。
- **打包命令禁止 `--include-module`**（编译主模块前解析，点分名必 FATAL）；`remote_crypto` 由 import 自动收录。
- **CI 的 pip 不许碰中文输出**：workflow 级必须有 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` /
  `PIP_PROGRESS_BAR=off`；安装前复制成 `%RUNNER_TEMP%\requirements-ci.txt` 再 `pip -r`（缓存键仍原名）。
- **`.iss` 的 `[Files]` 必须跟得上数据文件名**（默认日志种子已改 `main.fhla`，写死旧名会 ISCC aborted；
  种子带 `Check: NeedSeedMainFhla`）。改 `src/f_hamlog/file/` 被点名的文件必须同步 `.iss`。
- 合并 `file/`：`.tle` 取更完整一侧；`m_xml.txt` 只差 `sat_last_update` 取较新；`memory/*.md` 全保留。
