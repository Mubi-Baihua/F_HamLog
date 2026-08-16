# F HamLog 项目长期记忆

## 技术栈与约定
- 桌面应用，PySide6（Qt for Python）。入口 `main.py` → `project.py`（主日志窗口）。
- 日志数据：内存中 `file` 为 list，每条是 dict，字段含 date/time/m_call/o_call/freq/freq_rx/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes + **record（通联录音，base64 编码的音频二进制，空串表示无录音）**。
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

## 预测时长上限
- `satellite_pred.MAX_PREDICT_HOURS=240`/`MIN_PREDICT_HOURS=1`/`clamp_predict_hours()`，算法层+spinbox+读写设置三处兜底，越界值打开即收敛。

## 验证环境
- 沙箱 venv 已装 PySide6-Essentials+cryptography+skyfield+numpy，可 `QT_QPA_PLATFORM=offscreen` 做真实 GUI 冒烟（建窗/后台线程/读表/点按钮）。
- **`project.py` 主窗口在 offscreen 下硬崩溃（无回溯、exit 1）**——环境限制非代码问题；`main/satellite_window/mutual_window/batch_project` 均可正常离屏。
- 离屏测 GUI 完毕务必核对并还原 `file/m_xml.txt`（测试脚本可能写入坐标残留）。

## 呼号输入统一大写（call_upper 模块）
- 新增 `call_upper.py`（统一方案）：`UpperCallDelegate`（QTableWidget 呼号行单元格编辑实时转大写）+ `connect_callsign_upper(edit, field_getter)`（QLineEdit，仅当字段为 `m_call`/`o_call` 时实时转大写；恒定字段用 `lambda: 'm_call'`）。
- 接入点：① `project.main()` 打开项目时遍历 `file` 把每条 `m_call`/`o_call` 转大写（仅当 `filee` 为 list）；② `project.py` 的 `new()`/`project_others()` 表格行2(己方)/行3(对方) 挂委托；③ `research_call()` 搜索关键词、④ `find_replace()` 查找/替换框（按字段联动）；⑤ `set.py` 的「我的呼号」固定转大写；⑥ `batch_project.py` 模板表与翻页表（行2/3）挂委托，且 `app_list['m_call']` 取自设置即转大写。
- 委托引用须保留：挂完 `setItemDelegateForRow` 后务必要 `table._upper_call_delegate = delegate`，否则 Python 端 delegate 被回收导致编辑异常。
- 逻辑核心 `_upper_in_place` 用 `setText`+`setCursorPosition` 保光标；`text.upper()` 幂等，无需判空。

## 通联录音（record 字段）
- 新增 `qso_rec.py`：音频字节 ↔ base64（`encode_record`/`decode_record`），`detect_audio_ext` 按文件头魔数猜扩展名（wav/mp3/ogg/flac/m4a），`play_audio_bytes` 写到临时文件后用系统默认播放器打开（`os.startfile`/open/xdg-open）。
- 主页表格「通联录音」列为**第 13 列、位于「更多」列（第 14 列）之前**；按钮用默认 QPushButton 样式（与「更多」一致）：无录音显示「添加」，有录音显示「▶播放 / 删除」。搜索结果表格 `table_r` 同步同样布局，操作直接作用于 `file[orig_index]`。
- **「更多信息」(`project_others`) 与「新建日志」(`new`) 窗口也内置录音控件**（添加/播放/删除），操作 `file[index]['record']` / `file_app['record']`；新建窗口的录音随「新建日志」一并落盘。该控件以**独立表格行「通联录音」呈现，位于「备注」行之前**（把 `'record': '通联录音'` 插入两窗口的 `translation_dict` 并置于 `'notes'` 前，构建循环对 `record` 键用 `setCellWidget` 放 `build_record_cell` 而非文本单元格；`project_others.save_changes` 校验循环对 `cell is None` 的录音行 `continue` 跳过），不再作为表格下方的悬浮布局。
- 新增 `silent_save()`：强制静默 `fhl_rw.write_fhl_file` 写盘，**不受「自动保存」开关影响**——`attach_recording`/`delete_recording` 增删后即时落盘（用户要求“添加后自动保存”）。
- `play_recording` 播放时弹窗显示该日志的「时间 + 对方呼号」（`date`/`time`/`o_call`）。
- 数据模型：`record` 默认 `''`（无录音）；`_ensure_log_keys`、`new()` 模板、`input_fhl._ensure_log_keys` 均补默认，保证字段一致。该字段已加入 `COPY_FIELDS` / `FIELD_LABELS`（中文表头「通联录音」），剪贴板复制/粘贴可往返携带录音 base64；但仍不进 Excel / ADI 导出白名单（避免超大 base64 写入表格/ADI 文件）。
- 不依赖 `QtMultimedia`（PySide6-Essentials 不含），播放走系统默认播放器；加密模式下 base64 字符串随 JSON 一起 AES-GCM 加密。
