# F HamLog 项目长期记忆

> 只留**硬规则**；来龙去脉见 `YYYY-MM-DD.md`。

## 基本约定
- PySide6 + Nuitka，src 结构（`src/f_hamlog/`，入口 `__main__.py`）；包内模块不加 sys.path 守卫。
- 版本单一来源 = `__init__.py.__version__`（pyproject `dynamic`+`attr`；**main.yml 也读它**，workflow 不手填）；i18n 用 `{}`。
- 依赖版本单一来源 = 根 `第三方模块.txt`（全 `==`）；workflow 只 `pip install -r`。
- 数据目录 = `F_HAMLOG_DATA_DIR` → exe 目录 → 模块目录 → cwd；**绝不相信 cwd**，一律 `app_path('file/…')`。
- 长线程一律继承 `bg_thread.BgThread`；`aboutToQuit` → `stop_all()`（`exec()` 后调，幂等），否则 Qt abort（0xc0000409，无 traceback）。
- 本机：有 `ls/head/tail/wc/rm/git`，缺 `dirname/cat`；ISCC 要 `MSYS2_ARG_CONV_EXCL="*"`；venv `.venv/Scripts/python.exe`；**不主动 commit/push**；分支 `main`/`develop`/`develop-English`。

## git
- 部分克隆：合并停在 `Updating …` 是在回源下 blob（Inno 里 ~70 MB exe），不是卡死。
- 代理下必须用**环境变量**：`GIT_CONFIG_COUNT=2` + `http.sslBackend=openssl` + `http.sslVerify=false`（`-c` 传不进子 fetch）。
- 中断合并留 0 字节 `.git/index.lock` → 确认无 `git.exe` 后 `rm -f`。
- 误报 divergent（拉非跟踪分支）：`git rev-list --left-right --count origin/X...X` 得 `N 0` 即纯落后 → `merge --ff-only`。

## 文件格式 `.fhl` / `.fhla` / `.adi`
- `.fhl` = `list[dict]`；`.fhla` = `{"xml": 属性块, "project": 记录}`；读写**只走** `read_project_file`/`save_project_file`（`(records, key, meta)`，`.fhl` 的 meta 恒 None）。
- 显示名：`.fhla` = F HamLog 项目，`.fhl` = F HamLog 兼容项目；菜单动作名不改。
- 保存默认 `.fhla`（`project_save_filters()` 首条 + `complete_project_suffix()`）；`*.fhl` 是 `*.fhla` 前缀 → **先判 `.fhla`**；打开用 `project_open_filters()`。
- `.adi`/`.adif`：`is_adi_path()` → `input_adi.read_adi_records` / `export_adi.write_adif_file`；无属性块、无加密；**没改动不写盘**（重写丢未映射标签）。
- 「项目属性」「自定义日志字段」共用 `format_reject_text(path, feature)`，**按真实格式分开措辞**：`.fhla` 走属性块/正常窗口；`.adi` 说 ADI（不提 .fhl）；`.fhl` 才说「纯记录格式」；未保存说「先保存」。ADI 的提示**版式与 .fhl 一致**（都是 QMessageBox 提示，不摆条数/大小信息卡）。
- ADI **也有「加密此项目」入口**（别藏功能），点了走 `aes_open_` 首行的 ADI 分支给「不支持加密」提示。
- 开 `.fhl` 每次问「迁移/暂不迁移」：迁移 = 写同名 `.fhla`（读回校验条数）→ 删原 `.fhl`；`default_quick_project_path()` 优先 `main.fhla` → `main.fhl`。
- `encrypted` 只是声明，**以字节能否 UTF-8 解为准**；不记创建者/创建时间；「打开即自动保存」不算编辑；属性窗口 `Alt+I`；操作者 = 设置里的呼号（大写去空白），空则系统用户名。
- **加密 / 解密必须走 `_write_project_now()`**（`_write_project_file` 直写），**不能靠 `save(message=False)`**：静默保存有「内容没变就跳过」，会把加密动作整个吞掉（表现为「加密后仍是明文」）；失败要回滚 key。改 key 时置 `_fhla['dirty']=True` 才算一次编辑。
- 新建密钥只走 `fhl_rw.get_new_key_dialog()`（**两次输入**、空/不一致重弹）；读加密文件仍用 `get_user_key_dialog()`（单次）。
- `osave()` 会**换 save_path** 到新文件（标题跟着走）；`save_path` 为空时加密前必须先存盘。

## 自定义字段（`.fhla` 专属）
- 只填字段名称；键 = 首次创建名（撞名 `_2`），改名只改显示名 → 记录键不动。
- 含标准 20 行；**该表顺序 = 新建行序 = 更多信息行序 = 主页列序** → 呼号大写委托按 key 找行号。
- 「必填」「在主页显示」所有字段可改；xml 只记偏离默认的键；「恢复默认」只重置表格、点保存才写盘；**`.fhl` 一律不给**。
- **搜索 / 查找替换 / 统计图的字段清单唯一出处 = `field_entries()`**（`search_field_choices()` + `bind_field_combo()`），**禁止再写死清单**（写死 = 自定义字段搜不到）；自定义字段名不翻（`combo._i18n_skip=True`），统计图 `skip=('date','time')`。

## 多窗口 / 并发写
- 记录列表 / 密钥 / 子窗口引用**属于单个窗口**（`project.main()` 局部变量 + `nonlocal`，`_set_file()`/`_set_key()`）；模块级同名变量只是镜像，**逻辑里不许读**。
- 项目窗口可多开（`project_windows` + `_new_project_window()`）；`_confirm_replace_session()` 是恒 True 空壳。
- 未保存备份**按文件路径分开**（`backup.project_backup_path()`）；启动用 `list_project_backups()` 逐个恢复。
- **备份文件只在真有未保存内容时存在**：`clear_backup` = 删文件（不存在就什么都不做）、`write_backup(空)` 也删除、开窗**不写**（`_bk_tick` 仅在脏时写）、`list_project_backups` 顺手清 0 字节空壳。别再生成 `project_backup_<hash>.fhl` 空壳。
- 同文件可能被多窗口/批量记录同时写：`_disk` 记 `(mtime_ns, size)`；`save()` 里**外部改动检查在「内容没变就跳过」之前**；本窗口没改过 → `_reload_from_disk()` 且不写盘；写盘后 `notify_file_changed(path, skip=window)`。重载两条护栏：**有未保存改动**、**开着单元格编辑器** → 不重载。

## 批量记录（`batch_project.py`）
- 「自动保存到日志文件」= **边改边写**：`cellChanged`/增删列/撤销重做 → `_live_touch()`（400 ms 防抖）→ `_live_sync()`；`sync_io = {read, write}`。
- 只写**填完整**的列（必填 + 日期/时间格式），全空 = 删除；每列记 `pos`+`wrote` → 就地改那条，对不上按内容找回、再不行才追加（**宁可多一条也不覆盖**）；删列靠 `live['gone']`。
- 「完成」先 `_live_flush()`，成功即关窗；不能实时同步（多人日志/加密无密钥/未落盘）才退回 `on_saved`/`auto_pick`；取消勾选又完成用 `live['detached']` 去重。
- 未保存判定：`_bk_is_dirty()` = 还有「填了没填完」的列（`_pending_input()`）。
- 复选框**一律叫「日志文件」**，默认通联日志不挂文件名；`choose_save_target(parent, heading)` 只有标题 + 四条单选项，**不摆灰色说明**。

## 主表格 / 性能
- 主表与搜索结果表是**单元格选择**（`SelectItems`，点哪格只亮哪格）；因此 **`selectedRows()` 恒为空**，要行号一律 `sorted({i.row() for i in ...selectedIndexes()})`（`get_selected_row_indexes` / 搜索窗「复制选中行」）；「定位到此条」只 `setCurrentCell(orig,0)`，不 `selectRow`。
- 勾选 /「更多」列**一律自绘委托**，**禁止逐行 `setCellWidget`**；勾选权威 = `_checked_rows`；不启用 `stretchLastSection`、不强制行高、每列显式设宽（「选择」45、「更多」80）；重建要还原滚动位置。
- 内容比较用值快照（`_content_snap()` + `==`），**别比 `json.dumps`**；**单条编辑/少量删除禁止整表重建**（`table_refresh_row`/`table_remove_rows`），date/time 变了必须 `table_update()`。
- 列表变了先 `_table_sync_from_file(old)`：少量改动 → `table_refresh_row`；纯末尾追加 → `_append_table_rows`；删除/顺序变 → `table_update(persist=False)`。
- 撤销点逐条浅拷贝（别 `deepcopy`）；`_fill_rows` 期间 `gc.disable()`；`write_fhl_file` 必须一次 `f.write`。
- 搜索结果窗口 = `_main_cols()` + 「定位到此条」；**被搜字段不在主页列时补一列，必须插在「更多」之前**，并把 `_new_table` 挂在旧末列上的 `MoreButtonDelegate` 显式摘掉（`setItemDelegateForColumn(last_col-1, None)`），否则字段列会画出「更多」按钮。
- **格式与落盘函数不因性能改动**；改前跑 `__perf_tick_bench.py`/`__perf_long_fhl_bench.py`，验 `__inplace_edit_smoke.py`。

## 主题 / i18n / 布局
- 浅深**一律原生调色板**：不建兜底色、不上全局 QSS、不用 `Fusion`；颜色走 `theme.hint_css()/warn_css()/link_color()/watch_theme()`，禁止写死；抓像素必乘 DPR。
- 原生 wins11 两坑：① 悬停 `Highlight` 整行填充 → 必须写 `::item:hover`；② 焦点行描黑框（`PE_FrameFocusRect`）→ 委托 copy option 后剥 `State_HasFocus`。
- 星历数据源窗口定稿：悬停 = `blend(Window, WindowText, 0.08)` 且文字色不动；选中 = 链接色 + 透明底（`__tle_hover_gray_smoke.py`，须 `QT_QPA_PLATFORM=windows`）。
- 文件对话框一律原生静态调用；默认桌面、文件名空（`dialog_defaults.desktop_dir()`）。
- i18n：中文是源语言，**逐段 `tr` 后再拼**；单元格固定文案用 `bind_cell_texts`；文件对话框在调用处翻；`translate()` 幂等；窗口尺寸在 `show()` 之后量；词表别加重复键。
- 设置页 = 自动保存：文本 300 ms 防抖，开关/数字立即写；`_save()` 每次重读 `file/m_xml.txt` 再 update 自己的键；坐标解析失败保留上一次有效值；「自动更新」与「检查更新」同一行、默认 True、预览版置灰。
- 所有 `.setToolTip(...)` 已整段注释 → `__sat_window_smoke` 的「提示列出数据源」必然失败。
- `show_toast()`：非模态、无边框、置顶、1 秒关、可堆叠；**分层窗口禁用 `QGraphicsDropShadowEffect`**。
- **悬浮提示一律不带感叹号、句末也不带句号**：`toast_tip.strip_bang()` 在 `_Toast.__init__` 兜底（「！」/「!」先统一成句号，再把**句末**的「。」/「.」去掉），源文案也别写；句中/文件名里的点不动。`show_toast` 是所有提示的唯一出口。
- 自定义日志字段保存后只提示「已保存字段更改」（不再报条数）。
- **删除日志无二次确认**：直接删 + toast，安全网 = `snapshot_before()`。
- **别用 `setEnabled(False)` 表示「忙」**（焦点跳到「我的呼号」并全选）；改文字 + `isRunning()` 拦重入。
- `setFixedSize` 之后**禁止**再设 `setMinimumHeight/setMaximumWidth`；超高改 `QSpacerItem(…, Expanding)`，末尾别 `addStretch`（验 `__main_layout_settle_smoke.py`）。

## 卫星 / 过境
- `satellite_pred.py`（skyfield 离线）；`MAX_PREDICT_HOURS=240`、`MAX_SELECTED_SATELLITES=250`；数据源 `file/tle_sources.txt` + 独立窗口（`#` 禁用、延迟只进 `_ROLE_DELAY`、按 NORAD 增量更新）；**卫星名匹配规则两处同步**；隐藏行必须 `setRowHidden`，超限靠 `reset_requested` + `while True` 重开。
- 过境视图 = 极坐标天空图（**素色：无阴影/光晕/渐变/圆角**），配色一律从 `QPalette` 混合；可通联只把线画粗 2.4×；**skyfield 没有 `ts.utc(jd=...)`** → `ts.from_datetime(jd_to_datetime(jd))`。
- 「双方全部过境」= `emphasis=(起,止)` + `auto_spans=True`；过境/地图窗口都是**独立顶层窗口**；**经纬度 0° 合法**。

## 多人日志 / 服务端
- **`remote_crypto.py` 是密码学唯一出处**（全帧加密、nonce 滑窗、服务端先说话）；退出必走 `RemoteConnection.shutdown()`；Qt 关窗只隐藏不触发 `destroyed`；独立服务端目录 `src/F_HamLog_Remote_Log_Server_*` 自带两份副本 → **改协议须三份同步**。
- 服务端 exe：启动即建 `keys/`、`main.fhl`、`password_xml.txt`；`_app_dir()` 不能信 `sys.executable`；带 `--windows-uac-admin`，端到端要另打去掉它的包。

## 冒烟验证
- `QT_QPA_PLATFORM=offscreen` 可真冒烟。四坑：槽里 `sys.exit()`；静态 `QFileDialog.*`/`QMessageBox.*` 自带模态循环；`os._exit()` 跳过 flush；**加密文件不给 `key` 会弹密钥框挂死**。
- 测试放 `tests/__*_smoke.py`；`set.py`/`project.py` 读设置用硬编码 `file/m_xml.txt`；**绝不能 `git checkout -- file/…`**；`project.main()` 不触碰星历。

## 检查更新（`check_update.py` 唯一出处）
- 不 import Qt：`check()` → `preview|error|latest|new`；`download()` **动态分块并行**（≥4 MB 才切、16 线程、块数 ≈ 线程×3、块 ≥512 KB、抢块、**按偏移直写 `dest.part` 无合并**、失败退单线程）；`run_installer()` `/SILENT`；界面在 `set.py`（`BgThread` + 模块级强引用）。
- **别退回「段数 = 线程数 + 末尾合并」**（快的线程闲着 + CDN 每条连接先快后限速 = 前快后慢）；重试按「有没有进展」算（`stalls` 清零 + `PART_TRIES×8` 上限）。
- 进度窗：`setValue()` 内部会 `show()`，关窗后有帧就弹回 → `state['closed']` 拦住并**先 `reset()` 再 `hide()`**；QProgressDialog 只增不减。
- **QMessageBox 无 RejectRole 时叉号和 Esc 全失效**；要自定义按钮顺序自己用 QDialog 排。
- **下载/提示窗一律不可最大化**：`_no_maximize()` = 关 `WindowMaximizeButtonHint` + `MSWindowsFixedSizeDialogHint` + `changeEvent` 里 `isMaximized() → showNormal()`（别只删 hint）；进度窗还要 `WindowMinimizeButtonHint` + `Qt.NonModal` + `parent=None`。
- 速度/ETA 必须平滑：1 s 滑动窗；ETA 累计平均 + 只降不升 + 死区随 eta 缩放；`_Meter.add()` 回调在锁内；`done` 回退当帧不重算。
- 加速：多线程 + `PART_TIMEOUT=15` + `choose_source()` 镜像择优（快 1.3 倍才换、换前验 Range），镜像走 `_spot_check()`；版本文件可写第三段 sha256。
- **预览版不自我更新**（含 `UTC`/`Preview` 连网都不连）；`preview.yml` 改版本号**必须在 `pip install -e .` 之后、Nuitka 之前**；版本串全 ASCII。
- 下载前必查本地包：`%LOCALAPPDATA%/F_HamLog/update`（`F_HAMLOG_UPDATE_DIR` 可覆盖）+ 同名 `.json`；`find_installer()` = sha256 → 元数据 → 仅 exe 名，**<1 MB 不认**；判同一个包**只认 exe 文件名**；重下必须 `force=True`；线上版本文件 `版本号 下载地址 [sha256]`，远端不比本地新就算最新。

## 打包 / 发布
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，默认 `main`；`main.yml` 手动 / `preview.yml` cron；`.github/inno/F HamLog 2.iss`；本机无 `gh`；`commit_artifacts='false'` 跳过回写。
- **版本号不再手填**（2026-11-16）：`main.yml` 正则读 `src/f_hamlog/__init__.py` 的 `__version__`（须纯数字点，预览串报错）→ 检出必须在解析之前。
- 「打包后没生效」先怀疑装到旧包：扫 exe 字节找新字符串，**别用 mtime**；锁屏下验界面 `PrintWindow(hwnd,hdc,2)` + 先 `SetProcessDpiAwarenessContext(-4)`（`tests/__pkg_ui.py`）。
- **打包必须给 `PYTHONPATH=<repo>/src`**，否则「空壳 exe」：打包成功 ≠ 产物可用。
- 产出目录靠 `--output-folder-name=main` 固定；`.iss`、`.gitignore` 全按 `main.dist` 写死；**禁止 `--include-module`**（点分名必 FATAL），`remote_crypto` 由 import 收。
- CI 的 pip 不许碰中文输出：`PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` / `PIP_PROGRESS_BAR=off`。
- `.iss` 的 `[Files]` 必须跟上数据文件名（种子 `main.fhla`，`Check: NeedSeedMainFhla`）。
- 合并 `file/`：`.tle` 取更完整一侧；`m_xml.txt` 只差 `sat_last_update` 取较新；`memory/*.md` 全保留。
