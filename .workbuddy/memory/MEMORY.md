# F HamLog 项目长期记忆

> **可复现细节一律见 `DETAILS.md`**（文件结构 / 设置键 / 打包 / 卫星 API / 加密协议 / 发布 /
> i18n 机制 / 离屏坑）；逐次改动见 `YYYY-MM-DD.md`。本文件只留**约定、决策与踩坑**。

## 基本约定
- PySide6 桌面应用，Nuitka 打包；**src 结构**（包 `src/f_hamlog/`，入口 `__main__.py`，
  兼容 `-m f_hamlog` 与直跑）。开发用 `pip install -e .`，**包内模块不加 sys.path 守卫**（只 `__main__.py` 一处）。
- **版本单一来源 = `__init__.py.__version__`**（pyproject 用 `dynamic`+`attr`），一切版本号禁止硬编码（i18n 用 `{}`）。
- **退出前必须停掉所有后台 `QThread`**：所有长生命周期线程**一律继承
  `bg_thread.BgThread`**（只做弱引用登记，不改行为），`main.py` 里
  `app.aboutToQuit` 连 `bg_thread.stop_all()`、`app.exec()` 返回后再调一次（幂等）。
  原因：Qt 在「线程还在跑就被析构」时走 `qFatal`→`abort`，Windows 上是
  `0xc0000409` / 出错模块 `Qt6Core.dll`，**没有任何 Python traceback**。各窗口
  `closeEvent` 里的 `wait()` 只覆盖「用户关这个窗」，覆盖不到 quit / 关机 / 最后窗口关闭。
- **依赖版本单一来源 = 根目录 `第三方模块.txt`**（requirements 格式，全部 `==` 锁定，含
  运行时 7 个 + 仅打包用的 nuitka）。两个 workflow 用 `pip install -r` 装，**禁止在
  workflow 里另写包名列表**（会与 `hashFiles('第三方模块.txt')` 缓存键脱钩）；venv 缓存
  命中时**逐条比对版本**而不是只验 import（`restore-keys` 前缀匹配会把旧 venv 还回来）。
- **数据目录 = `F_HAMLOG_DATA_DIR` → exe 目录 → 模块目录 → cwd（垫底）**（`paths._app_base_dir()`
  只认带标记文件的候选）。**绝不相信 cwd**：数据文件一律 `app_path('file/…')` 绝对路径，
  禁止 cwd 相对路径写（`backup.py` 曾造出假 `file/` → 主窗打不开，2026-10-16）。
- 本机 shell 部分可用（`ls/head/tail/wc/rm/git`；缺 `dirname`/`cat`）；venv
  `D://F-Dev//BIG//F_HamLog//.venv//Scripts//python.exe`；文件优先 Glob/Grep/Read/Edit。
- **不主动 git commit/push**；分支 `main`（发版）/ `develop` / `develop-English`。

## 文件格式 `.fhl` / `.fhla`
- `.fhl` = 纯 `list[dict]`；`.fhla` = `{"xml": 属性块, "project": 记录}`。**读写统一走
  `project.read_project_file` / `save_project_file`**（按扩展名分派，上传送三元组 `(records, key, meta)`，
  `.fhl` 的 meta 恒 None；回写必须把 meta 原样带回）。实现在 `project.py`，原 `fhla_rw.py` 已并入删除。
- **显示名定稿**：`.fhla` = **F HamLog 项目**，`.fhl` = **F HamLog 兼容项目**（常量 `SAVE_FILTER_*` /
  `OPEN_FILTER_BOTH*`）。菜单动作「另存为 / 添加到 F HamLog项目」不改（动作名不是格式名）。
- **保存默认 `.fhla`**：`project_save_filters()`（第一条即默认）+ `complete_project_suffix(path, sel)`
  （Qt 不补后缀，`sel` 为空也补 `.fhla`；判 sel 时 `*.fhl` 是 `*.fhla` 前缀，**先判 `.fhla`**）。
- **打开 `.fhl` 每次都问「迁移 / 暂不迁移」**（无「不再提示」、无开关）：`offer_migration(...)` →
  `(实际路径, 属性块)`；迁移 = 写同名 `.fhla`（**读回校验条数**）→ **删原 `.fhl`**，沿用密钥，
  创建者 = 本次操作者；失败不挡打开。默认日志也问：`main.default_quick_project_path()`
  **优先 `main.fhla`** → `main.fhl` → 新装即 `.fhla`。
- `encrypted` 只是声明，**以字节能否 UTF-8 解为准**；创建者只认第一次落盘（幂等）；
  **「打开即自动保存」不算编辑**（打开时快照比对；改字段定义靠 `_fhla['dirty']`）。
- **操作者 = 设置里的呼号**（`m_call` 大写去空白），没填才退回系统用户名（`current_editor()`）；
  `load_settings()` 用 `utf-8-sig` + `literal_eval`（BOM 会让旧 `eval` 静默读不到呼号）。
- **项目属性 = `Alt+I`**；`.fhl` 直接提示「不支持的格式」（无属性块，不做半展示）。

## 自定义日志字段（`.fhla` 专属）
- 入口「文件 → 自定义日志字段」：说明 + 表格 + 添加/删除/上移/下移/**恢复默认**/保存更改/关闭。
  **只填字段名称**（键 = 首次创建时的名称，撞名 `_2`；改名只改显示名，记录键不动 → 不丢数据）。
- 整表含**标准 20 行**（名称灰显不可改/删，但可一起排队）；**这张表的顺序 = 「新建日志 / 更多信息」
  行序 = 主页列序**（一处排序三处跟着走）→ 呼号大写委托**按 key 找行号，不能写死行 2/3**。
- 「必填」「在主页显示」**所有字段都能改**（默认值 = 历史行为 `STANDARD_REQUIRED_KEYS` /
  `MAIN_DEFAULT_KEYS`）；改回默认即删覆盖项，**xml 里只记偏离默认的键**。
- 落盘：`other_item`（键→名称）+ `field_order` + `field_meta`（可选键）。**「恢复默认」只重置表格，
  点「保存更改」才写盘**；顺序回到历史默认时 `field_order` 整个省掉（文件回到出厂状态）。
- **`.fhl` 一律不给**：管理窗口拒绝、`custom_fields()` 恒空、录入窗口只 20 行。

## 主题 / 对话框 / i18n（细节见 `DETAILS.md`）
- 浅深**一律平台原生调色板**，不建兜底色、不上全局 QSS、不用 `Fusion`（`5e9fcbe` 已被否决）。
  颜色走 `theme.hint_css()/warn_css()/link_color()/watch_theme()`，禁止写死；**验证颜色看 `grab()` 像素**。
- 设置持久化 `file/m_xml.txt`（`eval` 字面量 dict），各模块只改自己的键。
- **文件对话框一律原生静态调用**（自绘 + 汉化已被否决）；`dialog_defaults.desktop_dir()` 默认桌面、文件名为空。
- i18n：中文是源语言，显示时查词表（`i18n.py` + `i18n_zh_en.py`）；**动态文案逐段 `i18n.tr` 后再拼**
  （整条拼完再翻会漏翻）；单元格固定文案用 `bind_cell_texts`；文件对话框必须**调用处**翻；
  切语言原地重译、`translate()` 幂等；**窗口尺寸在 `show()` 之后量**；**词表别加重复键**。

## 主表格（长日志性能）
- 勾选/「更多」列**一律自绘委托**，**禁止逐行 `setCellWidget`**；勾选唯一权威 = `_checked_rows`。
- **不启用 `stretchLastSection`**、不强制行高；每列显式设宽（`MAIN_COL_WIDTHS` / `CUSTOM_COL_WIDTH`）。
  「选择」45 恒首列、「更多」80 恒末列。改表格前先 `git show HEAD:project.py` 对照。
- 重建要**还原滚动位置**（`QTimer.singleShot(0, …)`）；`table_update(scroll_to_bottom=True)` 仅三处调用。
- `save()` 有「未变更跳过」（`_last_written`），首次必须执行；`fhl_rw.write_fhl_file` 必须
  `json.dumps` 后一次性 `f.write`（禁止 `json.dump`）。

## 运行日志（app_log.py）——2026-10-17 新增
- **入口装配**：`__main__.py`（import main **之前**）与 `main.main()` 开头各调一次
  `app_log.setup()`（幂等）。落盘 `app_path('file/log')`，按天一个文件
  `F_HamLog_YYYY-MM-DD.log`，**只留三天**（今天/昨天/前天，启动时清更早的）；
  C 层崩溃栈单独 `F_HamLog_crash_YYYY-MM-DD.log`（faulthandler 常开句柄）。
- **四路来源**：根 logger + `sys.stdout/stderr` 换成 `_StreamTee`（print 也进日志，
  stdout=INFO、stderr=ERROR）+ `sys.excepthook`/`threading.excepthook`（完整 traceback）
  + `faulthandler`/`qInstallMessageHandler`（Qt 警告）。
- 两条硬约束：**日志自己不能把程序带崩**（全部 try 兜住、`logging.raiseExceptions=False`、
  Tee 用 `threading.local` 防「写失败 → stderr 回灌 → 再失败」的递归）；
  **窗口版 exe 下 `sys.stdout` 是 None**，Tee 必须支持原流为 None（只记日志）。
- `_excepthook` 只调用**定制**的旧钩子；默认钩子改为直接写 `sys.__stderr__`，
  否则同一段 traceback 会经 Tee 在日志里出现两遍。
- 打包命令加 `--noinclude-data-files="file/log/*.log"`（别把开发日志打进包）；
  `.gitignore` 已忽略 `src/f_hamlog/file/log/`。验证：`tests/__app_log_smoke.py`（21 项）。

## 提示与通知
- 所有 `.setToolTip(...)` 已整段注释（2026-09-29，47 处）→ `__sat_window_smoke` 的「提示列出数据源」
  **必然失败**（既有状态，与 i18n 无关）。
- `toast_tip.show_toast(text, parent)`：非模态、无边框、置顶、1 秒关、可堆叠、跟随主题；
  **Windows 分层窗口禁止 `QGraphicsDropShadowEffect`**（脏矩形越界），用 1px 边框；
  改宽度只改该文件顶部常量区。
- **删除日志无二次确认**（定稿）：直接删 + toast，安全网是 `snapshot_before()`（Ctrl+Z 整表还原）；
  删除后处理 `_checked_rows`（批量清空 / 单条行号前移）。**别再改回 `QMessageBox.question`**。

## 卫星 / 多人日志 / 服务端 / 验证 / 发布
- **打包必须显式给 `PYTHONPATH=<repo>/src`**（本地手工打包同 CI）：Nuitka 解析
  `--main=src/f_hamlog/__main__.py` 时若 `f_hamlog` 不在 `sys.path`，会把 `__main__.py` 当孤立脚本
  编译，**零告警**产出「空壳 exe」（双击没反应、无日志，跑起来才见 `No module named 'f_hamlog'`）。
  本地老式 `pip install -e .` 的 `.pth` 恰好在 path 上，所以本机常看不出问题。两个 workflow 的
  「校验打包产物」已内置**空包检查**（exe 字节里找不到 `f_hamlog.app_log` 直接失败）。
  验证口诀：**「打包成功」≠产物可用**，必须扫符号或真跑一次。
- 卫星：`satellite_pred.py`（skyfield 离线）；`MAX_PREDICT_HOURS=240`、`MAX_SELECTED_SATELLITES=250`；
  数据源 = `file/tle_sources.txt` + 独立窗口（`#` 禁用、延迟自动探测只进 `_ROLE_DELAY`、按 NORAD 增量更新）；
  入口 project「卫星→通联预测」Ctrl+Shift+E / main「卫星过境」「通联预测」；
  **改卫星名匹配规则时两处同步**；选择框**隐藏行必须 `setRowHidden`**，超限靠 `reset_requested`+`while True` 重开。
- 多人日志：**`remote_crypto.py` 是密码学唯一出处**（全帧加密、nonce 滑动窗口防重放、服务端先说话）；
  **退出必走 `RemoteConnection.shutdown()`**；Qt 关窗只隐藏不触发 `destroyed`（资源在 `install_close_guard`）；
  独立服务端目录**自带两份副本 → 改协议须三份同步**；`main.py` 只保留一个 `project_window` 引用，
  改窗口管理必须保留 `_confirm_replace_session()`。
- 服务端 exe：启动即建 `keys/`、`main.fhl`、`password_xml.txt`；`_app_dir()` **不能信 `sys.executable`**；
  带 `--windows-uac-admin`，端到端验证须另打**去掉 uac-admin** 的临时包。
- 验证：`QT_QPA_PLATFORM=offscreen` 可真实冒烟（主窗/卫星/互通/批量/服务端/地图）。**四个坑**：
  ① 槽里 `sys.exit()` 终止进程；② 静态 `QFileDialog.*`/`QMessageBox.*` 自带模态循环（换 `QDialog.exec` 拦不住）；
  ③ `os._exit()` 跳过 flush；④ **加密文件不给 `key` 去读会弹密钥框挂死**。
  测试放 `test/`（`__*_smoke.py` 等，结果 `__*_out.txt` 已 gitignore）；`set.py`/`project.py` 读设置用
  **硬编码 `file/m_xml.txt`**，只 patch 常量不够（需 chdir 或字节还原）；**绝不能 `git checkout -- file/…`**；
  `project.main()` 不触碰星历（唯一自动更新入口是 `main.py` 的 `AutoTleUpdater`）。
- 发布：仓库 `github.com/Mubi-Baihua/F_HamLog`，默认分支 `main`，只有 `main.yml`（手动发布，唯一能发
  Release）/ `preview.yml`（cron 预览，必须在 `main`）/ `.github/inno/F HamLog 2.iss`；本机无 `gh`、无 token；
  **取产物脚本双位置回退**（先 `兼容版/` 再仓库根）。
- **打包产出目录名 = `main.dist` / `main.build`，靠命令行 `--output-folder-name=main` 固定**
  （Nuitka 默认取主模块文件名 → `--main=src/f_hamlog/__main__.py` 会变成 `__main__.dist`，
  同时让 `actions/cache` 的 `main.build` 空转、每次全量重编）；`.iss` 的 `SourceDistDir`、
  兼容版 zip、`.gitignore` 都按 `main.dist` 写死。**退出码无关，这行别删**。
- **打包命令禁止 `--include-module`**：它在「编译主模块之前」解析，那阶段只认主模块目录里的
  顶层名，点分名（`f_hamlog.remote_crypto`）必然 FATAL；`remote_crypto` 由 `project.py` 的
  `from f_hamlog import remote_crypto` 自动跟随收录，不需要额外 include。
- 合并 `file/` 数据文件：`.tle` 取更完整一侧；`m_xml.txt` 只差 `sat_last_update` 取较新；
  `.workbuddy/memory/*.md` **双方全保留**。
