# F HamLog 项目长期记忆

> 细节档案（卫星 API、加密协议字段、服务端内幕、离屏测试 7 条坑、发布流程细节、六个呼号接入点）见同目录 `DETAILS.md`；
> 逐次改动过程见 `YYYY-MM-DD.md`。本文件只留约定、决策与踩坑要点。

## 基本约定
- PySide6 桌面应用：`main.py` → `project.py`（主日志窗）；`batch_project.py` 批量、`set.py` 设置、`export_adi/output_adi/output_excel` 导出。
- 内存日志 `file` = list[dict]：date/time/m_call/o_call/freq(上行)/freq_rx(下行)/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。**无 `record`（通联录音已删）**。主页表格 **14 列**，末列「更多」。
- 持久化 `.fhl`（utf-8 JSON，可选 AES-GCM）走 `fhl_rw.py`。
- 设置 `file/m_xml.txt` 是 `eval` 的 dict，**一律 `.get` 读**；键：m_call/m_qth/m_dig/aouto_save/aouto_list、m_lat/m_lon/m_alt、sat_auto_update/sat_update_hours(1–168)/sat_last_update、sat_b_lat/lon/alt、sat_mu_el_a/b、sat_mu_dur/filter/sats、sat_map_hours/sat_dur、sat_sats/mu_sats。**星历数据源不在其中**（见下）。
- 版本 2.4；Nuitka 打包独立 exe。
- **界面颜色一律走 `theme.py` 取色，禁止写死颜色**（深色模式下 `#444` 字/`#f3f3f3` 底会不可读）：
  `hint_css()/warn_css()/link_css()`、`hint_color()/warn_color()/link_color()`、`subtle_bg()`、
  `border_color()`、`is_dark()`；长期窗口要 `theme.watch_theme(控件, 回调)` 注册主题变化重刷。
  坑：给控件设 `background-color` 的 QSS 会**反写进该控件自己的调色板**，用它自己取色会锁死在
  首次颜色 → 取色要用未被 QSS 染色的父/兄弟控件。
- **颜色模式**（跟随系统/浅色/深色）存 `file/m_xml.txt` 的 `theme_mode` 键：`theme.init_app(app)`
  在 main.py 启动时应用；「设置」窗口下拉**即改即生效并落盘**（不必点「保存更改」）；该下拉与
  「自动保存/自动按时间排序/星历自动更新/更新间隔」**同行**（`set.py` 固定 770×475）。
  `system` = `setColorScheme(Unknown)` + `setPalette(QPalette())` 交回 Qt；`light/dark` =
  `setColorScheme` + 自建调色板（深 Window #353535 / Base #252525，浅 Window #f0f0f0）。
- 不纳入主题化（勿误改）：`#remote_project.py`（历史备份、无引用）、
  `F_HamLog_Remote_Log_Server_2.0.0/main.py`（独立服务端，改后须重打包）；地图画布绘制色
  （satellite_map_window 的 QColor/QPen/QBrush 常量）是地图语义色，深色下地图仍浅色是刻意的。
- **本机 shell 部分可用**（PortableGit shim 缺 dirname/cat）：`ls/head/tail/wc/rm/git` 实测可用
  （2026-09-26）；文件读写仍优先 Glob/Grep/Read/Edit；命令输出写文件再 Read。项目 venv
  `D:\F-Dev\BIG\F_HamLog\.venv\Scripts\python.exe`（worktree 在 C 盘、venv 在 D 盘，直接用绝对路径即可）。

## 卫星功能
- `satellite_pred.py`（skyfield+numpy 离线）。`parse_tle_text` 的名字已 `.strip()`，与 satrec/表格按名匹配才不错位。
- 打包必带 `--include-package-data=skyfield` + `--include-data-dir=file=file`；数据路径走 `satellite_pred.app_path()`。
- 上限：预测 `MAX_PREDICT_HOURS=240`/`clamp_predict_hours()`；自选 `MAX_SELECTED_SATELLITES=250`+`clamp_selected_count()`（裁剪取排序后前 N）。
- **星历数据源 = 独立窗口 + 独立文件**：`file/tle_sources.txt`（每行一地址、`#` 注释），窗口 `tle_source_window.py`（**双击就地编辑**、非法/重复回滚、增删/上移下移/恢复默认、**改动即时落盘**）；入口是 `set.py` 一行按钮「设置星历数据源」（`set.tle_source_win` 非模态单例复用）。`load_tle_sources()` 顺序 = 独立文件 → 旧键 `sat_tle_sources`（写在 m_xml，仅兼容读）→ `DEFAULT_TLE_SOURCES`；`save_tle_sources()` 顺手 `drop_legacy_tle_sources()` 清旧键（单一事实来源）。冲突（同 NORAD 编号）取靠前源；**只有内置 Celestrak 源带「分类组回退」**（`_fetch_celestrak_source`）。
- **下载/导入一律「按 NORAD 编号增量更新」**（`merge_update_satellites`）：同编号替换、新编号追加、**旧的一律保留（绝不删除）**；`fetch_amateur_tle` 写缓存前再与旧缓存 `merge_tle_texts(新, 旧)`。「导入星历」写回缓存且**不自动勾选**。代价：缓存只增不减。
- `norad_key()` 去前导 0 统一编号（`1 00694U` 与空格补位视为同一颗）；`iter_tle_records()` 统一解析 3LE/2LE。
- **`Satrec` 包装必须自己存 `line1/line2`**：skyfield 的 `EarthSatellite` 不保留原始 TLE 行；`satellites_to_tle_text()` 依赖它。
- 时间精度：显示到秒（`_utc_to_local_str`），记录到分（`_log_date_str`/`_log_time_str`），共用 `_local_fmt()`。
- 入口：project「卫星→通联预测」(Ctrl+Shift+E)；main「卫星过境」「通联预测」。最佳时刻 = min(仰角A, 仰角B) 最大处。
- 地图：来源工具栏打开，与来源**单向同步**（`set_sats`/`set_satellite`/`set_stations`/`set_min_elev`），来源持 `win._map_window` 已开则 `raise_()`；多星同显（默认上限 30）、`sat_map_hours`(1~24 默认 3) 与 `sat_dur`(1~240h) 独立落盘并广播；铺满且 2:1（`_map_rect()` + `MapWindow.showEvent()` 按画布宽/2 锁高）。聚焦三入口：来源列表点行 / 地图「显示」下拉 / 画布点卫星。

## 卫星名匹配与选择对话框
- `normalize_sat_name`/`sat_name_match`/`parse_sat_keywords`：用于 ① 选择框搜索过滤 ② `lookup_transponder` 第 6 层兜底；改匹配规则两处须同步。
- **隐藏行必须 `QListWidget.setRowHidden(row,hide)`**（`QListWidgetItem.setHidden()` 只改标志、不触发重排）。
- 未搜索时已选置顶（`_reordering` 守卫防递归）；计数标签**必须由 `self._count_base` 缓存重建**（读 `count_label.text()` 当基数会累加）。
- 超限提示统一走 `satellite_window.prompt_over_limit_selection(...)`（重新选择 / 清除所有选择 / 取消，**不含"一键"**）；`accept()` 超限不关闭 → `reset_requested=True`+`reject()`，调用方 `while True:` 关窗重开。兜底三处：对话框 accept、两处 `open_select`、加载设置后立即裁剪。测试 `test_max_selected_smoke.py`。

## 呼号统一大写（call_upper.py）
- `UpperCallDelegate` + `connect_callsign_upper(edit, field_getter)`（仅 m_call/o_call；恒定字段用 `lambda: 'm_call'`）；六个接入点见 `DETAILS.md`。
- 挂完 `setItemDelegateForRow` 必须 `table._upper_call_delegate = delegate` 保引用，否则 delegate 被回收导致编辑异常。

## 通联录音：已移除（勿照旧版记忆实现）
- 当前分支无该功能（`qso_rec.py` 不存在）。历史：`f84864f` 加入、`b6a9162` 删除；重建从 `f84864f` 取回再适配。

## 多人日志：加密与密钥
- 需求：密码只做身份验证；密钥程序自主生成、非对称分发后再对称加密内容；**全帧加密**；首次连接核对指纹。协议字段/握手见 `DETAILS.md`。
- **`remote_crypto.py`（纯 `cryptography`）是密码学唯一出处**。
- **密钥根 `_data_dir(fhl_path, key_dir)`**：显式 `key_dir` > `fhl_path` 目录 > cwd；内嵌服务端 `key_dir='file'`→`file/keys/`，独立服务端 `_app_dir()`→程序目录 `keys/`。**同端口不同来源也是两把密钥**（指纹不同、信任库分开记）；**换端口即换身份**。
- 重放防护用 **nonce 滑动窗口**（`NONCE_MEMORY=4096`），**不要用序号计数器做 AAD**（`PEERS`/`SYNC` 广播会让客户端合法跳帧 → 后续全 `InvalidTag`）；必须支持乱序解密。
- **服务端必须先说话**（先发 HELLO 再读），否则两端互等到 2 秒空闲超时；握手失败回退旧明文 `AUTH`（旧客户端仍能连）。`LogServer(encrypt=False)` 时 `fingerprint_short` 是 `''`（空串非 None），不发 HELLO。
- **`.gitignore` 必须忽略**：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、`F_HamLog_Remote_Log_Server_2.0.0/{keys/,main.fhl,password_xml.txt}`、`file/_key_backup_*/`。

## 多人日志：架构与生命周期
- **功能只写一次**：引擎 `remote_server.LogServer`（纯标准库）；客户端 `RemoteConnection`/`_SyncThread` 在 project.py；独立服务端目录**自带两份副本——改协议/密码学须三份同步**（根 + 该目录 + 打包脚本）。
- **退出必走 `RemoteConnection.shutdown()`，顺序不可换**：① `sync.stop()` → ② `_close_socket()`（QUIT + shutdown/close）→ ③ `sync.wait(3000)`；先关 socket 有竞态、误报「连接断开」。`_SyncThread.run()` emit 断开前必须判 `self._running`。
- **Qt 关窗只隐藏、不触发 `destroyed`**：与窗口同生命周期的资源（连接/内嵌服务端/线程）必须在 `backup.install_close_guard` 的 `on_close` 里释放（「取消」分支不调用）；`destroyed` 仅兜底，回调里**禁止界面操作**（`_detach_remote(restore_ui=False)`）。判活用 `_qt_alive()`（`shiboken6.isValid`）。
- **表格刷新**：`table_update(delete=True, persist=True)`；远程同步用 `persist=False`——先 `removeWidget+deleteLater` 再重建，但不做 `list_time/save`。
- **文案**：在线人数一律「在线用户」；「服务端信息」属「服务端」分组；客户端管理窗只读无退出按钮；服务端**启动后禁用密码输入**（含「显示/隐藏」），停止后恢复。
- **服务端发送按客户端加锁**（`entry['_lock']` + `_send_entry`）：应答线程与广播线程可能同时写同一 socket。
- **默认端口 8000**（`project.DEFAULT_ROOM_PORT`），被占则回退 `port=0`。**Windows 端口占用探测**：bind 探测——① 探测 socket **绝不能设 `SO_REUSEADDR`**（否则恒判空闲）；② 必须试探与 holder **完全相同**的地址（本项目一律绑 `0.0.0.0`）；③ **不要用 `connect_ex`**（空闲端口返回 10035，与占用无法区分）。
- 空闲判定 2 秒（有数据即重置，大日志停顿不误杀）；连接 socket 保持阻塞，**不要** settimeout（影响广播线程 send）。心跳见 `DETAILS.md`。
- **`main.py` 只保留一个 `project_window` 引用**：新建窗口会回收旧窗口 → 旧房间静默死掉；已加 `_confirm_replace_session()`，**改动窗口管理必须保留**。
- **「未保存更改」双基线**（多人日志下服务端=已保存）与关闭守卫文案见 `DETAILS.md`。
- **本机数据文件不是测试 playground**：`file/project_backup.fhl` 是用户真实数据；任何会跑 `project.main` 的测试必须先备份字节、finally 还原。

## 独立服务端（F_HamLog_Remote_Log_Server_2.0.0）
- 启动即自动创建 `keys/`、`main.fhl`、`password_xml.txt`；分发只需一个 exe；`_app_dir()` 不能信 `sys.executable`/`__file__`（onefile 下指向 `%TEMP%`），必须自己 `import remote_crypto` —— 细节见 `DETAILS.md`。
- 该 exe 带 `--windows-uac-admin`（非提权启动 `WinError 740`）：端到端验证要另打**去掉 uac-admin** 的临时包（不覆盖 `dist/`）。它是 git 跟踪文件，重打后需提交。

## 验证环境（离屏 GUI 冒烟）
- venv 可 `QT_QPA_PLATFORM=offscreen` 真实冒烟；`project.main/satellite_window/mutual_window/batch_project`、独立服务端 `main.py` 均可离屏（做法与「嵌套模态消息框」7 条坑见 `DETAILS.md`）。
- **坑**：槽里的 `sys.exit()`（如 esave）会从 PySide6 的 C++ 边界直接终止进程（`except SystemExit`/`finally` 都拦不到）→ 测试前临时 `sys.exit = lambda *a, **k: None`；被管道捕获时缓冲区里的输出也会一起丢。
- 测完核对并还原 `file/m_xml.txt`（及 `file/amateur.tle`、`file/sat_map_markers.txt`、`file/tle_sources.txt`）；`m_lat/m_lon=0,0` 时卫星窗口会先弹「设置观测站」抢在待测提示前。
- 约定：冒烟脚本命名 `__*_smoke.py`，结果写 `__*_out.txt`（已被 `.gitignore` 覆盖）。**优先把路径常量 monkeypatch 到临时文件**（`sp.TLE_SOURCES_PATH`/`sp.SETTINGS_PATH`/`smw.MARKERS_PATH`），比「备份—还原字节」更干净。
- **离屏跑卫星窗口**：必须 patch `ObserverDialog.exec`/`SatelliteSelectDialog.exec` 返回 `Rejected`，再 patch `QMessageBox.information/warning` 抓文案、`QFileDialog.getOpenFileName` 喂文件；`win.findChildren(QPushButton)` 按文字点按钮。样例 `__sat_window_smoke.py`/`__tle_source_smoke.py`/`__tle_source_win_smoke.py`。
- `mutual_window` 的 `win` 是 `main()` 里的局部 `QMainWindow()`：离屏拿控件需临时替换模块的 `QMainWindow` 为注册实例的子类（否则返回即被回收）。

## 发布流程（GitHub Actions 全自动）
- 主分支 `develop`，`.github/workflows/main.yml` 手动 `workflow_dispatch` 一次跑完打包→安装包→兼容版 zip→发 Releases。**只填 `version`**，命名自动推导（`F HamLog 2.4 setup.exe` / `F.HamLog.2.4.zip` …）。
- **Release 说明留空、由作者手填**：`gh release create <tag>` **不传** `--title/--notes/--generate-notes`；已存在只 `gh release upload --clobber`，**不 edit**（幂等可重跑）。
- **改脚本必记的 7 条坑**、缓存策略、本地验证方法与 `.iss` 约定见 `DETAILS.md`。
