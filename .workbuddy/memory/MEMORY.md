# F HamLog 项目长期记忆

> 可复现的描述性细节（卫星 API、加密协议字段、服务端实现内幕等）已分流到同目录 `DETAILS.md`；
> 本文件只保留约定、决策与踩坑要点。

## 基本约定
- PySide6 桌面应用。`main.py` → `project.py`（主日志窗）；`batch_project.py` 批量、`set.py` 设置、`export_adi/output_adi/output_excel` 导出。
- 日志：内存 `file` 为 list[dict]，字段 date/time/m_call/o_call/freq(上行)/freq_rx(下行)/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。**`record`（通联录音）已移除**。
- 持久化 `.fhl`（utf-8 JSON，可选 AES-GCM），走 `fhl_rw.py`。
- 设置 `file/m_xml.txt`：Python `eval` 的 dict。键：m_call/m_qth/m_dig/aouto_save/aouto_list、卫星 m_lat/m_lon/m_alt、星历 sat_auto_update(bool)/sat_update_hours(1–168)/sat_last_update(epoch)、通联预测 sat_b_lat/lon/alt、sat_mu_el_a/b、sat_mu_dur、sat_mu_filter、sat_mu_sats、地图 sat_map_hours/sat_dur、自选 sat_sats/mu_sats。**一律 `.get` 读**。
- 版本 2.4（`F HamLog 2 Inno Setup\F HamLog 2.iss` 内 MyAppVersion=2.4.0），Releases 最新 2.3.0。Nuitka 打包独立 exe。
- **本机 shell 基本不可用**：PortableGit shim 缺 dirname/cat/head/tail/grep/sleep。一律用 Glob/Grep/Read/Edit，或 `C:/Users/13577/.workbuddy/binaries/python/envs/default/Scripts/python.exe`；输出重定向到文件再 Read（PowerShell 标准输出常不回传）。`__mp_*.py` 的 exit=127/3221226505 多为环境产物，以成功哨兵为准。

## 卫星功能
- `satellite_pred.py`（skyfield+numpy，离线）→ 详 `DETAILS.md`。**`parse_tle_text` 返回的名字已 `.strip()`**，与 `satrec.name`/表格 `r['name']` 一致，按名匹配（地图聚焦/TQSL/转发器）才不会错位。
- 打包必带 `--include-package-data=skyfield`（缺 .npz 资源双击即崩）+ `--include-data-dir=file=file`；数据路径一律走 `satellite_pred.app_path(rel)`（优先含 `file/` 子目录的目录，避免从非 exe 目录启动找不到数据）。
- 上限：`MAX_PREDICT_HOURS=240`/`MIN_PREDICT_HOURS=1`/`clamp_predict_hours()`，算法层+spinbox+设置读写三处兜底，越界值打开即收敛。
- 时间精度：**显示到秒**（`_utc_to_local_str`=`%m-%d %H:%M:%S`，用于升起/落下、可通联开始/结束/最佳时刻）；**记录到分**（`_log_date_str`/`_log_time_str`=`%Y-%m-%d`/`%H:%M`，与日志表 time、ADIF 精度一致）。两者共用 `_local_fmt(dt, tz, fmt)`。
- 入口：`project.py`「卫星」菜单、「卫星→通联预测」(Ctrl+Shift+E)；`main.py`「卫星过境」「通联预测」。通联预测「最佳时刻」= `min(仰角A, 仰角B)` 最大处。
- 地图窗口由来源工具栏「地图」打开，与来源**单向同步**（范围/TLE→`set_sats`；选行→`set_satellite`；台站→`set_stations`；仰角→`set_min_elev`）；来源持 `win._map_window`，关图反向清理，已开窗口 `raise_()` 复用。
- 地图约定：多星同显（「全部已选卫星(N)」或单颗；聚焦星加粗+覆盖区+图例●，显示上限默认 30/1–200）；`sat_map_hours`(1~24,默认3) 与 `sat_dur`(1~240h) 独立落盘并跨来源广播一致；可见段=本台仰角≥最低→实线加粗、有对方台时对方可见段虚线加粗；覆盖区=0°仰角地心半角圈，>5 颗只画聚焦星。
- **聚焦三入口**：① 来源列表点行（自动开图/聚焦）；② 地图「显示」下拉；③ 画布点卫星（圆点/轨迹/覆盖区，悬停手型）。列表用 `itemSelectionChanged`+`cellClicked`（跳过「记录」列）双信号，关图后点同/异行均可重开。
- **窗口宽度一致**：「对方最低仰角」组仅通联预测有 station_b 时可见，`setVisible(False)` 不计入布局最小宽→两来源 resize 结果不同。`__init__` 临时显示该组测一次统一最小宽后恢复（两处均 1192）。
- **地图铺满且保持 2:1**：`_map_rect()` 直接返回整块画布；`MapWindow.showEvent()` 首次显示按「画布宽/2」锁窗口高（1192→675，画布 1174×587 精确 2:1），并 `setMinimumHeight` 防缩小变形。

## 卫星名匹配（归一化，全局统一）
- 工具 `normalize_sat_name`（只留字母数字并大写，抹平大小写/空格/短横线/括号）、`sat_name_match(name,keys)`（多关键词 AND）、`parse_sat_keywords(text)`。用于 ① `SatelliteSelectDialog` 搜索过滤 ② `lookup_transponder` 第 6 层兜底（表中 `AO-91` 可匹配 TLE 名 `AO 91`）。改匹配规则两处须同步。
- **隐藏行必须 `QListWidget.setRowHidden(row,hide)`**，不能用 `QListWidgetItem.setHidden()`（只改标志、不保证触发 `doItemsLayout()` 重排）。
- 未搜索时已选置顶（勾选一变即物理重排到顶部，`_reordering` 守卫防递归）；计数标签**必须由 `self._count_base` 缓存重建**，别读 `count_label.text()` 当基数（会累加）。
- 上限 `MAX_SELECTED_SATELLITES=500` + `clamp_selected_count(n)`（裁剪取**排序后前 N 个**，保证可复现）。
- 超限提示统一走 `satellite_window.prompt_over_limit_selection(parent,n,limit,source_hint='')`（按钮：**重新选择** / **清除所有选择** / 取消，**不含"一键"**；改文案只改这处）；`accept()` 超限不关闭 → 置 `reset_requested=True`+`reject()`，调用方 `while True:` 循环「关窗重开」。兜底三处：对话框 accept、两处 `open_select`、加载设置后立即裁剪。测试 `test_max_selected_smoke.py`。详细机制（takeItem O(1)、`_row_names`、m_xml 超限三分支）见 `DETAILS.md`。

## 呼号统一大写（call_upper.py）
- `UpperCallDelegate`（QTableWidget 呼号单元格实时大写）+ `connect_callsign_upper(edit, field_getter)`（QLineEdit，仅字段为 m_call/o_call 时；恒定字段用 `lambda: 'm_call'`）。六个接入点见 `DETAILS.md`。
- 挂完 `setItemDelegateForRow` 必须 `table._upper_call_delegate = delegate` 保留引用，否则 Python 端 delegate 被回收导致编辑异常。

## 通联录音：已移除（勿照旧版记忆实现）
- 当前分支**无**该功能：`qso_rec.py` 不存在，表格无该列（主页表格 **14 列**，末列「更多」）。
- 历史：`f84864f` 加入，`b6a9162`「优化批量记录」删除（`project.py` 61197→56663 字节），后续多人日志提交未恢复。用户明确要求删除全部相关内容。将来若重建，从 `f84864f` 取回再适配当时列数/字段集。

## 多人日志加密（X25519 + AES-256-GCM）
- 需求：密码只负责身份验证；密钥程序自主生成，非对称加密分发后再用其对称加密日志内容；全帧加密；首次连接核对指纹。
- **`remote_crypto.py`（纯 `cryptography`，无 GUI 依赖）是所有密码学逻辑的唯一出处**；协议字段/握手流程见 `DETAILS.md`。
- **密钥根由 `_data_dir(fhl_path, key_dir)` 决定**（显式 `key_dir` > `fhl_path` 所在目录 > cwd），`LogServer(..., key_dir=...)` 是唯一入口：内嵌服务端 `key_dir='file'`→`file/keys/`；独立服务端 `key_dir=_app_dir()`→程序目录 `keys/`。**两者即便端口相同也是两把不同密钥**（指纹不同，信任库须分别记录），不可混用。**换端口即换身份**。
- **重放防护用 nonce 滑动窗口**（`SessionCipher.NONCE_MEMORY=4096`：set+deque），**不要用序号计数器做 AAD** —— 服务端会穿插 `PEERS`/`SYNC` 广播，客户端合法跳过帧会导致计数器错位、后续全部 `InvalidTag`（踩过的坑）。乱序解密是必须支持的。
- **服务端必须先说话**（`remote_server._handle`）：加密开启时立刻发 HELLO 再读，否则两端互等直到 2 秒空闲超时（踩过的坑）。握手失败回退旧明文 `AUTH` 路径（`entry['_legacy_frame']` → `_auth_plain`），**旧客户端仍能连**。
- `LogServer(..., encrypt=False)` 显式关加密供排障/测试；此时 `fingerprint_short` 为 `''`（**空字符串，不是 None**），不发 HELLO。
- **打包**：`remote_crypto` 由 `--include-module=remote_crypto` 显式加入 `打包.txt` 与 `F_HamLog_Remote_Log_Server_2.0.0/打包-服务端.txt`。旧明文烟测一律加 `encrypt=False`。
- **`.gitignore` 必须忽略**：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、`F_HamLog_Remote_Log_Server_2.0.0/keys/`、`file/_key_backup_*/`（私钥与信任库绝不能入库）。

## 多人日志架构与生命周期（important）
- **功能只写一次**：`remote_server.py` 纯标准库 `LogServer` 引擎；客户端 `RemoteConnection`/`_SyncThread` 在 `project.py`；project 全部功能在远程模式复用，仅「落盘」改为发服务端。独立 GUI 服务端在 `F_HamLog_Remote_Log_Server_2.0.0/`，**自带 `remote_server.py` 与 `remote_crypto.py` 副本 —— 改协议/密码学须三份同步**（根 + 该目录 + 打包脚本）。
- **退出必须走 `RemoteConnection.shutdown()`，顺序不可换**：① `sync.stop()` 置位 → ② `_close_socket()`（QUIT + shutdown/close，解除 recv 阻塞）→ ③ `sync.wait(3000)` join。先关 socket 后置位会有竞态，导致主动退出被误报「连接断开」。`_SyncThread.run()` 中 emit 断开信号前必须判 `if self._running`。
- **Qt 关窗默认只隐藏、不触发 `destroyed`**：与窗口同生命周期的后台资源（连接/内嵌服务端/线程）必须在 `backup.install_close_guard` 的 `on_close` 回调里释放（「取消」分支不调用）；`destroyed` 仅作兜底，且回调里**禁止任何界面操作**（C++ 对象已删）——`_detach_remote(restore_ui=False)` 就是为此。判活用模块级 `_qt_alive(widget)`（`shiboken6.isValid`），碰界面前都要判活。
- **表格刷新**：`table_update(delete=True, persist=True)`；远程同步用 `table_update(persist=False)`——必须先 `removeWidget+deleteLater` 再重建（否则旧表格残留 → 两个表格），但不做 `list_time/save`（避免把刚拉到的内容立刻回写服务端）。
- **文案约定**：统计在线人数一律用「在线用户」（不是「在线客户端」）；「服务端信息（局域网地址/端口/密码+复制）」属「服务端」分组内的内容。客户端的管理窗只读、无退出按钮。服务端（内嵌与独立 2.0）**启动后禁用密码输入**（连带「显示/隐藏」），停止后恢复。
- **服务端发送必须按客户端加锁**：`entry['_lock']` + `_send_entry(entry,type,payload)`，`_handle` 回包与 `_broadcast`/`_notify_peers` 广播都走它——应答线程与广播线程可能同时写同一 socket。
- **默认端口 8000**：`project.DEFAULT_ROOM_PORT = 8000`（与「加入多人日志」对话框 `port_e` 默认值一致）。若被占（`LogServer.port_status == 'occupied'`）则回退 `port=0` 自动分配，不会因此开放失败。
- **Windows 端口占用探测的正确写法（踩坑）**：`remote_server.is_port_in_use(host, port)` / `_can_bind(host, port)` 用 **bind 探测**，且 ① 探测 socket **绝不能设 `SO_REUSEADDR`**（Windows 允许由此 bind 到同一已监听地址，探测恒判空闲）；② 必须试探**与 holder 完全相同**的地址（Windows 绑定语义不对称：holder 在 `127.0.0.1` 时绑 `0.0.0.0` 会成功，反之亦然；本项目服务端一律绑 `0.0.0.0`，故以 `0.0.0.0` 为探测口径）；③ **不要用 `connect_ex` 探测**（`settimeout` 后对空闲端口返回 `WSAEWOULDBLOCK(10035)`，与占用无法区分）。
- **服务端空闲判定语义（2 秒）**：只有连续 2 秒一个字节都没收到才算客户端退出（有数据就重置计时），因此大日志传输过程中的停顿不会误杀。socket 保持阻塞，**不要**再对连接 settimeout（会影响广播线程的 send）。心跳机制见 `DETAILS.md`。
- **`main.py` 只保留一个 `project_window` 引用**：新建项目窗口会回收旧窗口 → 旧窗口若开着多人日志房间，房间会静默死掉（其他端再也收不到更新）。已加 `_confirm_replace_session()` 先确认，**改动窗口管理时必须保留这个确认**。
- **「未保存更改」判定（双基线，important）**：多人日志下「服务端=已保存」，本机文件与基线语义详见 `DETAILS.md`；要点：`_bk_snapshot()` 只有非多人日志才更新 `local`，退出会话时 `last = snap if snap == local else ''`（`''` 为恒脏哨兵），关闭守卫文案由可选 `texts()` 定制。
- **本机数据文件不是测试的 playground**：`file/project_backup.fhl` 属用户真实数据（可能是未保存内容）。任何会跑 `project.main` 的测试都必须先备份该文件字节、finally 还原。

## 验证环境（离屏 GUI 冒烟）
- venv 装 PySide6-Essentials+cryptography+skyfield+numpy，可 `QT_QPA_PLATFORM=offscreen` 真实冒烟（建窗/后台线程/读表/点按钮）。
- **`project.py` 主窗口 offscreen 下硬崩溃**（无回溯、exit 1）——环境限制；`main/satellite_window/mutual_window/batch_project` 可正常离屏。
- 测完核对并还原 `file/m_xml.txt`；`m_lat/m_lon=0,0` 时卫星窗口会先弹「设置观测站」抢在待测提示前。
- **1. 离屏「嵌套模态消息框」**（`QMessageBox.exec()` 由 `accept()` 内弹）与 **2. 两进程真机回归**（`__mp_host.py`/`__mp_guest.py`，单进程无法验证同步）—— 详细步骤与 7 条踩坑见 `DETAILS.md`。

## 发布流程（GitHub Actions 全自动）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，主分支 `develop`。`.github/workflows/main.yml` 手动 `workflow_dispatch`，一次跑完：Nuitka 打包 → Inno Setup 6 安装包 → 兼容版压缩包 → 发布 Releases。
- **只需填 `version`（如 2.4.0）**；可选输入 python_version(3.13) / app_exe_name(F HamLog 2) / remote_server_exe / draft / upload_debug_artifact。
- 命名由 version 推导（先 `-replace '\.0$',''` 得 display：2.4.0→2.4，补丁版 2.4.1 保持）：安装包 `F HamLog <display> setup.exe`；兼容版 `F HamLog <display>兼容版.zip`；Release 附件沿用历史点号风格 `F.HamLog.<display>.setup.exe` / `F.HamLog.<display>.zip`（GitHub 会把空格变点），外加 `F_HamLog_Remote_Log_Server_2.0.0.exe`（直接取仓库内已打包文件，不重新打包）。安装包内部 AppVersion 仍用完整版本（2.4.0，与作者本地 iss 的习惯一致），仅文件名取 2.4。
- **Release 说明内容留空、由作者手动填写**：`gh release create <tag>` **不传** `--title`/`--notes`/`--generate-notes`（标题即 tag，正文为空）；tag=填写的 version。已存在时只 `gh release upload --clobber` 覆盖附件，**不 edit、不动标题与说明**（避免抹掉手写内容）→ 幂等可重跑。
- `.github/inno/F HamLog 2.iss` 为 CI 专用脚本（安装/升级逻辑与 `F HamLog 2 Inno Setup\F HamLog 2.iss` 一致，**AppId 相同**故升级关系不变）：路径全走 `RepoRoot`（`/D` 注入），版本/包名/ExeName 由 `/DMyAppVersion` `/DOutputBaseFilename` `/DMyAppExeName` 注入；`.github/inno/ChineseSimplified.isl` 是仓库内置中文语言文件（**运行器 Inno Setup 6.7.1 不带非官方中文包**），配套 `.gitattributes` 锁定 CRLF。
- 缓存策略：`~\AppData\Local\pip\Cache`、`~\AppData\Local\Nuitka`（辅助工具）、`.venv`（按 `第三方模块.txt` 哈希，命中后先用 import 校验，Python 补丁版本变化致 venv 失效则重建）、`main.build`（按 `*.py` 哈希，源码未变的模块跳过 C 编译与链接）。
- **踩坑（改脚本务必注意）**：① PowerShell 里**紧跟中文的变量必须写 `${var}`** —— `"$display兼容版"` 会被当成一个变量名（中文属 Unicode 字母），值静默变空；② `VersionInfo.ProductVersion` 由系统**补尾部空格**，与版本号比较必须 `.Trim()`；③ `GITHUB_ENV`/summary 一律用 `[System.IO.File]::AppendAllLines`/`WriteAllLines` + `UTF8Encoding($false)` 写，避开 `Out-File` 在不同 shell 下的 BOM 差异（并统一 `shell: pwsh`）；④ 7-Zip 打包用 `Push-Location main.dist; 7z a -tzip <dst> *`（条目落在压缩包根部，与历史一致），无 7z 时退回 `Compress-Archive`；⑤ 多行文本数组**不要用 `[string[]]` 强转**（嵌套数组会被拼成空格分隔的一行），用 `List[string]` 逐行 `Add` 后 `.ToArray()`；⑥ **`nuitka.__version__` 在 Nuitka 4.x 已移除**，读包版本一律用 `importlib.metadata.version('nuitka')`；⑦ **`run:` 块里别在 PowerShell 双引号串中写 `${{ … }}`**（会被当 `${…}` 变量引用；GitHub 虽会在执行前替换，但本地解析必报错），统一改用 `$env:GITHUB_REPOSITORY` / `$env:GITHUB_SHA`（单引号形式不受影响）。
- 本地验证手法：PyYAML 解析工作流 → 抽出每段 `run` → 替换 `${{ }}` 占位 → 交 `[Parser]::ParseFile` 查语法；再用桩 `gh.cmd`（`PATH` 前置）真实跑「解析版本号/生成安装包/压缩包/准备附件/发布」各步，验证路径与参数拼装。本机已装 Inno Setup 6.7.3（`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`）与 7-Zip。**校验脚本本身别写错**：`powershell -Command <串> <路径>` 里 `$args[0]` 取不到值，`ParseFile('')` 解析空串恒「无错误」→ 假通过；须把路径**内联**进命令串，并核对解析的确实是目标文件。
