# F HamLog 项目长期记忆

> 只留**硬规则**（一条一句）。细节见 `DETAILS.md`，逐次改动见 `YYYY-MM-DD.md`。

## 基本约定
- PySide6 + Nuitka，**src 结构**（`src/f_hamlog/`，入口 `__main__.py`）；包内模块**不加 sys.path 守卫**。
- **版本单一来源 = `__init__.py.__version__`**（pyproject `dynamic`+`attr`）；i18n 用 `{}`。
- **长线程一律继承 `bg_thread.BgThread`**；`aboutToQuit` → `stop_all()`，`exec()` 后再调（幂等）。
  否则线程活着被析构 → Qt abort（`0xc0000409`，无 traceback）。
- **依赖版本单一来源 = 根 `第三方模块.txt`**（全 `==`），workflow 只 `pip install -r`；venv 命中缓存要逐条比版本。
- **数据目录 = `F_HAMLOG_DATA_DIR` → exe 目录 → 模块目录 → cwd**；**绝不相信 cwd**，一律 `app_path('file/…')`。
- 本机 shell：有 `ls/head/tail/wc/rm/git`，缺 `dirname/cat`；调 ISCC 要 `MSYS2_ARG_CONV_EXCL="*"`；
  venv `.venv/Scripts/python.exe`；**不主动 commit/push**；分支 `main` / `develop` / `develop-English`。

## git / 网络（2026-10-25）
- 仓库是**部分克隆**（`promisor=true`、`filter=blob:none`）：合并会**按需回源**下 blob，撞大二进制
  （`F HamLog 2 Inno Setup/*.exe` ~70 MB）会长时间停在 `Updating …`，是在下载不是卡死。
- shell 注入 `http(s)_proxy=127.0.0.1:2081`：代理下 schannel 报 `CRYPT_E_NO_REVOCATION_CHECK`、openssl 报
  `unable to get local issuer certificate`；**去掉代理变量也无效**。
- 可用组合（**必须环境变量，命令行 `-c` 传不进按需回源的子 fetch**）：
  `GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=http.sslBackend GIT_CONFIG_VALUE_0=openssl GIT_CONFIG_KEY_1=http.sslVerify
  GIT_CONFIG_VALUE_1=false git …`。
- **中断合并必留 0 字节 `.git/index.lock`** → 下次 pull 报 File exists；确认无 `git.exe` 后 `rm -f`。
- `git pull origin <非跟踪分支>` 会误报 divergent：用 `git rev-list --left-right --count origin/X...X`，
  `N 0` 即纯落后 → `git merge --ff-only origin/X`。

## 文件格式 `.fhl` / `.fhla`
- `.fhl` = `list[dict]`；`.fhla` = `{"xml": 属性块, "project": 记录}`；读写**只走 `read_project_file` /
  `save_project_file`**（`(records, key, meta)`；`.fhl` 的 meta 恒 None 且原样带回）。
- 显示名：`.fhla` = **F HamLog 项目**，`.fhl` = **F HamLog 兼容项目**；菜单动作名不改。
- **保存默认 `.fhla`**：`project_save_filters()` 首条 + `complete_project_suffix()`；`*.fhl` 是 `*.fhla` 前缀
  → **先判 `.fhla`**。
- **打开 `.fhl` 每次问「迁移 / 暂不迁移」**（无开关）：迁移 = 写同名 `.fhla`（读回校验条数）→ 删原 `.fhl`，
  失败不挡打开；`default_quick_project_path()` 优先 `main.fhla` → `main.fhl`。
- `encrypted` 只是声明，**以字节能否 UTF-8 解为准**；**不记「创建者 / 创建时间」**；**「打开即自动保存」不算
  编辑**；属性 = `last_editor` / `last_edit_time` / `last_version` / `encrypted` / 自定义字段键；
  属性窗口 `Alt+I`，`.fhl` 提示「不支持的格式」。
- **操作者 = 设置里的呼号**（大写去空白），空则退回系统用户名；`load_settings()` 用 `utf-8-sig` + `literal_eval`。

## 自定义日志字段（`.fhla` 专属）
- **只填字段名称**；键 = 首次创建时的名称（撞名 `_2`），改名只改显示名 → 记录键不动。
- 含**标准 20 行**；**该表顺序 = 新建行序 = 更多信息行序 = 主页列序** → 呼号大写委托**按 key 找行号**。
- 「必填」「在主页显示」**所有字段可改**，**xml 只记偏离默认的键**；落 `other_item` + `field_order` +
  `field_meta`；**「恢复默认」只重置表格，点保存才写盘**；**`.fhl` 一律不给**。

## 主题 / 对话框 / i18n
- 浅深**一律原生调色板**：不建兜底色、不上全局 QSS、不用 `Fusion`；颜色走 `theme.hint_css()/warn_css()/
  link_color()/watch_theme()`，**禁止写死**。
- **抓像素必乘 DPR**，取「省略地址与右端延迟之间空白带」的众数（别取首行）。
- **原生 windows11 两坑**：① 悬停 `Highlight` 整行填充 → 必须写 `::item:hover`；② 焦点行描黑框
  （`PE_FrameFocusRect`）→ 委托 copy option 后剥 `State_HasFocus`。
- **星历数据源窗口定稿**：悬停 = `blend(Window, WindowText, 0.08)` 且文字色不动；选中 = 链接色文字 + 透明底，
  `:hover:selected` 同观感；不描黑框（`__tle_hover_gray_smoke.py`，须 `QT_QPA_PLATFORM=windows`）。
- **文件对话框一律原生静态调用**；默认桌面、文件名空（`dialog_defaults.desktop_dir()`）。
- i18n：中文是源语言，**逐段 `tr` 后再拼**；单元格固定文案用 `bind_cell_texts`；文件对话框在**调用处**翻；
  `translate()` 幂等；**窗口尺寸在 `show()` 之后量**；**词表别加重复键**；设置存 `file/m_xml.txt`，各模块只改
  自己的键。
- **设置页 = 自动保存，没有「保存更改」**：文本接 `textChanged` → 300 ms 防抖；开关/数字立即写；`_save()`
  **每次重读整份 m_xml.txt 再 update 自己的键**；坐标解析失败**保留上一次有效值**，不弹提示。
- **「自动更新」复选框在「检查更新」同一行**，默认 **True**；新版照常弹窗（`_on_update_checked`），只有
  「已是最新 / 失败」不打扰；预览版置灰且不起线程；挂 `QTimer.singleShot(1500, …)`。

## 主表格 / 大项目性能
- 勾选 /「更多」列**一律自绘委托**，**禁止逐行 `setCellWidget`**；勾选唯一权威 = `_checked_rows`。
- **不启用 `stretchLastSection`**、不强制行高；每列显式设宽（「选择」45、「更多」80）。
- 重建要**还原滚动位置**；`table_update(scroll_to_bottom=True)` 仅三处调用。
- `write_fhl_file` 必须 `json.dumps` 后一次性 `f.write`；`save()` 有未变更跳过但首次必执行。
- **内容比较用值快照**（`_content_snap()` + `==`），**别比 `json.dumps` 字符串**；**单条编辑 / 少量删除禁止
  整表重建**（`table_refresh_row` / `table_remove_rows`），但 date / time 变了必须 `table_update()`。
- 撤销点逐条浅拷贝（别 `deepcopy`），按「步数 + 记录总数」限流；`_fill_rows` 期间 `gc.disable()`。
- **格式与落盘函数不允许因性能原因改动**；改前跑 `__perf_tick_bench.py`、`__perf_long_fhl_bench.py`，
  验 `__inplace_edit_smoke.py`。

## 运行日志（app_log.py）
- `__main__.py`（import main 前）与 `main.main()` 各调一次 `setup()`（幂等）；`file/log/` **只留三天**；
  C 层崩溃栈单独 `F_HamLog_crash_*.log`。
- **日志不能把程序带崩**（全 try、`raiseExceptions=False`、Tee 用 `threading.local`）；窗口版 exe 的
  `sys.stdout` 是 None，Tee 必须支持；打包加 `--noinclude-data-files="file/log/*.log"`。

## 布局 / 尺寸（启动器）
- **`setFixedSize` 之后禁止再 `setMinimumHeight/setMaximumWidth`**（会让固定尺寸变区间 → 打开跳一下）。
- 内容超高**别用 `addSpacing(N)` 硬撑**，改 `QSpacerItem(…, Expanding)`，末尾别加 `addStretch`；
  验 `__main_layout_settle_smoke.py`（须 `QT_QPA_PLATFORM=windows`）。

## 提示与通知
- 所有 `.setToolTip(...)` 已整段注释（2026-09-29，47 处）→ `__sat_window_smoke` 的「提示列出数据源」必然失败。
- `show_toast()`：非模态、无边框、置顶、1 秒关、可堆叠、跟随主题；**分层窗口禁用 `QGraphicsDropShadowEffect`**。
- **删除日志无二次确认**（定稿）：直接删 + toast，安全网 = `snapshot_before()`；别改回 `QMessageBox.question`。
- **别用 `setEnabled(False)` 表示「忙」**（焦点会跳到「我的呼号」QLineEdit 并全选文本）；改文字 +
  `isRunning()` 拦重入。回归 `__update_btn_focus_smoke.py`。

## 卫星 / 过境视图
- `satellite_pred.py`（skyfield 离线）；`MAX_PREDICT_HOURS=240`、`MAX_SELECTED_SATELLITES=250`；数据源
  `file/tle_sources.txt` + 独立窗口（`#` 禁用、延迟只进 `_ROLE_DELAY`、按 NORAD 增量更新）；入口 project
  Ctrl+Shift+E / main 两处；**卫星名匹配规则两处同步**；选择框隐藏行必须 `setRowHidden`，超限靠
  `reset_requested` + `while True` 重开。
- 过境视图 = 极坐标天空图（**素色：无阴影/光晕/渐变/圆角**），**配色一律从 `QPalette` 混合**；可通联只把线画粗
  （2.4×）；**skyfield 没有 `ts.utc(jd=...)`**，JD 走 `ts.from_datetime(jd_to_datetime(jd))`。
- 「双方全部过境」用 `emphasis=(起,止)` + `auto_spans=True`；工具栏「过境视图」有选中用选中行，否则自动取
  最近一次并 `selectRow()`。
- **过境 / 地图窗口都是独立顶层窗口**（有父会随来源窗口一起最小化）。
- **经纬度 0° 是合法坐标**：不得用「均为 0 → 未设置」拦截。

## 多人日志 / 服务端
- **`remote_crypto.py` 是密码学唯一出处**（全帧加密、nonce 滑窗防重放、服务端先说话）；**退出必走
  `RemoteConnection.shutdown()`**；Qt 关窗只隐藏不触发 `destroyed`；独立服务端目录**自带两份副本 → 改协议须
  三份同步**；`main.py` 只留一个 `project_window`，须保留 `_confirm_replace_session()`。
- 服务端 exe：启动即建 `keys/`、`main.fhl`、`password_xml.txt`；`_app_dir()` **不能信 `sys.executable`**；带
  `--windows-uac-admin`，端到端验证要另打**去掉 uac-admin** 的临时包。

## 验证（离屏冒烟）
- `QT_QPA_PLATFORM=offscreen` 可真冒烟。**四坑**：槽里 `sys.exit()`；静态 `QFileDialog.*`/`QMessageBox.*` 自带
  模态循环；`os._exit()` 跳过 flush；**加密文件不给 `key` 会弹密钥框挂死**。
- 测试放 `tests/__*_smoke.py`；`set.py`/`project.py` 读设置用**硬编码 `file/m_xml.txt`**；**绝不能
  `git checkout -- file/…`**；`project.main()` 不触碰星历。

## 检查更新（`check_update.py` 唯一出处）
- **不 import Qt**：`check()` → `preview|error|latest|new`；`download()` 多线程分段（≥4 MB 才切、16 线程、每段
  ≥512 KB、失败退单线程）；`run_installer()` `/SILENT`；界面按钮在 `set.py`（`BgThread` + **模块级强引用**）。
- **进度窗**：`setValue()` 内部 `ensureDialog() → show()`，关窗后只要有帧就弹回 → 用 `state['closed']` 拦住并
  **先 `reset()` 再 `hide()`**；QProgressDialog **只增不减**。
- **QMessageBox 无 RejectRole 时叉号和 Esc 全失效**；要自定义按钮顺序就自己用 QDialog 排（Windows 下 Reject
  紧跟 Accept，role 救不了）。
- **下载/提示窗一律不可最大化**：`_no_maximize()` = `WindowMaximizeButtonHint=False` +
  `MSWindowsFixedSizeDialogHint=True` + `changeEvent` 里 `isMaximized() → showNormal()`；**别只删 hint**。
  进度窗还要 `WindowMinimizeButtonHint` + `Qt.NonModal` + `parent=None`，收尾用 `_alive()` 探活。
- **速度 / ETA 必须平滑**：1 s 滑动窗（`Speedometer`）、ETA 用累计平均 + 只降不升 + 死区随 eta 缩放；
  `_Meter.add()` 的**回调必须在锁内**；`done` 回退当帧不重算、**别重设基准**。
- **加速**：GitHub 限单连接 → 多线程 + `PART_TIMEOUT=15` + `choose_source()` 镜像择优（快 1.3 倍才换、换前验
  Range），走镜像时 `_spot_check()` 抽样比对；版本文件可写第三段 sha256。
- **预览版不自我更新**（含 `UTC`/`Preview` 就连网都不连）；`preview.yml` 改版本号**必须夹在 `pip install -e .`
  之后与 Nuitka 之前**；版本串**全 ASCII**（`Preview UTC-yyyyMMdd-HHmm 2.x.y`）。
- **下载前必查本地包**：`%LOCALAPPDATA%/F_HamLog/update`（`F_HAMLOG_UPDATE_DIR` 可覆盖）+ 同名 `.json` 元数据；
  `find_installer()` 判据 = sha256 → 元数据 → 仅 exe 名，**小于 1 MB 不认**；**判同一个包只认 exe 文件名**
  （`installer_name()` 归一化，不解析版本号）；选**重新下载必须 `force=True`**。
- 线上版本文件 `版本号 下载地址 [sha256]`；远端**不比本地新就算最新**。
## 打包 / 发布（命令细节见 `DETAILS.md`）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，默认 `main`；`main.yml` 手动 / `preview.yml` cron；`.github/inno/
  F HamLog 2.iss`；本机无 `gh`；取产物脚本双位置回退；`commit_artifacts='false'` 跳过回写分支。
- **「打包后没生效」先怀疑装到旧包**：扫 exe 字节找新字符串，**别用 mtime**（Inno 改成安装时刻）；锁屏下验界面
  `PrintWindow(hwnd,hdc,2)` + 先 `SetProcessDpiAwarenessContext(-4)`（`tests/__pkg_ui.py`）。
- **打包必须给 `PYTHONPATH=<repo>/src`**，否则产出「空壳 exe」；workflow 有空包检查（找不到 `f_hamlog.app_log`
  即失败）：**「打包成功」≠ 产物可用**。
- **产出目录靠 `--output-folder-name=main` 固定**；`.iss`、兼容版 zip、`.gitignore` 全按 `main.dist` 写死。
- **打包命令禁止 `--include-module`**（点分名必 FATAL）；`remote_crypto` 由 import 自动收录。
- **CI 的 pip 不许碰中文输出**：`PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` / `PIP_PROGRESS_BAR=off`；安装前复制成
  `%RUNNER_TEMP%\requirements-ci.txt` 再 `pip -r`。
- **`.iss` 的 `[Files]` 必须跟上数据文件名**（默认种子 `main.fhla`，种子带 `Check: NeedSeedMainFhla`）；
  改 `src/f_hamlog/file/` 被点名文件必须同步 `.iss`。
- 合并 `file/`：`.tle` 取更完整一侧；`m_xml.txt` 只差 `sat_last_update` 取较新；`memory/*.md` 全保留。
