# F HamLog 项目长期记忆

> 可复现细节见 `DETAILS.md`（文件结构 / 设置键 / 打包 / 卫星 API / 加密协议 / 发布 / i18n / 离屏坑）；
> 逐次改动见 `YYYY-MM-DD.md`。本文件只留**约定、决策与踩坑**，尽量写成可直接执行的硬规则。

## 基本约定
- PySide6 + Nuitka；**src 结构**（`src/f_hamlog/`，入口 `__main__.py`，兼容 `-m f_hamlog` 与直跑）。
  `pip install -e .` 开发；**包内模块不加 sys.path 守卫**（只 `__main__.py` 一处）。
- **版本单一来源 = `__init__.py.__version__`**（pyproject `dynamic`+`attr`），禁止硬编码；i18n 里用 `{}`。
- **退出前必须停掉所有后台 `QThread`**：长线程**一律继承 `bg_thread.BgThread`**（弱引用登记，不改行为）；
  `main.py` 的 `app.aboutToQuit` 连 `stop_all()`，`app.exec()` 返回后再调一次（幂等）。否则「线程在跑就被
  析构」→ Qt `qFatal`→`abort`（`0xc0000409` / `Qt6Core.dll`，**无 traceback**）；窗口 `closeEvent` 的 `wait()`
  只管「关这个窗」，管不了 quit / 关机 / 关最后窗口。
- **依赖版本单一来源 = 根目录 `第三方模块.txt`**（全 `==`）。workflow 用 `pip install -r`，**禁止另写包名
  列表**（会与 `hashFiles('第三方模块.txt')` 缓存键脱钩）；venv 缓存命中要**逐条比对版本**而非只验 import
  （`restore-keys` 前缀匹配会还原旧 venv）。
- **数据目录 = `F_HAMLOG_DATA_DIR` → exe 目录 → 模块目录 → cwd（垫底）**（`paths._app_base_dir()` 只认带
  标记文件的候选）。**绝不相信 cwd**：一律 `app_path('file/…')` 绝对路径（`backup.py` 曾造出假 `file/` →
  主窗打不开）。
- 本机 shell：`ls/head/tail/wc/rm/git` 有，缺 `dirname`/`cat`；Git Bash 会把 `/Dxxx` 当路径转换，
  调 ISCC 等要 `MSYS2_ARG_CONV_EXCL="*"`；venv `D://F-Dev//BIG//F_HamLog//.venv//Scripts//python.exe`；
  文件优先 Glob/Grep/Read/Edit。**不主动 git commit/push**；分支 `main` / `develop` / `develop-English`。

## 文件格式 `.fhl` / `.fhla`
- `.fhl` = 纯 `list[dict]`；`.fhla` = `{"xml": 属性块, "project": 记录}`。**读写统一走
  `project.read_project_file` / `save_project_file`**（按扩展名分派，传 `(records, key, meta)`；`.fhl` 的 meta
  恒 None，回写必须原样带回）。原 `fhla_rw.py` 已并入 `project.py`。
- **显示名定稿**：`.fhla` = **F HamLog 项目**，`.fhl` = **F HamLog 兼容项目**（`SAVE_FILTER_*` /
  `OPEN_FILTER_BOTH*`）。菜单动作「另存为 / 添加到 F HamLog项目」不改（动作名不是格式名）。
- **保存默认 `.fhla`**：`project_save_filters()` 第一条即默认 + `complete_project_suffix(path, sel)`
  （Qt 不补后缀，`sel` 空也补 `.fhla`；`*.fhl` 是 `*.fhla` 前缀，**先判 `.fhla`**）。
- **打开 `.fhl` 每次都问「迁移 / 暂不迁移」**（无「不再提示」、无开关）：`offer_migration()` → `(路径, 属性块)`；
  迁移 = 写同名 `.fhla`（**读回校验条数**）→ **删原 `.fhl`**，沿用密钥，失败不挡打开。默认日志同样问；
  `main.default_quick_project_path()` **优先 `main.fhla`** → `main.fhl` → 新装即 `.fhla`。
- `encrypted` 只是声明，**以字节能否 UTF-8 解为准**；**不记「创建者 / 创建时间」这类首次编辑属性**
  （迁移也不写）。`.fhla` 只记 `last_editor` / `last_edit_time` / `last_version` / `encrypted` / 自定义字段键；
  **「打开即自动保存」不算编辑**（打开时快照比对；字段定义变更靠 `_fhla['dirty']`）。
- **操作者 = 设置里的呼号**（`m_call` 大写去空白），没填退回系统用户名（`current_editor()`）；
  `load_settings()` 用 `utf-8-sig` + `literal_eval`（BOM 会让旧 `eval` 静默读不到呼号）。
- **项目属性 = `Alt+I`**；`.fhl` 直接提示「不支持的格式」（无属性块，不做半展示）。

## 自定义日志字段（`.fhla` 专属，细节见 `DETAILS.md`）
- **只填字段名称**；键 = 首次创建时的名称（撞名 `_2`），改名只改显示名 → 记录键不动，不丢数据。
- 整表含**标准 20 行**；**该表顺序 = 「新建日志 / 更多信息」行序 = 主页列序** → 呼号大写委托**按 key
  找行号，不能写死行 2/3**。
- 「必填」「在主页显示」**所有字段可改**（默认 `STANDARD_REQUIRED_KEYS` / `MAIN_DEFAULT_KEYS`），
  **xml 只记偏离默认的键**；落盘 `other_item` + `field_order` + `field_meta`；**「恢复默认」只重置表格，
  点「保存更改」才写盘**。**`.fhl` 一律不给**（管理窗口拒绝、`custom_fields()` 恒空、录入只 20 行）。

## 主题 / 对话框 / i18n（细节见 `DETAILS.md`）
- 浅深**一律平台原生调色板**：不建兜底色、不上全局 QSS、不用 `Fusion`（`5e9fcbe` 已否决）。颜色走
  `theme.hint_css()/warn_css()/link_color()/watch_theme()`，禁止写死；**验证颜色看 `grab()` 像素**。
- **抓像素必乘 DPR**：本机 125% 缩放，`viewport().grab().toImage()` 是**设备像素**图，
  `pixelColor(x,y)` 必须传「逻辑坐标 × `devicePixelRatio()`」；直接用逻辑坐标会采到隔壁行
  （曾误判「悬停只在前两行生效」「斑马纹错乱」，全是假象）。行底色别在行中点取（长地址
  省略后文字伸得到），取「省略地址与右端延迟之间空白带」的众数。
- **原生 windows11 样式两个坑**（item view）：① 悬停态用调色板 `Highlight` **整行填充**
  （变蓝）——QSS 必须显式写 `::item:hover`；② 焦点行描**纯黑大框**（`PE_FrameFocusRect`，
  由 `State_HasFocus` 触发）——自绘委托里 copy option 后剥掉 `State_HasFocus`。
- **星历数据源窗口观感定稿**（`tle_source_window.py`）：悬停 = `blend(Window, WindowText, 0.08)`
  的跟随主题浅灰（浅 #e0e0e0 / 深 #303030），文字色不动；选中 = 链接色文字 + 透明底，
  `:hover:selected` 维持选中观感；**不描黑框**。验证 `tests/__tle_hover_gray_smoke.py`
  （必须 `QT_QPA_PLATFORM=windows`）。
- **文件对话框一律原生静态调用**（自绘+汉化已否决）；`dialog_defaults.desktop_dir()` 默认桌面、文件名为空。
- i18n：中文是源语言，显示时查词表；**动态文案逐段 `i18n.tr` 后再拼**；单元格固定文案用
  `bind_cell_texts`；文件对话框在**调用处**翻；`translate()` 幂等；**窗口尺寸在 `show()` 之后量**；
  **词表别加重复键**。设置持久化 `file/m_xml.txt`，各模块只改自己的键。

## 主表格 / 大项目性能（细节见 `DETAILS.md`「大型项目性能」）
- 勾选/「更多」列**一律自绘委托**，**禁止逐行 `setCellWidget`**；勾选唯一权威 = `_checked_rows`。
- **不启用 `stretchLastSection`**、不强制行高；每列显式设宽（`MAIN_COL_WIDTHS` / `CUSTOM_COL_WIDTH`），
  「选择」45 恒首列、「更多」80 恒末列。改表格前先 `git show HEAD:project.py` 对照。
- 重建要**还原滚动位置**（`QTimer.singleShot(0, …)`）；`table_update(scroll_to_bottom=True)` 仅三处调用。
- `save()` 有「未变更跳过」（`_last_written`）但首次必须执行；`write_fhl_file` 必须 `json.dumps` 后一次性
  `f.write`（禁止 `json.dump`）。
- **内容比较一律用「值快照」**（`_content_snap()` 存 `[dict(r) …]` 基线，`==` 比），**别再退回
  `json.dumps(...) == ...`**（定时器 1.5 s 反复调）；**单条编辑 / 少量删除禁止整表重建**
  （`table_refresh_row` / `table_remove_rows`），但 **date / time 变了必须 `table_update()`**。
- 撤销点用**逐条浅拷贝**（别 `deepcopy`），撤销栈按「步数 + 记录总数」双重限流；`_fill_rows` 期间
  `gc.disable()`；打开项目**只建一次表**。
- 改表格/保存路径前先跑 `tests/__perf_tick_bench.py`、`__perf_long_fhl_bench.py` 对照；**格式与落盘函数
  不允许因性能原因改动**，验证 `tests/__inplace_edit_smoke.py`。

## 运行日志（app_log.py，细节见 `DETAILS.md`）
- `__main__.py`（import main **之前**）与 `main.main()` 各调一次 `app_log.setup()`（幂等）；落
  `file/log/F_HamLog_YYYY-MM-DD.log`，**只留三天**，C 层崩溃栈单独 `F_HamLog_crash_*.log`。
- 硬约束：**日志不能把程序带崩**（全 try、`raiseExceptions=False`、Tee 用 `threading.local` 防递归）；
  **窗口版 exe 的 `sys.stdout` 是 None**，Tee 必须支持原流为 None。打包加
  `--noinclude-data-files="file/log/*.log"`；验证 `tests/__app_log_smoke.py`。

## 布局 / 尺寸（启动器）
- **`setFixedSize` 之后禁止再 `setMinimumHeight/setMaximumWidth`**：会把固定尺寸解成区间，show() 两遍
  排布取不同值 → 「打开时跳一下」（`_style_btn` 曾如此）。
- 内容比窗口高时**别用 `addSpacing(N)` 硬撑**（溢出高度被布局从可压缩子项挤，且发生在 show() 之后），
  改 `QSpacerItem(…, QSizePolicy.Expanding)` 自吸收，末尾别再加 `addStretch`。
- 验证 `tests/__main_layout_settle_smoke.py`（show() 瞬间快照 → 300ms 再比）；**必须
  `QT_QPA_PLATFORM=windows`**，离屏字体小、复现不出来。

## 提示与通知
- 所有 `.setToolTip(...)` 已整段注释（2026-09-29，47 处）→ `__sat_window_smoke` 的「提示列出数据源」
  **必然失败**（既有状态，与 i18n 无关）。
- `toast_tip.show_toast(text, parent)`：非模态、无边框、置顶、1 秒关、可堆叠、跟随主题；
  **Windows 分层窗口禁用 `QGraphicsDropShadowEffect`**（脏矩形越界），用 1px 边框；宽度只改文件顶部常量。
- **删除日志无二次确认**（定稿）：直接删 + toast，安全网 = `snapshot_before()`（Ctrl+Z 整表还原）；
  删除后处理 `_checked_rows`。**别再改回 `QMessageBox.question`**。

## 卫星 / 过境视图（视图细节见 `DETAILS.md`「过境 / 通联视图」）
- `satellite_pred.py`（skyfield 离线）；`MAX_PREDICT_HOURS=240`、`MAX_SELECTED_SATELLITES=250`；数据源 =
  `file/tle_sources.txt` + 独立窗口（`#` 禁用、延迟自动探测只进 `_ROLE_DELAY`、按 NORAD 增量更新）；入口
  project「卫星→通联预测」Ctrl+Shift+E / main「卫星过境」「通联预测」；**改卫星名匹配规则时两处同步**；
  选择框**隐藏行必须 `setRowHidden`**，超限靠 `reset_requested`+`while True` 重开。
- 过境视图 = 极坐标天空图（**素色定稿：无阴影/光晕/渐变/圆角**），**配色一律从 `QPalette` 混合、禁止
  写死**；可通联只把线画粗（2.4×）；**skyfield 没有 `ts.utc(jd=...)`**，JD 走 `ts.from_datetime(jd_to_datetime(jd))`。
- 「双方全部过境」用 `emphasis=(起,止)` + `auto_spans=True`，每站 `_pass_span()` 求 AOS→LOS，时间轴取并集。
- 工具栏「过境视图」：**有选中用选中行，没有就自动取最近一次**并 `selectRow()`；表格为空才提示。
- **过境 / 地图窗口都是独立顶层窗口**（`SkyWindow(None, …)` / `MapWindow(None, …)`，`_source` 只定位置）：
  有父对象会变「被拥有的窗口」，Windows 下最小化来源窗口就跟着最小化。**新开窗口一律照此**。
- **经纬度 0° 是合法坐标**：不得用「经纬度均为 0 → 未设置」拦截。

## 多人日志 / 服务端
- **`remote_crypto.py` 是密码学唯一出处**（全帧加密、nonce 滑动窗口防重放、服务端先说话）；**退出必走
  `RemoteConnection.shutdown()`**；Qt 关窗只隐藏不触发 `destroyed`（资源在 `install_close_guard`）；独立服务端
  目录**自带两份副本 → 改协议须三份同步**；`main.py` 只保留一个 `project_window` 引用，改窗口管理必须保留
  `_confirm_replace_session()`。
- 服务端 exe：启动即建 `keys/`、`main.fhl`、`password_xml.txt`；`_app_dir()` **不能信 `sys.executable`**；
  带 `--windows-uac-admin`，端到端验证须另打**去掉 uac-admin** 的临时包。

## 验证（离屏冒烟）
- `QT_QPA_PLATFORM=offscreen` 可真实冒烟（主窗/卫星/互通/批量/服务端/地图）。**四个坑**：① 槽里 `sys.exit()`
  终止进程；② 静态 `QFileDialog.*`/`QMessageBox.*` 自带模态循环（`QDialog.exec` 拦不住）；③ `os._exit()`
  跳过 flush；④ **加密文件不给 `key` 去读会弹密钥框挂死**。
- 测试放 `tests/`（`__*_smoke.py`，结果 `__*_out.txt` 已 gitignore）；`set.py`/`project.py` 读设置用**硬编码
  `file/m_xml.txt`**，只 patch 常量不够（需 chdir 或字节还原）；**绝不能 `git checkout -- file/…`**；
  `project.main()` 不触碰星历（唯一自动更新入口是 `main.py` 的 `AutoTleUpdater`）。

## 打包 / 发布
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，默认分支 `main`；`main.yml`（手动发布，唯一能发 Release）/
  `preview.yml`（cron 预览，必须在 `main`）/ `.github/inno/F HamLog 2.iss`；本机无 `gh`、无 token；
  **取产物脚本双位置回退**（先 `兼容版/` 再仓库根）。
- **打包必须显式给 `PYTHONPATH=<repo>/src`**：否则 Nuitka 把 `__main__.py` 当孤立脚本编译，**零告警**产出
  「空壳 exe」（双击没反应、无日志）。两个 workflow 的「校验打包产物」已内置**空包检查**（exe 字节里找不到
  `f_hamlog.app_log` 即失败）。口诀：**「打包成功」≠ 产物可用**。
- **产出目录名 = `main.dist` / `main.build`，靠 `--output-folder-name=main` 固定**（否则变 `__main__.dist`，
  并让 `actions/cache` 的 `main.build` 空转、每次全量重编）；`.iss` 的 `SourceDistDir`、兼容版 zip、
  `.gitignore` 全按 `main.dist` 写死。**这行别删**。
- **打包命令禁止 `--include-module`**：它在「编译主模块之前」解析，点分名必然 FATAL；`remote_crypto` 由
  `project.py` 的 `from f_hamlog import remote_crypto` 自动跟随收录。
- **CI 的 pip 不许碰中文输出**：runner 代码页 cp1252，pip 26 用 rich 渲染，一写中文（需求文件名
  「第三方模块.txt」）就 `UnicodeEncodeError` 非 0 退出。两个 workflow 必须保持 workflow 级 `PYTHONUTF8=1` /
  `PYTHONIOENCODING=utf-8` / `PIP_PROGRESS_BAR=off`；步骤内再设 + `[Console]::OutputEncoding`；安装前复制成
  `%RUNNER_TEMP%\requirements-ci.txt` 再 `pip -r`（**缓存键仍 hashFiles 原名**）；装完逐条复核版本。
- **`.iss` 的 `[Files]` 引用必须跟得上数据文件名**（打包脚本里最容易漏的一处）：默认日志种子已从 `main.fhl`
  改成 **`main.fhla`**，曾因写死旧名 → ISCC `Compile aborted`，白跑 54 分钟构建（2026-10-18）。该种子带
  `Check: NeedSeedMainFhla`：**有旧 `main.fhl` 就不种空 `.fhla`**（否则老用户以为记录丢了）。改
  `src/f_hamlog/file/` 里被点名的文件后必须同步 `.iss`。**本机试编译 / 运行时验证的具体命令见
  `DETAILS.md`「发布流程：`.iss` 与 PowerShell 补充」**。
- 合并 `file/` 数据文件：`.tle` 取更完整一侧；`m_xml.txt` 只差 `sat_last_update` 取较新；
  `.workbuddy/memory/*.md` **双方全保留**。
