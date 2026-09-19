# F HamLog 项目长期记忆

> 详细描述性内容（卫星 API、加密协议字段、服务端内幕、离屏测试步骤、六个呼号接入点）见同目录 `DETAILS.md`；
> 逐次改动过程见 `YYYY-MM-DD.md` 日志。本文件只留约定、决策与踩坑要点。

## 基本约定
- PySide6 桌面应用：`main.py` → `project.py`（主日志窗）；`batch_project.py` 批量、`set.py` 设置、`export_adi/output_adi/output_excel` 导出。
- 内存日志 `file` = list[dict]：date/time/m_call/o_call/freq(上行)/freq_rx(下行)/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。**无 `record`（通联录音已删）**。主页表格 **14 列**，末列「更多」。
- 持久化 `.fhl`（utf-8 JSON，可选 AES-GCM）走 `fhl_rw.py`。
- 设置 `file/m_xml.txt`：`eval` 的 dict。键含 m_call/m_qth/m_dig/aouto_save/aouto_list、卫星 m_lat/m_lon/m_alt、sat_auto_update/sat_update_hours(1–168)/sat_last_update、sat_b_lat/lon/alt、sat_mu_el_a/b、sat_mu_dur/filter/sats、sat_map_hours/sat_dur、sat_sats/mu_sats。**一律 `.get` 读**。
- 版本 2.4；Nuitka 打包独立 exe。
- **本机 shell 不可用**（PortableGit shim 缺 dirname/cat/head/grep）：用 Glob/Grep/Read/Edit，或项目 venv `D:\F-Dev\BIG\F_HamLog\.venv\Scripts\python.exe`（含 PySide6/cryptography/skyfield/numpy）；命令输出写文件再 Read。

## 卫星功能
- `satellite_pred.py`（skyfield+numpy 离线）。`parse_tle_text` 返回的名字已 `.strip()`，与 satrec/表格按名匹配才不错位。
- 打包必带 `--include-package-data=skyfield` + `--include-data-dir=file=file`；数据路径走 `satellite_pred.app_path()`。
- 上限：预测 `MAX_PREDICT_HOURS=240`/`MIN_PREDICT_HOURS=1`/`clamp_predict_hours()`（算法+spinbox+设置三处兜底）；自选 `MAX_SELECTED_SATELLITES=500`+`clamp_selected_count()`（裁剪取排序后前 N，保证可复现）。
- 时间精度：**显示到秒**（`_utc_to_local_str`），**记录到分**（`_log_date_str`/`_log_time_str`，与日志表/ADIF 一致），共用 `_local_fmt()`。
- 入口：project「卫星→通联预测」(Ctrl+Shift+E)；main「卫星过境」「通联预测」。最佳时刻 = min(仰角A, 仰角B) 最大处。
- 地图窗由来源工具栏打开，与来源**单向同步**（范围/TLE→`set_sats`、选行→`set_satellite`、台站→`set_stations`、仰角→`set_min_elev`）；来源持 `win._map_window`，已开则 `raise_()` 复用，关图反向清理。
- 地图约定：多星同显（默认上限 30/1–200），聚焦星加粗+覆盖区+图例；`sat_map_hours`(1~24 默认 3) 与 `sat_dur`(1~240h) 独立落盘并跨来源广播；可见段实线加粗、对方可见段虚线加粗；覆盖区=0° 仰角圈。
- **聚焦三入口**：来源列表点行（自动开图）/ 地图「显示」下拉 / 画布点卫星。列表用 `itemSelectionChanged`+`cellClicked`（跳过「记录」列）双信号，关图后点同/异行均可重开。
- 两来源窗口宽度一致：`__init__` 临时显示「对方最低仰角」组测一次统一最小宽（均 1192）。
- 地图铺满且保持 2:1：`_map_rect()` 返回整块画布；`MapWindow.showEvent()` 首次显示按「画布宽/2」锁高（1192→675）并 `setMinimumHeight`。

## 卫星名匹配与选择对话框
- `normalize_sat_name`（只留字母数字并大写）/`sat_name_match`（多关键词 AND）/`parse_sat_keywords`：用于 ① 选择框搜索过滤 ② `lookup_transponder` 第 6 层兜底；改匹配规则两处须同步。
- **隐藏行必须 `QListWidget.setRowHidden(row,hide)`**（`QListWidgetItem.setHidden()` 只改标志、不触发重排）。
- 未搜索时已选置顶（`_reordering` 守卫防递归）；计数标签**必须由 `self._count_base` 缓存重建**（读 `count_label.text()` 当基数会累加）。
- 超限提示统一走 `satellite_window.prompt_over_limit_selection(parent,n,limit,source_hint='')`（按钮：重新选择 / 清除所有选择 / 取消，**不含"一键"**）；`accept()` 超限不关闭 → 置 `reset_requested=True`+`reject()`，调用方 `while True:` 关窗重开。兜底三处：对话框 accept、两处 `open_select`、加载设置后立即裁剪。测试 `test_max_selected_smoke.py`。

## 呼号统一大写（call_upper.py）
- `UpperCallDelegate`（表格呼号单元格实时大写）+ `connect_callsign_upper(edit, field_getter)`（仅 m_call/o_call；恒定字段用 `lambda: 'm_call'`）。
- 挂完 `setItemDelegateForRow` 必须 `table._upper_call_delegate = delegate` 保引用，否则 delegate 被回收导致编辑异常。

## 通联录音：已移除（勿照旧版记忆实现）
- 当前分支无该功能（`qso_rec.py` 不存在，表格无该列）。历史：`f84864f` 加入，`b6a9162` 删除；若重建从 `f84864f` 取回再适配当时列数/字段集。

## 多人日志：加密与密钥
- 需求：密码只负责身份验证；密钥程序自主生成、非对称分发后再对称加密内容；全帧加密；首次连接核对指纹。
- **`remote_crypto.py`（纯 `cryptography`）是所有密码学逻辑的唯一出处**；协议字段/握手流程见 `DETAILS.md`。
- **密钥根由 `_data_dir(fhl_path, key_dir)` 决定**：显式 `key_dir` > `fhl_path` 所在目录 > cwd。内嵌服务端 `key_dir='file'`→`file/keys/`；独立服务端 `key_dir=_app_dir()`→程序目录 `keys/`。**两者即便端口相同也是两把不同密钥**（指纹不同，信任库须分别记录）；**换端口即换身份**。
- 重放防护用 **nonce 滑动窗口**（`SessionCipher.NONCE_MEMORY=4096`），**不要用序号计数器做 AAD** —— 服务端穿插 `PEERS`/`SYNC` 广播会让客户端合法跳帧、后续全部 `InvalidTag`。乱序解密必须支持。
- **服务端必须先说话**：加密开启时先发 HELLO 再读，否则两端互等到 2 秒空闲超时。握手失败回退旧明文 `AUTH` 路径（旧客户端仍能连）。
- `LogServer(..., encrypt=False)` 显式关加密供排障/测试；此时 `fingerprint_short` 为 `''`（空字符串，非 None），不发 HELLO。
- 打包：`remote_crypto` 由 `--include-module=remote_crypto` 加入 `打包.txt` 与 `F_HamLog_Remote_Log_Server_2.0.0/打包-服务端.txt`。旧明文烟测一律加 `encrypt=False`。
- **`.gitignore` 必须忽略**（私钥/信任库绝不能入库）：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、`F_HamLog_Remote_Log_Server_2.0.0/keys/`、`F_HamLog_Remote_Log_Server_2.0.0/main.fhl`、`F_HamLog_Remote_Log_Server_2.0.0/password_xml.txt`、`file/_key_backup_*/`。

## 多人日志：架构与生命周期
- **功能只写一次**：引擎 `remote_server.LogServer`（纯标准库）；客户端 `RemoteConnection`/`_SyncThread` 在 project.py。独立 GUI 服务端在 `F_HamLog_Remote_Log_Server_2.0.0/`，**自带 `remote_server.py`/`remote_crypto.py` 副本 —— 改协议/密码学须三份同步**（根 + 该目录 + 打包脚本）。
- **退出必须走 `RemoteConnection.shutdown()`，顺序不可换**：① `sync.stop()` 置位 → ② `_close_socket()`（QUIT + shutdown/close）→ ③ `sync.wait(3000)`。先关 socket 会有竞态、误报「连接断开」。`_SyncThread.run()` emit 断开信号前必须判 `if self._running`。
- **Qt 关窗默认只隐藏、不触发 `destroyed`**：与窗口同生命周期的后台资源（连接/内嵌服务端/线程）必须在 `backup.install_close_guard` 的 `on_close` 回调里释放（「取消」分支不调用）；`destroyed` 仅兜底，且回调里**禁止任何界面操作**——`_detach_remote(restore_ui=False)` 即为此。判活用模块级 `_qt_alive()`（`shiboken6.isValid`）。
- **表格刷新**：`table_update(delete=True, persist=True)`；远程同步用 `table_update(persist=False)`——必须先 `removeWidget+deleteLater` 再重建（否则两个表格残留），但不做 `list_time/save`。
- **文案**：在线人数一律「在线用户」；「服务端信息」（局域网地址/端口/密码+复制）属「服务端」分组内；客户端管理窗只读、无退出按钮；服务端（内嵌与独立）**启动后禁用密码输入**（含「显示/隐藏」），停止后恢复。
- **服务端发送必须按客户端加锁**：`entry['_lock']` + `_send_entry(entry,type,payload)`，回包与 `_broadcast`/`_notify_peers` 都走它（应答线程与广播线程可能同时写同一 socket）。
- **默认端口 8000**：`project.DEFAULT_ROOM_PORT = 8000`（与「加入多人日志」对话框默认值一致）；被占（`port_status=='occupied'`）则回退 `port=0` 自动分配。
- **Windows 端口占用探测**：`remote_server.is_port_in_use()`/`_can_bind()` 用 bind 探测 —— ① 探测 socket **绝不能设 `SO_REUSEADDR`**（否则恒判空闲）；② 必须试探**与 holder 完全相同**的地址（绑定语义不对称；本项目服务端一律绑 `0.0.0.0`，故以 `0.0.0.0` 为口径）；③ **不要用 `connect_ex`**（对空闲端口返回 `WSAEWOULDBLOCK(10035)`，与占用无法区分）。
- 空闲判定 2 秒（有数据即重置计时，大日志传输停顿不会误杀）；连接 socket 保持阻塞，**不要**再 settimeout（会影响广播线程 send）。心跳见 `DETAILS.md`。
- **`main.py` 只保留一个 `project_window` 引用**：新建窗口会回收旧窗口 → 旧窗口若开着房间会静默死掉；已加 `_confirm_replace_session()` 先确认，**改动窗口管理必须保留**。
- **「未保存更改」双基线**（多人日志下「服务端=已保存」）：`_bk_snapshot()` 只有非多人日志才更新 `local`；退出会话时 `last = snap if snap == local else ''`（`''` 为恒脏哨兵）；关闭守卫文案由可选 `texts()` 定制。详见 `DETAILS.md`。
- **本机数据文件不是测试 playground**：`file/project_backup.fhl` 是用户真实数据（可能含未保存内容）。任何会跑 `project.main` 的测试必须先备份该文件字节、finally 还原。

## 独立服务端（F_HamLog_Remote_Log_Server_2.0.0）
- 启动即**自动创建所需文件与目录**：`keys/`（含当前端口长期密钥 `server_<端口>.fhlkey`）、`main.fhl`（空日志 `[]`）、`password_xml.txt`（默认 `000000`）；`_ensure_runtime_files()` 返回失败项文字，由 `__init__` 写进事件日志（只读目录下也不影响开窗）。分发时只需一个 exe。
- `_app_dir()` **不能信 `sys.executable`/`__file__`**：Nuitka onefile 下两者都指向 `%TEMP%\onefile_<PID>_…`（退出即清理），`sys.frozen` 不存在（只有 `'__compiled__' in globals()` 为 True）。正确顺序：① `os.environ['NUITKA_ONEFILE_DIRECTORY']`（引导程序给的 exe 目录）→ ② `sys.argv[0]` 再 `sys.executable` 的目录 → ③ `__file__` 目录。启动时会在事件日志打印「数据目录：…」。**注意 `main.py` 必须自己 `import remote_crypto`**（曾漏，密钥创建被静默跳过）。
- 该 exe 带 `--windows-uac-admin`：非提权进程直接启动会 `WinError 740`；要端到端验证就另打一个**去掉 uac-admin** 的临时测试包（不覆盖 `dist/` 正式产物）。该 exe 是 git 跟踪文件，发布工作流默认路径就是 `F_HamLog_Remote_Log_Server_2.0.0/dist/F_HamLog_Remote_Log_Server_2.0.0.exe`，重打后需提交。
- 客户端「多人日志管理」窗为可最小化的非模态 `QDialog`（`project.open_multiplayer_manager`，当前 640×640），单例复用（`window._mp_dialog`）。

## 验证环境（离屏 GUI 冒烟）
- 项目 venv 可 `QT_QPA_PLATFORM=offscreen` 真实冒烟（建窗/后台线程/读表/点按钮）。
- **`project.py` 主窗口可以 offscreen 离屏**（旧记录的“硬崩溃”不成立）：`project.main(QMainWindow(), 数据, 路径, key_=…, recovered=…)` 同步跑完建表/自动保存/关闭守卫，实测 exit 0；配 patch `QMessageBox.exec/clickedButton`（模拟点按钮）、`QMessageBox.information/warning`、`QFileDialog.getSaveFileName`、`fhl_rw.write_fhl_file`（统计落盘）即可端到端测保存与关闭流程（样例 `test_recover_save_smoke.py`）。槽里的 `sys.exit()`（如 esave）会从 PySide6 的 C++ 边界直接终止进程（finally 都不跑）→ 测试前临时 `sys.exit = lambda *a, **k: None`。`main/satellite_window/mutual_window/batch_project`、独立服务端 `main.py` 亦可离屏。
- 测完核对并还原 `file/m_xml.txt`；`m_lat/m_lon=0,0` 时卫星窗口会先弹「设置观测站」抢在待测提示前。
- 离屏「嵌套模态消息框」与「两进程真机回归」（`__mp_host.py`/`__mp_guest.py`）的步骤与 7 条踩坑见 `DETAILS.md`。
- 约定：新增冒烟脚本命名 `__*_smoke.py`，结果写 `__*_out.txt`（两者已被 `.gitignore` 的 `__*_out.txt` 覆盖）。

## 发布流程（GitHub Actions 全自动）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，主分支 `develop`。`.github/workflows/main.yml` 手动 `workflow_dispatch`，一次跑完：Nuitka 打包 → Inno Setup 6 安装包 → 兼容版压缩包 → 发 Releases。
- **只填 `version`（如 2.4.0）**；命名由 version 推导（先 `-replace '\.0$',''` 得 display：2.4）：安装包 `F HamLog 2.4 setup.exe`、兼容版 `F HamLog 2.4兼容版.zip`、Release 附件沿用点号风格 `F.HamLog.2.4.setup.exe` / `F.HamLog.2.4.zip`，外加仓库内已打包的 `F_HamLog_Remote_Log_Server_2.0.0.exe`（不重打包）。安装包内部 AppVersion 仍用完整版本。
- **Release 说明留空、由作者手填**：`gh release create <tag>` **不传** `--title`/`--notes`/`--generate-notes`；已存在时只 `gh release upload --clobber`，**不 edit**（幂等可重跑）。
- `.github/inno/F HamLog 2.iss` 为 CI 专用（AppId 与本地一致故升级关系不变；路径走 `RepoRoot`，版本/包名/ExeName 由 `/D` 注入）；`.github/inno/ChineseSimplified.isl` 内置中文语言文件（运行器 Inno 6.7.1 不带非官方中文包），`.gitattributes` 锁 CRLF。
- 缓存：pip、Nuitka 辅助工具、`.venv`（按 `第三方模块.txt` 哈希）、`main.build`（按 `*.py` 哈希）。
- **改脚本必记的坑**：① PowerShell 里紧跟中文的变量必须写 `${var}`（`"$display兼容版"` 会被当成一个变量名，值静默变空）；② `VersionInfo.ProductVersion` 由系统补尾部空格，比较前必须 `.Trim()`；③ `GITHUB_ENV`/摘要用 `[System.IO.File]::AppendAllLines`+`UTF8Encoding($false)`（统一 `shell: pwsh`）；④ 多行文本数组不要 `[string[]]` 强转（会被拼成一行），用 `List[string]` 逐行 `Add`；⑤ 7-Zip 打包 `Push-Location main.dist; 7z a -tzip <dst> *`；⑥ `nuitka.__version__` 在 4.x 已移除，用 `importlib.metadata.version('nuitka')`；⑦ `run:` 双引号串里别写 `${{ }}`，用 `$env:GITHUB_REPOSITORY`/`$env:GITHUB_SHA`。
- 本地验证：PyYAML 解析工作流 → 抽 `run` → `[Parser]::ParseFile` 查语法（**目标路径必须内联进命令串**：`ParseFile('')` 恒「无错误」→ 假通过）；再用桩 `gh.cmd` 前置 `PATH` 演练各步。本机已装 Inno 6.7.3 与 7-Zip。
