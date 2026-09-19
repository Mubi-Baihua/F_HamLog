# F HamLog 细节档案

> 由 MEMORY.md 分流出来的、可从代码复现的描述性细节。改协议/算法前先看这里。

## 卫星模块 API
- `satellite_pred.py` 用 `skyfield`+`numpy` 做全部天文计算（SGP4、仰角/方位、过境），离线 `load.timescale(builtin=True)`。
- `twoline2rv` 返回包装 `EarthSatellite` 的 `Satrec`，含 `.name/.satnum/._earth_sat`；另有 `observe`、`subpoint`（→lat/lon/alt）、`ground_track`（批量星下点+台站仰角）、`predict_passes`（find_events 求 AOS/MAX/LOS，`duration_sec` 秒级）、`fetch_amateur_tle`、`parse_tle_text`、`SATE_BANDS`、`app_path(rel)`。
- `satellite_window.py`：过境预测 GUI，由 `project.py`「卫星」菜单或 `main.py`「卫星过境」按钮打开；每行「记录」按钮经 `quick_log_callback`→`project.new` 预填；工具栏「编辑转发器」(`sat_radio_dict.txt`)/「TQSL映射」(`tqsl_dict.txt`)/「星历自动更新」复选框。
- `satellite_auto_update.py`：`main.py` 启动时 `AutoTleUpdater(window).start()` 常驻，QTimer 每小时巡检 `should_update_now()`，到间隔由后台线程 `_FetchThread` 调 `fetch_amateur_tle(force=True)` 刷新 `file/amateur.tle`。
- 通联预测算法：`visibility_windows()`（按最低仰角的连续可见窗口）+ `predict_mutual_passes()`（两站窗口交集，交集内采样得两站最大仰角/方位/最佳时刻）+ `great_circle_km()`。
- 地图：`open_map(parent, sats, home, station_b, selected_name, source, min_elev=0.0)`；纯 QPainter 等距圆柱投影（不引 matplotlib）；陆地 `file/world_land.json`；海洋/陆地/网格缓存成 QPixmap，动态层（轨迹/当前位置/覆盖区/台站/图例）每帧叠加。已修：多圈轨迹重合、南极洲接缝、极地覆盖区绘制。

## 多人日志加密协议细节
- 需求原话：「密码输入只负责身份验证。密钥由程序自主生成，之后加密（非对称加密）分发密钥，之后再用密钥传输日志内容（对称加密）」+「全帧加密」+「X25519 ECDH」+「首次连接核对指纹」。
- 服务端长期密钥：`X25519PrivateKey` 首次启动生成，base64 原始 32 字节私钥落盘 `<密钥根>/keys/server_<port>.fhlkey`（尝试 `chmod 0600`，Windows 上基本无效）。端口 0 时先用 `server_default.fhlkey`，`start()` 里 `os.replace` 迁到真实端口名。
- 密钥根目录由 `_data_dir(fhl_path, key_dir)` 决定，优先级 **显式 `key_dir` > `fhl_path` 所在目录 > cwd**；`LogServer(..., key_dir=...)` 是唯一入口。
  - 内嵌服务端（「开放多人日志」`project._open_lan()`）传 `key_dir='file'` → 密钥落在 `file/keys/`（与各房间会话日志分开，便于查找清理）。
  - 独立服务端（`F_HamLog_Remote_Log_Server_2.0.0/main.py`）传 `key_dir=_app_dir()` → 程序目录下 `keys/`。
- 指纹：`fingerprint()` = SHA-256 前缀 16 字节 hex（32 字符）；`fingerprint_short()` = 大写 4-4 分组 8 段。**`fingerprint_short(raw_pub_bytes)` 收的是原始字节，不是公钥对象**。
- 握手：服务端先发 `HELLO`（`{"pub","fingerprint","fmt":"x25519-hkdf-aesgcm-v1"}`）→ 客户端回 `HELLO_ACK`（`{"ct": 加密的 login_blob, "pub": 客户端临时公钥}`）。`login_blob` = `{"password","role","ip","key": <会话密钥 b64>}`，用 ECDH 共享秘密经 `HKDF(salt=server_pub||client_pub, info=b'fhl-remote-v1', 32)` 加密。**会话密钥由客户端每连接随机生成**（`new_session_key()`）。
- 帧正文封装 `{"enc": "<b64 of nonce||tag||ciphertext>"}`，每帧独立随机 12 字节 GCM nonce。
- 信任库 `file/known_server_keys.txt`（JSON `{"host:port": {"pub":.., "fp":..}}`）；`check_known_key(host, port, raw_pub)` 返回 **`(status, info)` 元组**，status ∈ `'new'|'match'|'mismatch'`；另有 `remember_key` / `forget_key`。
- 客户端接入（`project.py`）：`RemoteConnection(..., verify_fingerprint=回调)`；`_handshake()` 在收到 `LOGIN` **之前**就装好 `self.cipher`；`self.encrypted` / `self.server_fingerprint` 记录本次状态；`_recv()` 只对 `HELLO`/`DENY` 放行明文，其余走 `open_enc_payload`；`_SyncThread.run()` 必须用 `conn._recv()`。
- `make_fingerprint_verifier(parent, host, port)`（project.py 模块级）返回 `_verify(short_fp, raw_pub)`：`match` 静默放行；否则弹 `_fingerprint_verify_dialog`（`mismatch` 红色粗体强警告），确认后 `remember_key`。
- 指纹 UI：`project.py` 多人日志管理窗 `lbl_fp`（「密钥指纹：」+「加密传输已启用：客户端加入时请核对上面这串指纹。」）；独立服务端 `main.py` 亦有 `fp_label`/`fp_note`。
- 测试：`test_remote_encrypt_smoke.py`（25 项：握手/密文 FETCH/密文 SAVE/密文 SYNC/错密码 DENY/篡改 DENY/明文回退/`encrypt=False`）、`test_fp_ui_smoke.py`（18 项：指纹格式/乱序解密/重放拒绝/三种核对分支）。

## 服务端实现细节
- `remote_server.py` 纯标准库 `LogServer` 引擎；客户端 `RemoteConnection`/`_SyncThread` 在 `project.py`；project 全部功能在远程模式复用，仅「落盘」改为发服务端。独立 GUI 服务端在 `F_HamLog_Remote_Log_Server_2.0.0/`，**自带 `remote_server.py` 与 `remote_crypto.py` 副本**（改协议/密码学须三份同步：根 + 该目录 + 打包脚本）。
- 空闲判定语义（2 秒）：`_FrameReader.read_frame(CLIENT_IDLE_TIMEOUT)` —— **只有连续 2 秒一个字节都没收到**才算客户端退出（有数据就重置计时），因此大日志传输中的停顿不会误杀。实现用大块 `recv` + 自带缓冲 + `select`，socket 保持阻塞（**不要**再对连接 settimeout，否则影响广播线程的 send）。哨兵 `_IDLE`/`_BAD` 是模块级对象。
- 客户端心跳（大日志保活）：`RemoteConnection._start_heartbeat()`（`start_sync` 里启动 / `_close_socket` 里停）每秒发 `NEXT`，服务端回 PONG（同步线程忽略）。同步线程固定 1 秒周期（`sleep(max(0, 1.0 - 本轮耗时))`），瞬时异常**重试 3 次**才报断开；`recv_frame` 返回 None（对端关闭）仍立即报断开。
- 「未保存更改」判定（双基线）：`_bk_state = {'last': 已持久化基线, 'local': 最近一次写入本机文件的内容}`；`_bk_snapshot()` 里 `last` 总更新、**只有 `_rc() is None`（非多人日志）才更新 `local`**（所以既有 save/osave/打开 等调用点无需改动）。多人日志语义：服务端=已保存 → `_on_sync` 采纳服务端内容后（含「内容与服务端一致」的自愈分支）补 `_bk_snapshot()`；`_bk_write` 在多人日志下不写 `project_backup.fhl`（`force=True` 仅供关闭守卫「不保存」分支）；`_bk_tick` 多人日志下直接 return。退出会话（`_detach_remote` / `_on_disconnect`）调 `_bk_on_remote_exit()`：`last = snap if snap == local else ''`（`''` 为恒脏哨兵）→ 只有内容相对本机文件确有变化才提示保存。关闭守卫文案由可选 `texts()` 回调定制：多人日志＝「未同步到服务端 / 同步 / 不同步」。

## 遥控台/转发器与其它
- 转发器表 `file/sat_radio_dict.txt`、TQSL 映射 `file/tqsl_dict.txt`、星下点标记 `file/sat_map_markers.txt`。
- 呼号大写委托：挂完 `setItemDelegateForRow` 必须 `table._upper_call_delegate = delegate` 保留引用，否则 Python 端 delegate 被回收导致编辑异常。核心 `_upper_in_place` 用 `setText`+`setCursorPosition` 保光标；`text.upper()` 幂等。
- 呼号大写接入点：① `project.main()` 打开项目时遍历 `file` 把每条 `m_call`/`o_call` 转大写（仅当 `file` 为 list）；② `new()`/`project_others()` 行2(己方)/行3(对方) 挂委托；③ `research_call()` 搜索关键词；④ `find_replace()` 查找/替换框（按字段联动）；⑤ `set.py`「我的呼号」；⑥ `batch_project.py` 模板表与翻页表（行2/3），且 `app_list['m_call']` 取自设置即转大写。
