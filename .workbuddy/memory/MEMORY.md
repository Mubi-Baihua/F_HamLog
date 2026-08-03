# F HamLog 项目长期记忆

## 技术栈与约定
- 桌面应用，PySide6（Qt for Python）。入口 `main.py` → `project.py`（主日志窗口）。
- 日志数据：内存中 `file` 为 list，每条是 dict，字段含 date/time/m_call/o_call/freq/freq_rx/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。
- 持久化：`.fhl` 文件（utf-8 JSON，可选 AES-GCM 加密），读写走 `fhl_rw.py`。
- 设置文件：`file/m_xml.txt`，内容为 Python `eval` 可解析的 dict。键：`m_call/m_qth/m_dig/aouto_save/aouto_list` + 卫星功能新增 `m_lat/m_lon/m_alt`（观测站纬度/经度/海拔，单位°/°/m）+ 星历自动更新 `sat_auto_update`(bool)/`sat_update_hours`(int, 1–168)/`sat_last_update`(epoch 秒)。读写该文件一律用 `.get` 避免 KeyError。

## 卫星预测功能（2026-07-26 新增，2026-07-27 改用 skyfield）
- `satellite_pred.py`：**使用第三方库 `skyfield`（+`numpy`）** 完成全部天文计算（SGP4 传播、ECI→ECEF 旋转、GMST、仰角/方位、过境事件检测），离线用 `load.timescale(builtin=True)`。不再手写 SGP4/坐标变换。核心 API：`twoline2rv`(返回包装 `EarthSatellite` 的 `Satrec`，含 `.name/.satnum/._earth_sat`)、`observe`、`subpoint`(星下点 lat/lon/alt)、`predict_passes`、`fetch_amateur_tle`、`parse_tle_text`、`SATE_BANDS`（频段表）。`predict_passes` 用 `find_events` 求 AOS/MAX/LOS，`duration_sec` 为精确秒级差值。
- `satellite_window.py`：预测 GUI。由 `project.py` 的“卫星”菜单或 `main.py` 的“卫星过境”按钮打开；每行列“记录”按钮经 `quick_log_callback(preset)` 调 `project.new(preset)` 实现快速记录。工具栏新增「编辑转发器」(`sat_radio_dict.txt`) 与「TQSL映射」(`tqsl_dict.txt`) 两个按钮，打开 `DictEditorDialog` 通用键值编辑器（保留 `#` 注释行，单列值用 `value_delimiter=None`，多值用 `','`）；另有「星历自动更新」复选框实时开关设置里的 `sat_auto_update`。
- `satellite_auto_update.py`（2026-07-27 新增）：**星历(TLE)自动定时更新**。由 `main.py` 启动时 `AutoTleUpdater(window).start()` 常驻；`QTimer` 每小时巡检一次 `should_update_now()`（纯函数，便于测试），到间隔则在**后台线程 `_FetchThread`** 调 `sp.fetch_amateur_tle(force=True)` 刷新 `file/amateur.tle`，成功写 `sat_last_update`。开关/间隔完全由设置决定，改设置无需重启即生效。
- **依赖**：`skyfield` + `numpy`（已写入 `第三方模块.txt` 与 `打包.txt` 的 nuitka 命令）。沙箱验证用 venv：`C:\Users\13577\.workbuddy\binaries\python\envs\default`。
- **Nuitka 打包必带 `--include-package-data=skyfield`**：`skyfield` 的 `data/*.npz`（iers.npz 等）是运行时资源文件，`--include-package` 不会打包，缺了会导致 `load.timescale(builtin=True)` 崩溃、打包后无法读星历（与 CWD 无关，双击也炸）。另注意 `file/` 目录靠 `打包.txt` 里的 `--include-data-dir=file=file` 打包。
- **数据路径一律走 `satellite_pred.app_path(rel)`**：`satellite_pred` 提供 `_app_base_dir()`/`app_path()`，优先返回“确实含 `file/` 子目录”的目录（exe 目录优先于 `__file__` 目录），把 `file/amateur.tle`、`file/m_xml.txt`、`file/*_dict.txt` 等解析为绝对路径，避免从非 exe 目录启动（快捷方式等）时找不到数据。`satellite_window.py`/`satellite_auto_update.py` 的 `SETTINGS_PATH`/`TLE_CACHE` 已改用 `sp.app_path(...)`。

## 通联预测（双站卫星互视，2026-08-02 新增）
- 算法在 `satellite_pred.py`：`visibility_windows()`（以**用户最低仰角**为门限的连续可见窗口，带 clipped 截断标记）
  + `predict_mutual_passes()`（双指针求两站窗口交集，交集内矢量化采样得两站最大仰角/方位/最佳时刻）
  + `great_circle_km()`。「最佳时刻」= `min(仰角A, 仰角B)` 最大的时刻。
- 界面 `mutual_window.py`：两个 `StationBox`（经纬高 + 梅登黑格双向互转 + 各自最低仰角），A 站默认取 `m_lat/m_lon/m_alt`；
  显式「开始预测」按钮 + `MutualWorker(QThread)`。复用 `satellite_window` 的 `SatelliteSelectDialog/TleFetchWorker/
  _load_settings/_save_settings/_duration_str/_utc_to_local_str/LOCAL_TZ`（单向依赖，无循环导入）。
- 入口：`project.py`「卫星 → 通联预测」(Ctrl+Shift+E)、`main.py` 主页「通联预测」按钮。
- 设置新增键：`sat_b_lat/sat_b_lon/sat_b_alt`、`sat_mu_el_a/sat_mu_el_b`、`sat_mu_dur`、`sat_mu_filter`、`sat_mu_sats`。
- `batch_project.main(preset=...)` 的 preset 白名单已扩到含 `m_qth/o_qth/o_call/notes`。

## 卫星地图窗口（2026-08-03 新增，同日增强为多星同显 / 未来方向轨迹）
- `satellite_map_window.py`：全球卫星地图窗口。由「卫星过境预测」(`satellite_window.py`) 与「通联预测」(`mutual_window.py`) 工具栏的「地图」按钮打开（`open_map(parent, sats, home, station_b, selected_name, source, min_elev=0.0)`）。
- **纯 QPainter 等距圆柱投影绘制，不引入 matplotlib 等新依赖**：海洋/陆地/经纬网格只在尺寸变化时渲染并缓存为 QPixmap；动态层（地面轨迹、当前位置、覆盖区、台站标记、图例）每次 `paintEvent` 叠加。陆地数据来自 `file/world_land.json`（Natural Earth 110m 陆地多边形，已随 `打包.txt` 的 `--include-data-dir=file=file/` 打包）。
- 与来源窗口实时同步（**单向 source→map**）：
  - 范围 / 自选卫星 / TLE 刷新 → `map.set_sats(active_sats_list())`；
  - 表格行选择变化 → `map.set_satellite(name)`（聚焦高亮）；
  - 观测站/台站变化 → `map.set_stations(home, station_b)`；
  - 最低仰角变化 → `map.set_min_elev(deg)`。
  来源窗口持有 `win._map_window` 引用，地图关闭时反向清理。
- **多星同显**：下拉框可选「全部已选卫星 (N)」或只看某一颗；默认显示来源窗口「范围/自选卫星」当前生效的所有卫星，每颗一色；左下角图例；聚焦卫星（表格点选）轨迹加粗、显示覆盖区。最多显示上限可调（默认 30，范围 1–200），避免过多卫星拥挤。
- **轨迹方向**：从当前时刻起、向后延伸「轨迹时长」小时（不再是 ±时长/2 的对称窗）。
- **「轨迹时长」与「预测时长」是两个独立的量**（2026-08-03，用户明确要求分开）：
  - 预测时长 `sat_dur`（1~240h）决定过境/通联的搜索跨度，由 `satellite_window`/`mutual_window` 共用；
  - 轨迹时长 `sat_map_hours`（1~24h，默认 3）只决定地图上画多长一段星下点连线——再长会画出十几圈糊成一片。
  - 相关 API 都在 `satellite_map_window`：`clamp_track_hours` / `load_track_hours` / `save_track_hours` / `_broadcast_track_hours`，
    窗口侧 `set_track_hours(hours, persist=False)` 与 `track_hours()`。
  - 改动即落盘，关窗后仍记住；过境预测与通联预测各自打开的地图通过遍历模块级 `_open_windows` 广播，实时保持一致。
  - 两个来源窗口的 `open_map()` 都会先检查 `win._map_window` 是否仍 `isVisible()`，是则 `raise_()/activateWindow()` 复用，
    不再重复新建（否则残留窗口会参与广播）。
- **可见区段高亮**：按来源窗口最低仰角判定，轨迹上本台仰角 ≥ 该值的区段用实线加粗。
- 覆盖区为 0° 仰角地心半角圆圈（`_footprint_radius_deg(alt)` = `acos(R/(R+alt))`）；5 颗以内同时显示所有卫星覆盖区，更多时只显示聚焦卫星。
  - **极地覆盖区修复（2026-08-03）**：原 `_draw_footprint` 用 `QPainter.drawEllipse`（统一角半径椭圆），在极地有两个错误——
    (1) 经度方向没除以 `cos(lat)`，极地覆盖区在经度方向被严重低估（应收敛成绕极点的整圈，却画成窄带）；
    (2) 覆盖区越过极点时画布顶/底边截断、不封口，残缺。
  - 修复：新增 `_footprint_paths(lon,lat,ang,W,H)`，用球面小圆边界投影成多边形绘制。
    - **含极点**（|lat|+ang≥90）用「按经度解边界纬度」生成单值边界曲线，封顶/底（y=0 或 y=H）成极点帽；
      解的两支规范到 [-90,90] 后取正确半球（北极取 ≥0，南极取 ≤0），并且 `dlon` **不**归一化到 [-180,180]，
      避免 `lon_p=±180` 两端被折成不同值导致封口错位、把南极帽填成整个画布。
    - **不含极点**改用方位角采样 + 不归一化经度，生成闭合多边形后绘制「自身 + 平移 ±W 两个副本」，
      让跨 ±180° 的覆盖区从画布另一侧补现；彻底绕开了旧实现把闭合小圆边界当开放曲线用
      `_split_dateline` 切开、再被 `closeSubpath` 横贯画布连起来导致的左右两侧残缺问题。
    验证：跨 ±180° 场景（lon=179/170，赤道/高纬，ang=20/30/40）左右边缘带像素召回率 1.000；
    北极帽、南极帽、含极点跨 ±180 综合、赤道控制组均召回 1.000。
- 台站标记：本台红方块「本台」；通联预测时对方蓝方块「对方台」。
- `satellite_pred.py`：
  - 新增 `subpoint(satrec, jd_utc)` → `(lat_deg, lon_deg, alt_km)`，底层 `EarthSatellite.at(t).subpoint()`，注意返回对象是 `GeographicPosition`，属性是 `.latitude/.longitude/.elevation`（不是 `.lat/.lon`）。
  - 新增 `ground_track(satrec, start_utc, duration_hours, samples, observer=None)`：使用 skyfield 时间数组一次性批量计算整个时间窗的星下点与台站仰角，供地图后台线程使用；避免逐点 `subpoint()`/`observe()`。
- 沙箱验证用 venv：`C:\Users\13577\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（Windows 布局，注意是 `Scripts` 不是 `bin`）。
- **多圈轨迹与南极洲绘制修复（2026-08-03 后续）**：
  - 根因：`_draw_track` 对跨越 ±180° 的轨迹做了累加式经度 unwrap，导致第二圈及以后的地面轨迹被整体平移 +360° 而移出画布，看起来只剩第一圈或“多圈重合”。
  - 修复：在 `satellite_map_window.py` 新增 `_split_dateline(points)`，在 ±180° 边界按纬度线性插值切分成多段，`_draw_track` 改为对每段分别绘制；相邻圈升交点西移约 -22°~-25°，轨迹不再重合。
  - 采样密度：`_track_samples(hours)` 自适应约 1 点/分钟（120~720 钳制），避免长时长下每圈采样过少。
  - 南极洲修复：`_ring_path` 删除对陆地多边形的 unwrap 处理（原始数据已裁剪在 [-180,180]），南极洲 (180,-90)→(-180,-90) 的底边接缝不再被误判，像素级验证包围盒完整落在画布内。

## 预测时长上限（2026-08-02）
- `satellite_pred.MAX_PREDICT_HOURS = 240`（10 天）/ `MIN_PREDICT_HOURS = 1` / `clamp_predict_hours()`。
- 三处兜底：算法层（`predict_passes`/`visibility_windows` 内部钳制）、GUI spinbox `setRange`、读取与写回设置时钳制。
  历史设置里的越界值（如 999）打开窗口即自动收敛为 240。

## 验证环境提示
- 沙箱 venv（`C:\Users\13577\.workbuddy\binaries\python\envs\default`）**已装 PySide6-Essentials + cryptography + skyfield + numpy**，
  可用 `QT_QPA_PLATFORM=offscreen` 做真实 GUI 冒烟测试（构建窗口、跑后台线程、读表格内容、点按钮）。
- **但 `project.py` 的主窗口在 offscreen 下会硬崩溃（无回溯、exit 1）**，这是环境限制而非代码问题
  —— 已用 `git show HEAD:project.py` 的未修改版对照验证，同样崩溃。`main.py` / `satellite_window.py` /
  `mutual_window.py` / `batch_project.py` 均可正常离屏测试。
- 离屏测 GUI 时若脚本中途崩溃，会把测试用的坐标残留写进 `file/m_xml.txt`，**测完务必核对并还原设置文件**。
