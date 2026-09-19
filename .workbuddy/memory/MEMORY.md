# F HamLog 项目长期记忆

## 技术栈与约定
- 桌面应用，PySide6（Qt for Python）。入口 `main.py` → `project.py`（主日志窗口）。
- 日志数据：内存中 `file` 为 list，每条是 dict，字段含 date/time/m_call/o_call/freq/freq_rx/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。**注意：`record`（通联录音）字段已在当前分支移除**（见下方「通联录音：已移除」）。
- 持久化：`.fhl` 文件（utf-8 JSON，可选 AES-GCM 加密），读写走 `fhl_rw.py`。
- 设置文件：`file/m_xml.txt`，内容为 Python `eval` 可解析的 dict。键：`m_call/m_qth/m_dig/aouto_save/aouto_list` + 卫星功能新增 `m_lat/m_lon/m_alt`（观测站纬度/经度/海拔，单位°/°/m）+ 星历自动更新 `sat_auto_update`(bool)/`sat_update_hours`(int, 1–168)/`sat_last_update`(epoch 秒)。读写该文件一律用 `.get` 避免 KeyError。
- 当前版本 2.2，Nuitka 打包为独立 exe。

## 卫星预测功能
- `satellite_pred.py`：用第三方库 `skyfield`(+`numpy`) 完成全部天文计算（SGP4 传播、仰角/方位、过境检测），离线 `load.timescale(builtin=True)`。核心 API：`twoline2rv`(返回包装 `EarthSatellite` 的 `Satrec`，含 `.name/.satnum/._earth_sat`)、`observe`、`subpoint`(→lat/lon/alt)、`ground_track`(批量星下点+台站仰角)、`predict_passes`(find_events 求 AOS/MAX/LOS，`duration_sec` 秒级)、`fetch_amateur_tle`、`parse_tle_text`、`SATE_BANDS`。**`parse_tle_text` 返回的名字已 `.strip()`**（去 TLE 名称行尾随空格），与 `satrec.name`/表格 `r['name']` 一致——按名匹配（地图聚焦/TQSL/转发器）才不会错位。
- `satellite_window.py`：过境预测 GUI（由 `project.py`「卫星」菜单或 `main.py`「卫星过境」按钮打开）。每行列「记录」按钮经 `quick_log_callback`→`project.new` 快速记录。工具栏有「编辑转发器」(`sat_radio_dict.txt`)/「TQSL映射」(`tqsl_dict.txt`)/「星历自动更新」复选框。
- `satellite_auto_update.py`：`main.py` 启动时 `AutoTleUpdater(window).start()` 常驻，`QTimer` 每小时巡检 `should_update_now()`，到间隔后台线程 `_FetchThread` 调 `fetch_amateur_tle(force=True)` 刷新 `file/amateur.tle`。
- 依赖：`skyfield`+`numpy`（venv `C:\Users\13577\.workbuddy\binaries\python\envs\default`）。Nuitka 打包必带 `--include-package-data=skyfield`（缺 `.npz` 资源双击即崩）+ `--include-data-dir=file=file`。数据路径一律走 `satellite_pred.app_path(rel)`，优先含 `file/` 子目录的目录，避免从非 exe 目录启动找不到数据。

## 通联预测（双站卫星互视）
- 算法 `satellite_pred.py`：`visibility_windows()`(按最低仰角的连续可见窗口)+`predict_mutual_passes()`(两站窗口交集，交集内采样得两站最大仰角/方位/最佳时刻)+`great_circle_km()`。「最佳时刻」=`min(仰角A,仰角B)` 最大处。
- `mutual_window.py`：两 `StationBox`(经纬高+梅登黑格互转+各自最低仰角)，A 站默认 `m_lat/m_lon/m_alt`；「开始预测」按钮+`MutualWorker(QThread)`。复用 `satellite_window` 的对话框/工具函数（单向依赖）。入口 `project.py`「卫星→通联预测」(Ctrl+Shift+E)、`main.py`「通联预测」。设置键：`sat_b_lat/lon/alt`、`sat_mu_el_a/b`、`sat_mu_dur`、`sat_mu_filter`、`sat_mu_sats`。

## 卫星地图窗口（satellite_map_window.py）
- 由「卫星过境预测」(`satellite_window`) 与「通联预测」(`mutual_window`) 工具栏「地图」按钮打开：`open_map(parent, sats, home, station_b, selected_name, source, min_elev=0.0)`。
- 纯 QPainter 等距圆柱投影，不引 matplotlib。陆地 `file/world_land.json`；海洋/陆地/网格缓存 QPixmap，动态层（轨迹/当前位置/覆盖区/台站/图例）每帧叠加。已修复多圈轨迹重合、南极洲接缝、极地覆盖区绘制。
- 与来源窗口单向同步：范围/TLE→`set_sats`；表格选行→`set_satellite(name)`；台站→`set_stations`；仰角→`set_min_elev`。来源持 `win._map_window`，关图反向清理；`open_map` 对已开窗口 `raise_()` 复用。
- 多星同显：下拉「全部已选卫星(N)」或单颗；聚焦星整条加粗+覆盖区+图例●。最多显示上限可调（默认 30，1–200）。
- 轨迹时长 `sat_map_hours`(1~24h,默认3) 与 预测时长 `sat_dur`(1~240h) 独立，各自落盘并跨来源广播一致。
- 可见区段：本台仰角≥最低仰角→实线加粗；有对方台时对方可见段虚线加粗。覆盖区为 0°仰角地心半角圈；>5 颗只画聚焦星。
- **聚焦卫星有三种入口**：① 来源列表点行（自动开图/聚焦）；② 地图「显示」下拉选单颗；③ 地图画布直接点卫星（圆点/轨迹/覆盖区，悬停变手型）。列表用 `itemSelectionChanged`+`cellClicked`(跳过「记录」列) 双信号，关图后点同/异行均可重开。
- **窗口宽度一致性**：控制条含「对方最低仰角」组（仅通联预测有 station_b 时可见），`setVisible(False)` 不计入布局最小宽→两来源 `resize` 被不同最小宽覆盖而不一致。`__init__` 临时显示该组测一次统一最小宽 `setMinimumWidth(_uniform_min_w)` 再恢复，保证两处地图窗口宽度相同（均为 1192）。
- **地图铺满窗口且保持 2:1 比例**：等距圆柱投影的世界本应是 2:1（经度 360° : 纬度 180°）。原 `MapCanvas` 投影基于整个画布，窗口拉伸时地图变形；后改为 `_map_rect()` 固定 2:1 但四周留边。现 `_map_rect()` 直接返回整块画布，地图铺满窗口；`MapWindow.showEvent()` 首次显示时按「画布宽度/2」锁定窗口高度（1192 宽 → 675 高，画布 1174×587 精确 2:1），并 `setMinimumHeight` 防止被缩小变形。宽度保持统一 1192。

## 卫星名匹配（归一化，全局统一）
- `satellite_pred.py` 三个公共工具：`normalize_sat_name`（只留字母数字并大写，抹平大小写/空格/短横线/括号）、`sat_name_match(name, keys)`（多关键词 AND）、`parse_sat_keywords(text)`（按空白拆词+归一化）。
- 使用场景：① `SatelliteSelectDialog` 搜索过滤（预计算 `self._norm`，底部计数标签「匹配 N / 共 M 颗」，全选/全不选只作用于可见项）；② `lookup_transponder` 第 6 层归一化兜底（表中 `AO-91` 可匹配 TLE 名 `AO 91`）。改匹配规则时两处应同步。
- **隐藏行必须用 `QListWidget.setRowHidden(row, hide)`**，不要用 `QListWidgetItem.setHidden()`——后者只改标志、不保证触发视图 `doItemsLayout()` 重排。对话框内维护 `self._row_names`（行号→卫星名）以便按行号隐藏；过滤后 `scrollToItem(首个匹配项, PositionAtTop)`。
- 搜索期间被隐藏但已勾选的项，点「确定」仍保留在 `get_selected()` 中（有意设计）。
- **未搜索时已选置顶**：`SatelliteSelectDialog` 搜索框为空时，`_filter` 末尾调 `_reorder_pin_selected()` 把已勾选项物理重排到顶部（已选在前、保持各自原相对顺序，未选在后），并同步 `self._row_names`；`list_widget.itemChanged`→`_on_item_changed` 在未搜索时勾选一变就重新置顶（新勾选自动跳到顶部），`self._reordering` 守卫防递归。搜索中不重排（只显示匹配项）。重排取出 item 用尾部 `takeItem(count-1)`（O(1)/次）而非 `takeItem(0)`（O(N)/次），整体 O(N)，避免数千颗时 O(N²)。对话框被 `satellite_window` 与 `mutual_window` 共用，两处同时生效。

## 时间精度约定（卫星模块）
- **显示到秒**：`satellite_window._utc_to_local_str` = `%m-%d %H:%M:%S`，用于过境表「升起/落下」与通联预测表「可通联开始/结束/最佳时刻」。
- **记录到分**：「记录」预填（`preset['date']/['time']`）用 `_log_date_str`(`%Y-%m-%d`)/`_log_time_str`(`%H:%M`)，与日志表 time 字段、ADIF 精度一致。两者共用底层 `_local_fmt(dt, tz, fmt)`。

## 预测时长上限
- `satellite_pred.MAX_PREDICT_HOURS=240`/`MIN_PREDICT_HOURS=1`/`clamp_predict_hours()`，算法层+spinbox+读写设置三处兜底，越界值打开即收敛。

## 自选卫星数量上限
- `satellite_pred.MAX_SELECTED_SATELLITES=500` + `clamp_selected_count(n)` → `(保留集合, 裁掉数)`；裁剪取**排序后前 N 个**（set 无序，保证结果可复现）。
- **超限提示统一走 `satellite_window.prompt_over_limit_selection(parent, n, limit, source_hint='')`**
  → 返回 True=用户确认「清除所有选择」（已过二次确认）/ False=「重新选择」或「取消」。
  提示框与二次确认的文案、按钮（**重新选择** / **清除所有选择** / 取消，**文案不含"一键"**）全集中此处。
  `source_hint` 附来源说明。**两个入口共用它**：① `SatelliteSelectDialog.accept()`；
  ② 打开窗口读 `m_xml` 发现超限（见下）。改文案只改这里。
- `SatelliteSelectDialog.accept()`：超限不关闭，调上述函数；**选「是」后不原地重置，而是关窗重开新窗口**（性能）：
  置 `self.reset_requested=True` + `super().reject()`；两处调用方（`satellite_window`/`mutual_window` 的 `open_select`）用
  `while True:` 循环——`Accepted`→裁剪+break；`Rejected && reset_requested`→`selected_names=set()`
  后重开；否则 `return`。`_persist()/run_prediction()/推地图` 移出循环只跑一次。
  原因：原地对数千项 `setCheckState` 会逐次触发 `itemChanged`→重排+刷新标签，O(N²) 卡顿。
  旧的 `_clear_all_selected()` 已删除。
- **`m_xml` 保存的自选卫星超限时不再静默裁剪**：`satellite_window.main()` / `mutual_window.main()`
  读 `sat_sats`/`mu_sats` 后先 `clamp_selected_count` 兜底（防卡），并记 `_oversized_from_settings`；
  在 `win.show()` 之后弹 `prompt_over_limit_selection(..., source_hint='设置文件 file/m_xml.txt …')`，
  选清除则 `selected_names.clear()` + `_persist()`。
- 计数标签 = `self._count_base` 缓存基数 + `　已选 N 颗`，超限追加「，超过上限 500 颗」并转红。
  **改动时务必由缓存重建标签，不要读 `count_label.text()` 当基数**——否则每次勾选变化都会累加。
- 兜底三处：对话框 accept()、两处调用方（satellite_window / mutual_window 的 open_select）、
  以及加载设置（`sat_sats` / `mu_sats`）后立即裁剪。`import_tle()` 默认全选同样受上限约束。
- 测试 `test_max_selected_smoke.py`（36 项）含**重开循环模拟**（新窗口不继承旧选择 `已选 0`）
  与 **m_xml 超限提示**（重新选择/二次确认否/是）三组用例。

## 验证环境
- 沙箱 venv 已装 PySide6-Essentials+cryptography+skyfield+numpy，可 `QT_QPA_PLATFORM=offscreen` 做真实 GUI 冒烟（建窗/后台线程/读表/点按钮）。
- **`project.py` 主窗口在 offscreen 下硬崩溃（无回溯、exit 1）**——环境限制非代码问题；`main/satellite_window/mutual_window/batch_project` 均可正常离屏。
- 离屏测 GUI 完毕务必核对并还原 `file/m_xml.txt`（测试脚本可能写入坐标残留）。
  另注意：m_xml 里 `m_lat/m_lon=0,0` 时打开卫星窗口会先弹「设置观测站」引导框，会抢在待测提示框前面。
- **离屏测「嵌套模态消息框」的要点**（`QMessageBox.exec()` 由 `accept()` 内部弹出时）：
  ① 必须显式触发 `QTimer.singleShot(150, dlg.accept)`，否则消息框不出现；
  ② 点击用**独立 `QTimer()` 对象**轮询（`setInterval(50)`+`timeout.connect`），**不要用链式 `singleShot`**（模态嵌套后不再触发→挂死）；
  ③ 找按钮**必须限定 `isinstance(w, QMessageBox) and w.isVisible()`**（`topLevelWidgets()` 会返回主对话框自身，点到隐藏控件不触发槽）；
  ④ 被拦下后对话框**故意保持打开**，测试需再补一次点击（如「取消」）结束 `exec()`；
  ⑤ 抓第二个框要用 `delay_ms` 跳过第一个框；
  ⑥ **标准按钮 `text()` 带助记符**（实测 `'&Yes'`/`'&No'`），按文本 `=='Yes'` **点不到**，
     必须用 `w.button(QMessageBox.StandardButton.Yes)` 按 role 匹配（自定义 `addButton` 的按钮无 `&`，可按文本）；
  ⑦ 测「开窗即弹提示」时，`main()` 里的同步模态会阻塞主线程 → 用 `QTimer.singleShot(80, lambda: main(None))` 延迟触发。
  测试见 `test_max_selected_smoke.py`（36 项）。

## 呼号输入统一大写（call_upper 模块）
- 新增 `call_upper.py`（统一方案）：`UpperCallDelegate`（QTableWidget 呼号行单元格编辑实时转大写）+ `connect_callsign_upper(edit, field_getter)`（QLineEdit，仅当字段为 `m_call`/`o_call` 时实时转大写；恒定字段用 `lambda: 'm_call'`）。
- 接入点：① `project.main()` 打开项目时遍历 `file` 把每条 `m_call`/`o_call` 转大写（仅当 `filee` 为 list）；② `project.py` 的 `new()`/`project_others()` 表格行2(己方)/行3(对方) 挂委托；③ `research_call()` 搜索关键词、④ `find_replace()` 查找/替换框（按字段联动）；⑤ `set.py` 的「我的呼号」固定转大写；⑥ `batch_project.py` 模板表与翻页表（行2/3）挂委托，且 `app_list['m_call']` 取自设置即转大写。
- 委托引用须保留：挂完 `setItemDelegateForRow` 后务必要 `table._upper_call_delegate = delegate`，否则 Python 端 delegate 被回收导致编辑异常。
- 逻辑核心 `_upper_in_place` 用 `setText`+`setCursorPosition` 保光标；`text.upper()` 幂等，无需判空。

## 通联录音：已移除（不要照旧记忆实现）
- **当前分支不存在通联录音功能**。`qso_rec.py` 不存在，表格无「通联录音」列（主页表格现在是 **14 列**，末列为「更多」）。
- 历史：`f84864f` 曾加入该功能，`b6a9162`「优化批量记录」把它删除（`project.py` 61197→56663 字节，`qso_rec.py` −88 行），之后的多人日志提交（`d3f1b23` 等）也未恢复。
- 用户明确要求：**删除所有有关通联录音的内容**（残留已清理：`input_fhl.py` 默认字段、`output_excel.py` 的 `record` 过滤、`project.py` 注释、测试里的 `'record'` 大数据）。
- 若将来要重新实现，须从 `f84864f` 取回再适配当时的表格列数/字段集，**不要照搬本记忆里旧版 15 列的描述**。

## 多人日志传输加密（X25519 + AES-256-GCM）
- 需求原话：「密码输入只负责身份验证。密钥由程序自主生成，之后加密（非对称加密）分发密钥，之后再用密钥传输日志内容（对称加密）」+「全帧加密」+「X25519 ECDH」+「首次连接核对指纹」。
- **`remote_crypto.py`（纯 `cryptography`，无 GUI 依赖）**是所有密码学逻辑的唯一出处：
  - 服务端长期密钥 `X25519PrivateKey`，首次启动生成，base64 原始 32 字节私钥落盘 `<密钥根>/keys/server_<port>.fhlkey`（尝试 `chmod 0600`，Windows 上基本无效）。端口 0 时先用 `server_default.fhlkey`，`start()` 里 `os.replace` 迁到真实端口名。**换端口即换身份**。
  - **密钥根目录由 `_data_dir(fhl_path, key_dir)` 决定**，优先级 **显式 `key_dir` > `fhl_path` 所在目录 > cwd**。`LogServer(..., key_dir=...)` 是唯一入口。
    - 内嵌服务端（「开放多人日志」，`project._open_lan()`）传 **`key_dir='file'`** → 密钥统一落在 **`file/keys/`**（与各房间会话日志分开，便于查找清理）。
    - 独立服务端（`F_HamLog_Remote_Log_Server_2.0.0/main.py`）传 **`key_dir=_app_dir()`** → 密钥落在**程序目录下的 `keys/`**。
    - 两者即便端口相同也是**两把不同的密钥**（路径不同 → 指纹不同 → 信任库需分别记录），不可混用。
  - 指纹：`fingerprint()`=SHA-256 前缀 16 字节 hex（32 字符）；`fingerprint_short()`=大写 4-4 分组 8 段（如 `A1B2-C3D4-...`）。**`fingerprint_short(raw_pub_bytes)` 收的是原始字节，不是公钥对象**。
  - 握手：服务端先发 `HELLO`（`{"pub","fingerprint","fmt":"x25519-hkdf-aesgcm-v1"}`）→ 客户端回 `HELLO_ACK`（`{"ct": 加密的 login_blob, "pub": 客户端临时公钥}`）。`login_blob` = `{"password","role","ip","key": <会话密钥 b64>}`，用 ECDH 共享秘密经 `HKDF(salt=server_pub||client_pub, info=b'fhl-remote-v1', 32)` 加密。
  - **会话密钥由客户端每连接随机生成**（`new_session_key()`）经上述非对称加密通道交给服务端；密码只做身份认证，不参与内容加密。
  - 帧正文封装 `{"enc": "<b64 of nonce||tag||ciphertext>"}`，每帧独立随机 12 字节 GCM nonce。
  - **重放防护用 nonce 滑动窗口（`SessionCipher.NONCE_MEMORY=4096`：set + deque），不要用序号计数器做 AAD**。服务端会穿插 `PEERS`/`SYNC` 广播，客户端合法跳过帧会导致计数器错位、后续全部 `InvalidTag`（这是踩过的坑）。乱序解密是必须支持的。
  - `check_known_key(host, port, raw_pub)` 返回 **`(status, info)` 元组**，status ∈ `'new'|'match'|'mismatch'`；信任库 `file/known_server_keys.txt`（JSON `{"host:port": {"pub":.., "fp":..}}`）。`remember_key` / `forget_key`。
- **服务端必须先说话**（`remote_server._handle`）：加密开启时立刻发 HELLO 再读，否则两端互等直到 2 秒空闲超时（踩过的坑）。握手失败回退旧明文 `AUTH` 路径（`entry['_legacy_frame']` → `_auth_plain`），所以**旧客户端仍能连**。
- `LogServer(..., encrypt=False)` 显式关加密供排障/测试；此时 `fingerprint_short` 为 `''`（**空字符串，不是 None**），不发 HELLO。
- **客户端接入**（`project.py`）：`RemoteConnection(..., verify_fingerprint=回调)`；`_handshake()` 在收到 `LOGIN` **之前**就装好 `self.cipher`（服务端 LOGIN 之后全密文）；`self.encrypted` / `self.server_fingerprint` 记录本次状态。`_recv()` 只对 `HELLO`/`DENY` 放行明文，其余走 `open_enc_payload`。`_SyncThread.run()` 必须用 `conn._recv()`，不能直接 `recv_frame(sock)`。
- `make_fingerprint_verifier(parent, host, port)`（project.py 模块级）返回 `_verify(short_fp, raw_pub)`：`match` 静默放行；否则弹 `_fingerprint_verify_dialog`（`mismatch` 用红色粗体强警告），确认后 `remember_key`。
- 指纹 UI：`project.py` 多人日志管理窗 `lbl_fp`（「密钥指纹：」+「加密传输已启用：客户端加入时请核对上面这串指纹。」）；独立服务端 `F_HamLog_Remote_Log_Server_2.0.0/main.py` 也有 `fp_label`/`fp_note`，启动成功后填 `server.fingerprint_short`。
- **打包**：`remote_crypto` 已被 `--include-module=remote_crypto` 显式加入两份打包脚本（`打包.txt` 与 `F_HamLog_Remote_Log_Server_2.0.0/打包-服务端.txt`）。
- **`.gitignore` 必须忽略**：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、`F_HamLog_Remote_Log_Server_2.0.0/keys/`、`file/_key_backup_*/`（私钥与信任库绝不能入库）。
- 测试：`test_remote_encrypt_smoke.py`（25 项：握手/密文 FETCH/密文 SAVE/密文 SYNC/错密码 DENY/篡改 DENY/明文回退/`encrypt=False`）、`test_fp_ui_smoke.py`（18 项：指纹格式/乱序解密/重放拒绝/三种核对分支）。旧明文烟测一律加 `encrypt=False`。

## 多人日志架构与退出/生命周期约定（important）
- **功能只写一次**：`remote_server.py` 纯标准库 `LogServer` 引擎；客户端 `RemoteConnection`/`_SyncThread` 在 `project.py`；project 全部功能在远程模式复用，仅「落盘」改为发服务端。独立 GUI 服务端在 **`F_HamLog_Remote_Log_Server_2.0.0/`**（自带 `remote_server.py` **与 `remote_crypto.py`** 副本，改协议/改密码学时**三份都要同步**：根 + 该目录 + 打包脚本）。
- **退出必须走 `RemoteConnection.shutdown()`，顺序不可换**：① `sync.stop()` 置位 → ② `_close_socket()`（QUIT + shutdown/close，解除 recv 阻塞）→ ③ `sync.wait(3000)` join。先关 socket 后置位会有竞态，导致主动退出被误报「连接断开」。`_SyncThread.run()` 中 emit 断开信号前必须判 `if self._running`。
- **Qt 关窗默认只隐藏、不触发 `destroyed`**：与窗口同生命周期的后台资源（连接/内嵌服务端/线程）必须在 `backup.install_close_guard` 的 `on_close` 回调里释放（「取消」分支不调用）；`destroyed` 仅作兜底。`destroyed` 回调里**禁止任何界面操作**（C++ 对象已删），`_detach_remote(restore_ui=False)` 就是为此。
- **判活工具**：模块级 `_qt_alive(widget)`（`shiboken6.isValid`）。凡可能在窗口销毁后触发的回调，碰界面前都要判活。
- **表格刷新**：`table_update(delete=True, persist=True)`。远程同步用 `table_update(persist=False)`——必须先 `removeWidget+deleteLater` 再重建（否则旧表格残留 → 两个表格），但不做 `list_time/save`（避免把刚拉到的内容立刻回写服务端）。
- **文案约定**：统计在线人数一律用「在线用户」（不是「在线客户端」）；「服务端信息（局域网地址/端口/密码+复制）」属于「服务端」分组内的内容。客户端的管理窗只读、无退出按钮。
- 服务端（内嵌与独立 2.0）**启动后禁用密码输入**（连带「显示/隐藏」），停止后恢复。
- **服务端发送必须按客户端加锁**：`entry['_lock']` + `_send_entry(entry,type,payload)`，`_handle` 回包与 `_broadcast`/`_notify_peers` 广播都走它——应答线程与广播线程可能同时写同一 socket。
- **默认端口 8000**：`project.DEFAULT_ROOM_PORT = 8000`，「开放多人日志」按此端口启动（与「加入多人日志」对话框 `port_e` 默认值一致）。若 8000 被占（`LogServer.port_status == 'occupied'`）则回退 `port=0` 自动分配，不会因此开放失败。
- **Windows 端口占用探测的正确写法（踩坑记录）**：`remote_server.is_port_in_use(host, port)` / `_can_bind(host, port)`——用 **bind 探测**，且：① 探测 socket **绝不能设 `SO_REUSEADDR`**（Windows 允许由此 bind 到同一已监听地址，探测恒判空闲）；② 必须试探**与 holder 完全相同**的地址（Windows 绑定语义不对称：holder 在 `127.0.0.1` 时绑 `0.0.0.0` 会成功，反之亦然）；本项目服务端一律绑 `0.0.0.0`，故以 `0.0.0.0` 为探测口径。③ **不要用 connect_ex 探测**：`settimeout` 后对空闲端口返回 `WSAEWOULDBLOCK(10035)`，与占用无法区分。
- **服务端空闲判定语义（2 秒）**：`_FrameReader.read_frame(CLIENT_IDLE_TIMEOUT)`——**只有连续 2 秒一个字节都没收到**才算客户端退出（有数据就重置计时），因此大日志传输过程中的停顿不会误杀。实现用大块 `recv` + 自带缓冲 + `select`，socket 保持阻塞（**不要**再对连接 settimeout，广播线程的 send 会被影响）。哨兵 `_IDLE`/`_BAD` 是模块级对象。
- **客户端心跳（大日志保活的关键）**：`RemoteConnection._start_heartbeat()`（`start_sync` 里启动 / `_close_socket` 里停）每秒发 `NEXT`，服务端回 PONG（同步线程忽略）。同步线程改为**固定 1 秒周期**（`sleep(max(0, 1.0 - 本轮耗时))`），并对瞬时异常**重试 3 次**才报断开；`recv_frame` 返回 None（对端关闭）仍立即报断开。
- **`main.py` 只保留一个 `project_window` 引用**：新建项目窗口会回收旧窗口 → 旧窗口若开着多人日志房间，房间会静默死掉（其他端再也收不到更新）。已加 `_confirm_replace_session()` 先确认。**改动窗口管理时必须保留这个确认**。
- **两进程真机回归脚本**：仓库根的 `__mp_host.py`（房主：开房→写端口+指纹→轮询状态）与 `__mp_guest.py`（客户端：等端口→**经 `verify_fingerprint` 走真实核对路径**→加入→经真实表格加记录→轮询）；先跑 host（后台）再跑 guest，读 `__host_log.txt`/`__guest_log.txt`。**单进程无法验证同步**（`project.file` 是模块级全局，两个窗口共用）。
- **离屏 GUI 点击坑**：`app.topLevelWidgets()` 会同时返回对话框**和不可见的 parent**，`findChildren(QPushButton)` 会把两边按钮都捞出来；若点到隐藏控件上**不会触发槽函数**（表现为测试挂死在 `dlg.exec()`）。自动点按钮必须限定窗口**可见**（点 `QMessageBox` 就限定 `isinstance(w, QMessageBox) and w.isVisible()`），且只点 `btn.isVisible()` 的按钮。涉及嵌套模态消息框的完整要点见上方「验证环境」。诊断挂死位置用 `faulthandler.dump_traceback_later(N, exit=True)`。
- **shell 在本机基本不可用**：PortableGit shim 缺 `dirname`/`cat`/`head`/`tail`/`sleep`/`grep`。一律改用 `Glob`/`Grep`/`Read`/`Edit` 工具，或经 `"C:/Users/13577/.workbuddy/binaries/python/envs/default/Scripts/python.exe"` 执行；调试输出重定向到文件后用 `Read` 看，不要用 `cat`。`__mp_*.py` 跑完的 `exit=127`/`3221226505` 常是环境产物，以输出的成功哨兵为准。
- **「未保存更改」判定（双基线，important）**：`_bk_state = {'last': 已持久化基线, 'local': 最近一次写入本机文件的内容}`；`_bk_snapshot()` 里 `last` 总更新、**只有 `_rc() is None`（非多人日志）才更新 `local`**（所以既有 save/osave/打开 等调用点无需改动）。多人日志语义：服务端=已保存 → `_on_sync` 采纳服务端内容后（含「内容与服务端一致」的自愈分支）补 `_bk_snapshot()`；`_bk_write` 在多人日志下不写 `project_backup.fhl`（`force=True` 仅供关闭守卫「不保存」分支）；`_bk_tick` 多人日志下直接 return。退出会话（`_detach_remote` / `_on_disconnect`）调 `_bk_on_remote_exit()`：`last = snap if snap == local else ''`（'' 为恒脏哨兵）→ 只有内容相对本机文件确有变化才提示保存。关闭守卫文案由可选 `texts()` 回调定制：多人日志＝「未同步到服务端 / 同步 / 不同步」。
- **本机数据文件不是测试的 playground**：`file/project_backup.fhl` 属用户真实数据（可能是未保存内容）。任何会跑 `project.main` 的测试都必须先备份该文件字节、finally 还原。
