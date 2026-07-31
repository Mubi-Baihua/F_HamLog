# F HamLog 项目长期记忆

## 技术栈与约定
- 桌面应用，PySide6（Qt for Python）。入口 `main.py` → `project.py`（主日志窗口）。
- 日志数据：内存中 `file` 为 list，每条是 dict，字段含 date/time/m_call/o_call/freq/freq_rx/mode/prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。
- 持久化：`.fhl` 文件（utf-8 JSON，可选 AES-GCM 加密），读写走 `fhl_rw.py`。
- 设置文件：`file/m_xml.txt`，内容为 Python `eval` 可解析的 dict。键：`m_call/m_qth/m_dig/aouto_save/aouto_list` + 卫星功能新增 `m_lat/m_lon/m_alt`（观测站纬度/经度/海拔，单位°/°/m）+ 星历自动更新 `sat_auto_update`(bool)/`sat_update_hours`(int, 1–168)/`sat_last_update`(epoch 秒)。读写该文件一律用 `.get` 避免 KeyError。

## 卫星预测功能（2026-07-26 新增，2026-07-27 改用 skyfield）
- `satellite_pred.py`：**使用第三方库 `skyfield`（+`numpy`）** 完成全部天文计算（SGP4 传播、ECI→ECEF 旋转、GMST、仰角/方位、过境事件检测），离线用 `load.timescale(builtin=True)`。不再手写 SGP4/坐标变换。核心 API：`twoline2rv`(返回包装 `EarthSatellite` 的 `Satrec`，含 `.name/.satnum/._earth_sat`)、`observe`、`predict_passes`、`fetch_amateur_tle`、`parse_tle_text`、`SATE_BANDS`（频段表）。`predict_passes` 用 `find_events` 求 AOS/MAX/LOS，`duration_sec` 为精确秒级差值。
- `satellite_window.py`：预测 GUI。由 `project.py` 的“卫星”菜单或 `main.py` 的“卫星过境”按钮打开；每行列“记录”按钮经 `quick_log_callback(preset)` 调 `project.new(preset)` 实现快速记录。工具栏新增「编辑转发器」(`sat_radio_dict.txt`) 与「TQSL映射」(`tqsl_dict.txt`) 两个按钮，打开 `DictEditorDialog` 通用键值编辑器（保留 `#` 注释行，单列值用 `value_delimiter=None`，多值用 `','`）；另有「星历自动更新」复选框实时开关设置里的 `sat_auto_update`。
- `satellite_auto_update.py`（2026-07-27 新增）：**星历(TLE)自动定时更新**。由 `main.py` 启动时 `AutoTleUpdater(window).start()` 常驻；`QTimer` 每小时巡检一次 `should_update_now()`（纯函数，便于测试），到间隔则在**后台线程 `_FetchThread`** 调 `sp.fetch_amateur_tle(force=True)` 刷新 `file/amateur.tle`，成功写 `sat_last_update`。开关/间隔完全由设置决定，改设置无需重启即生效。
- **依赖**：`skyfield` + `numpy`（已写入 `第三方模块.txt` 与 `打包.txt` 的 nuitka 命令）。沙箱验证用 venv：`C:\Users\13577\.workbuddy\binaries\python\envs\default`。
- **Nuitka 打包必带 `--include-package-data=skyfield`**：`skyfield` 的 `data/*.npz`（iers.npz 等）是运行时资源文件，`--include-package` 不会打包，缺了会导致 `load.timescale(builtin=True)` 崩溃、打包后无法读星历（与 CWD 无关，双击也炸）。另注意 `file/` 目录靠 `打包.txt` 里的 `--include-data-dir=file=file` 打包。
- **数据路径一律走 `satellite_pred.app_path(rel)`**：`satellite_pred` 提供 `_app_base_dir()`/`app_path()`，优先返回“确实含 `file/` 子目录”的目录（exe 目录优先于 `__file__` 目录），把 `file/amateur.tle`、`file/m_xml.txt`、`file/*_dict.txt` 等解析为绝对路径，避免从非 exe 目录启动（快捷方式等）时找不到数据。`satellite_window.py`/`satellite_auto_update.py` 的 `SETTINGS_PATH`/`TLE_CACHE` 已改用 `sp.app_path(...)`。

## 验证环境提示
- 沙箱内无 PySide6，无法运行 GUI；只能 `py_compile` 校验 + 对纯 Python 模块（`satellite_pred.py`）做运行时冒烟测试。
