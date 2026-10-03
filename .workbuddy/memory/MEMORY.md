# F HamLog 项目长期记忆

> 可复现细节**一律见同目录 `DETAILS.md`**（文件结构/设置键/打包/卫星 API/加密/发布/i18n 机制/离屏坑）；
> 逐次改动见 `YYYY-MM-DD.md`。本文件只留**约定、决策与踩坑**，新增细节写进 `DETAILS.md`。

## 基本约定
- PySide6 桌面应用（当前 2.6.0），Nuitka 打包独立 exe。
- 本机 shell 部分可用（shim 缺 `dirname`/`cat`）：`ls/head/tail/wc/rm/git` 可用。
- 文件读写优先 Glob/Grep/Read/Edit；项目 venv：`D:\F-Dev\BIG\F_HamLog\.venv\Scripts\python.exe`（绝对路径）。
- **不主动 git commit/push**，除非用户明确要求。
- 分支：`main`（默认/发版）、`develop`（开发）、`develop-English`（英文翻译）。

## 主题系统（theme.py）——基线 = 6d48024
- 浅/深**一律采用平台原生调色板**，不自建兜底色；应用保持**系统原生样式（windows11）**。
- `5e9fcbe` 的「自建调色板 + 全局 QSS 覆盖」与 `Fusion` 样式**均已被用户否决**。
- 界面颜色一律走 `theme.py`（`hint_css()`/`warn_css()`/`link_color()`/`watch_theme()`），**禁止写死**；
  **验证颜色必须看渲染像素**（`grab()`），不能只读 `palette()`。
- 设置持久化：`file/m_xml.txt`（`eval` 字面量 dict）；各模块只改自己的键、保留其它键。

## 多语言（i18n）——基线 = develop-English
- **中文是源语言**，不做 `tr()` 侵入式改造：文字在**显示时**查词表翻译。
  `i18n.py`（机制）+ `i18n_zh_en.py`（`TRANSLATIONS` 约 600 条）。
- 三层 = 词表 → `translate_widget()`（**只翻表头，不翻单元格**）→ `install(app)` 事件过滤器
  （`Show` 翻顶层窗、`LanguageChange` 重译）。
- 模板值里写 `{}` 表示动态片段；**捕获片段要递归再翻**，**不要按「是否含汉字」短路**。
- **切语言 = 立即原地重译**：`set_language`（+`save_language` 落盘），不重建窗口、不丢数据；
  `translate()` 幂等，中英来回切可还原。
- **新增界面代码零改动**即可跟随；**动态文案**要不走「漏斗函数」要不**逐段 `i18n.tr` 后再拼**
  ——**整条拼完再翻会漏翻**（多段中文抢同一模板）。
- **写在单元格里的固定文案**（表头之外）必须 `i18n.bind_cell_texts(win, table, texts, col=0)`：
  按**中文原文**重设 + 跟随语言、幂等还原。已接入 `project.new()` / `project.project_others()`。
- **冻结列 x = 竖向表头宽度**，随**行标签文字**变化；**只在 `resizeEvent` 重算不够**（宽窗切语言
  不触发 resize）→ 监听表头几何/`headerDataChanged` + `QTimer.singleShot(0)` **延后一轮**再同步。
- **文件对话框必须调用处翻**（原生静态 `QFileDialog.get*` 不走控件树）；Qt 标准按钮由 `qtbase_*.qm` 负责。
- 词表键 = 源码中文**逐字符一致**；`%d`/`%.2f` 拼的写成渲染后形状（占位符统一 `{}`）。
- **窗口尺寸随语言**：中文严格历史基准、英文按内容放宽（`fit_window`/`fit_min_width`）；
  **必须在 `show()` 之后量**（Show 事件才触发翻译）。
- 验证：`__i18n_smoke.py`（9 窗三阶段，漏翻/裁切/压扁须全 0）+ `__project_new_window_i18n_probe.py`
  / `__project_more_info_i18n_probe.py` / `__set_lang_row_smoke.py`。设置页
  **「颜色模式」+「语言」+「保存更改」同一行**（颜色在语言左侧）。

## 文件对话框——定稿：一律原生
- 调用处静态调 `QFileDialog.getOpen/SaveFileName(...)`；`dialog_defaults.py` 只有 `desktop_dir()`
  （默认打开桌面、默认文件名为空）。
- **Qt 自绘 + 汉化已被否决**（丢中文/快速访问/缩略图）；本机 Qt 6.11 无原生 `#32770`。

## 卫星功能（细节、API、打包见 `DETAILS.md`）
- `satellite_pred.py`（skyfield+numpy 离线）；数据路径一律走 `satellite_pred.app_path()`。
- 上限：预测 `MAX_PREDICT_HOURS=240`；自选 `MAX_SELECTED_SATELLITES=250`（排序后取前 N）。
- **星历数据源 = 独立文件 `file/tle_sources.txt` + 独立窗口 `tle_source_window.py`**（入口 `set.py`）；
  读取顺序：独立文件 → 旧键 `sat_tle_sources`（仅兼容读）→ `DEFAULT_TLE_SOURCES`。
  **定稿**：「添加」=插入空行进内联编辑（不弹框）；`#` 前缀即禁用且**全禁用返回空列表**；
  数据源一视同仁无 URL 特判；延迟自动探测（无按钮）只进 `_ROLE_DELAY`，**不写 `item.text()`**；
  下载/导入**按 NORAD 编号增量更新**（旧的保留），「导入星历」**不自动勾选**。
- 入口：project「卫星→通联预测」(Ctrl+Shift+E)；main「卫星过境」「通联预测」。
- 地图与来源**单向同步**；**改卫星名匹配规则时两处须同步**（选择框搜索 + `lookup_transponder` 兜底）。
- 选择对话框：**隐藏行必须 `setRowHidden`**（`setHidden()` 不触发重排）；超限 `accept()` 不关闭
  → `reset_requested=True`+`reject()`，调用方 `while True:` 重开。

## 主表格（project.py）——长日志性能定稿
- **勾选/「更多」列一律用自绘委托**，**禁止逐行 `setCellWidget`**（万行=2 万控件→卡死）。
- **勾选状态唯一权威 = 闭包集合 `_checked_rows`**；委托只回调 `on_toggle(row, checked)`，**不直接改 model**。
- **UI 必须与旧版逐项一致（用户硬要求）**：14 列**全部显式设宽**
  `[45,80,70,90,90,70,80,90,90,80,80,120,120,80]`；**不启用 `stretchLastSection`**；**不强制行高**。
  **改表格前先 `git show HEAD:project.py` 对照原实现，别自行加「优化」。**
- **重建必须还原滚动位置**：重建前记 `vbar.value()`，重建后 `QTimer.singleShot(0, ...)` 延迟设回；
  `scrollToBottom` 同理需延迟。
- **`table_update(...)`**：`scrollToBottom()` 仅 `scroll_to_bottom=True` 时执行
  （恰好三处：首开/新建保存/批量记录保存回调）；其余重建不得跳底。
- **`save()` 有「未变更跳过」**（`_last_written`），**首次保存必须执行**；写文件统一 `_write_project_file(path)`。
- **`fhl_rw.write_fhl_file` 必须 `json.dumps` 后一次性 `f.write`**，**禁止 `json.dump`**。

## 提示与通知
- **2026-09-29：所有 `.setToolTip(...)` 已整段注释**（6 文件共 47 处），便于日后启用。
  ⚠️ 因此 `test/__sat_window_smoke.py`「刷新星历提示列出数据源」一项**必然失败**（`toolTip()` 为空）
  ——既有状态，与 i18n 无关。
- `toast_tip.py` 是动作型通知（非悬停提示）：非模态、无边框、置顶、不抢焦点、跟随主题、1 秒关、可堆叠。
  **Windows 分层窗口绝不能加 `QGraphicsDropShadowEffect`**（脏矩形越界），用 1px 边框；
  **宽度自适口径见 `DETAILS.md`，改宽度只改 `toast_tip.py` 顶部常量区**（别退回 `label.width()`）。
- 结果反馈用 `toast_tip.show_toast`；二次确认/`QFileDialog`/格式错误/加解密/搜索/统计等仍用对话框。
- **2026-10-02：删除日志已取消二次确认（定稿）**——两处都**直接删除 + `show_toast("已删除 N 条日志。")`**，
  安全网是删除前的 `snapshot_before()`（Ctrl+Z 整表还原）。**不要再加回 `QMessageBox.question`**。
  删除后须处理 `_checked_rows`：批量删除**清空**，单条删除**行号整体前移**。

## 呼号统一大写（call_upper.py）
- `UpperCallDelegate` + `connect_callsign_upper(edit, field_getter)`（仅 m_call/o_call）；挂完
  `setItemDelegateForRow` 须 `table._upper_call_delegate = delegate` 保引用。

## 多人日志（协议与实现细节见 `DETAILS.md`）
- 密码只做身份验证；密钥程序自主生成、非对称分发后再对称加密；**全帧加密**；首次连接核对指纹。
  **`remote_crypto.py`（纯 `cryptography`）是密码学唯一出处**。
- **密钥根 `_data_dir(fhl_path, key_dir)`**：显式 `key_dir` > `fhl_path` 目录 > cwd；
  **换端口即换身份**（同端口不同来源也是两把密钥）。
- 重放防护用 **nonce 滑动窗口**（须支持乱序），**不要**用序号计数器做 AAD（广播合法跳帧→全 `InvalidTag`）。
- **服务端必须先说话**（先发 HELLO 再读），否则互等 2 秒超时；握手失败回退旧明文 `AUTH`。
- 引擎 `remote_server.LogServer`（纯标准库）；客户端在 project.py；独立服务端目录**自带两份副本
  ——改协议/密码学须三份同步**（根+该目录+打包脚本）。
- **退出必走 `RemoteConnection.shutdown()`，顺序不可换**；**Qt 关窗只隐藏、不触发 `destroyed`**
  （资源在 `backup.install_close_guard` 的 `on_close` 释放；`destroyed` 仅兜底，**回调里禁止界面操作**；
  判活 `_qt_alive()`）。
- **`main.py` 只保留一个 `project_window` 引用**；改动窗口管理必须保留 `_confirm_replace_session()`。
- **本机数据文件不是测试 playground**（`file/project_backup.fhl` 是真实数据）：测试前备份字节、finally 还原。

## 独立服务端（F_HamLog_Remote_Log_Server_2.0.0）——细节见 `DETAILS.md`
- 启动即自动创建 `keys/`、`main.fhl`、`password_xml.txt`；分发只需一个 exe。
- `_app_dir()` **不能信 `sys.executable`/`__file__`**（onefile 指向 `%TEMP%`）；`main.py` 必须自己
  `import remote_crypto`。
- 该 exe 带 `--windows-uac-admin`：端到端验证须另打**去掉 uac-admin** 的临时包（不覆盖 `dist/`）。

## 验证环境（离屏 GUI 冒烟）——细节见 `DETAILS.md`
- venv 可 `QT_QPA_PLATFORM=offscreen` 真实冒烟；主窗/卫星窗/互通窗/批量/独立服务端/地图**均可离屏**。
- **三条必记的坑**：① 槽里 `sys.exit()` 会直接终止进程 → 测试前 `sys.exit = lambda *a, **k: None`；
  ② 静态 `QFileDialog.get*`/`QMessageBox.*` 自带模态循环，**替换 `QDialog.exec` 拦不住**，必须替换
  静态方法本身；③ `os._exit()` 跳过 flush → 日志逐行写盘 + `faulthandler` 看门狗。
- 脚本统一放 `test/`（`__*_smoke.py`/`__*_probe.py`/`test_*.py`，结果 `__*_out.txt`，已 `.gitignore`）；
  **优先 monkeypatch 路径常量到临时文件**（`sp.TLE_SOURCES_PATH`/`sp.SETTINGS_PATH`/`smw.MARKERS_PATH`）。
  ⚠️ **只 patch `sp.SETTINGS_PATH` 不够**：`set.py`/`project.py`/`batch_project.py` 读设置用**硬编码
  相对路径 `file/m_xml.txt`**（绕过 `theme.settings_path()`）→ 还需 `os.chdir(临时目录)` 或备份字节还原。
- **绝不能 `git checkout -- file/…` 还原 `file/` 数据文件**（用户正在用，可能已手工改）；测完核对并还原。
- **`project.main()` 不触碰星历**（`test/__tle_write_probe.py` 可复现）：`.tle`/`m_xml.txt` md5 不变；
  **唯一星历自动更新入口是 `main.py` 的 `satellite_auto_update.AutoTleUpdater`**。
  若发现 `amateur.tle` 被重写，先怀疑**用户本机开着的应用实例**。

## Git 合并 file/ 数据文件
- `.tle` 冲突几乎总是「不同时刻同一批数据」：比三侧行数，**取更完整/更新一侧**。
- `m_xml.txt` 冲突通常只差 `sat_last_update` 时间戳 → 取较新值。
- `.workbuddy/memory/*.md` 追加型 → **双方内容全保留**，只删标记行。
- `project.py` 的 `_bk_snapshot(...)` 冲突 → 合并为 `_bk_snapshot(snap)` + 各自提示调用。

## 发布流程（GitHub Actions）——细节见 `DETAILS.md`
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，默认分支 `main`；**只有三个文件**：`main.yml`
  （手动发布，**唯一能发 Release**）、`preview.yml`（cron 定时预览→Artifact，**无 push**）、
  `.github/inno/F HamLog 2.iss`。**没有** `releases.yml`/`preview-cleanup.yml`（已被否）。
- **`workflow_dispatch`/`schedule` 只认默认分支上的工作流** → `preview.yml` 必须存在于 `main` 才生效。
- 本机**无 `gh` CLI、无 token** → 查/删 run 只能 CI 内用 `GITHUB_TOKEN`。
- ⚠️ **取产物脚本必须双位置回退**（先 `兼容版/` 再仓库根——历史产物布局不同）。
