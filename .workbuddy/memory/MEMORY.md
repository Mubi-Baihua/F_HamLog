# F HamLog 项目长期记忆

> 细节档案（主题/对话框/发布流程/卫星 API/加密协议/离屏测试坑等可复现描述）见同目录 `DETAILS.md`；
> 逐次改动过程见 `YYYY-MM-DD.md`。本文件只留**约定、决策与踩坑要点**。

## 基本约定
- PySide6 桌面应用，版本 2.4，Nuitka 打包独立 exe。文件结构见 `DETAILS.md`。
- 本机 shell 部分可用（PortableGit shim 缺 `dirname`/`cat`）：`ls/head/tail/wc/rm/git` 可用。
  文件读写优先 Glob/Grep/Read/Edit；项目 venv `D:\F-Dev\BIG\F_HamLog\.venv\Scripts\python.exe`（worktree 在 C 盘、venv 在 D 盘，用绝对路径）。

## 主题系统（theme.py）——基线 = 6d48024
- **浅/深一律采用平台原生调色板，不自建兜底色**。`5e9fcbe` 的「自建调色板 + 全局 QSS 覆盖」与 `Fusion` 样式**均已被用户否决**。
- **应用保持系统原生样式（windows11）**。界面颜色一律走 `theme.py` 取色，**禁止写死**。
- **验证颜色必须看渲染像素**（`grab()`），不能只读 `palette()`。

## 文件对话框——定稿：一律原生，别自绘
- 调用处静态调 `QFileDialog.getOpen/SaveFileName(...)`；`dialog_defaults.py` 只有 `desktop_dir()`。
- **Qt 自绘 + 汉化已被否决**（丢中文/快速访问/缩略图）；本机 Qt 6.11 无原生 `#32770`，「原生+DWM」是 no-op。

## 卫星功能
- `satellite_pred.py`（skyfield+numpy 离线）。打包必带 `--include-package-data=skyfield` + `--include-data-dir=file=file`；数据路径走 `satellite_pred.app_path()`。
- 上限：预测 `MAX_PREDICT_HOURS=240`；自选 `MAX_SELECTED_SATELLITES=250`（排序后取前 N）。
- **星历数据源 = 独立文件 `file/tle_sources.txt` + 独立窗口 `tle_source_window.py`**（入口在 `set.py`）。
  - 读取顺序：独立文件 → 旧键 `sat_tle_sources`（仅兼容读）→ `DEFAULT_TLE_SOURCES`；冲突取靠前源。
  - **「添加」= 直接插入空行并进入内联编辑**（不弹 `QInputDialog`）；已有空行时聚焦不重复创建。
  - **启用/禁用写在同文件**：地址前加 `#` 即禁用；**全被禁用返回空列表**（不偷偷启用默认源）。
  - **数据源一视同仁，无 URL 特判**；**延迟探测自动进行**（打开/改完/新加/恢复默认），无「测试延迟」按钮；延迟只进 `_ROLE_DELAY` 供 delegate 自绘，**绝不写进 `item.text()`**。
- **内置默认源（2026-09-27，越靠前优先级越高）**：live.ariss.org/iss.txt → r4uab.ru/satonline.txt → amsat.org/tle/current/nasabare.txt → celestrak.org/…GROUP=active&FORMAT=csv → db.satnogs.org/api/tle/?format=3le。
- **`iter_tle_records()` 兼容 3LE / 2LE / Celestrak OMM CSV**（CSV 按列**重建** TLE 两行）。
- **下载/导入一律「按 NORAD 编号增量更新」**：同编号替换、新编号追加、**旧的一律保留**；「导入星历」**不自动勾选**。
- 入口：project「卫星→通联预测」(Ctrl+Shift+E)；main「卫星过境」「通联预测」。
- **地图画布已主题化**（深浅两套）；地图与来源**单向同步**，`sat_map_hours`/`sat_dur` 独立落盘并广播。

## 卫星名匹配与选择对话框
- `normalize_sat_name`/`sat_name_match`/`parse_sat_keywords` 用于①选择框搜索②`lookup_transponder` 第 6 层兜底；**改匹配规则两处须同步**。
- **隐藏行必须 `QListWidget.setRowHidden(row,hide)`**（`setHidden()` 不触发重排）。
- 未搜索时已选置顶（`_reordering` 守卫）；计数标签由 `self._count_base` 缓存重建。
- 超限提示统一 `prompt_over_limit_selection(...)`；`accept()` 超限不关闭 → `reset_requested=True`+`reject()`，调用方 `while True:` 重开。

## 主表格（project.py）——长日志性能定稿
- **勾选/「更多」列一律用自绘委托**（`CheckColumnDelegate`/`MoreButtonDelegate`），**禁止逐行 `setCellWidget`**（万行=2 万控件→卡死）。
- **勾选状态唯一权威 = 闭包集合 `_checked_rows`**；委托只回调 `on_toggle(row, checked)`，**委托不直接改 model**。
- 表格统一 `_new_table()` + `_fill_rows()` 构建；列常量主表与搜索窗共用。
- **UI 必须与旧版逐项一致（用户硬要求）**：14 列**全部显式设宽** `[45,80,70,90,90,70,80,90,90,80,80,120,120,80]`；**不启用 `stretchLastSection`**；**不强制行高**；「更多」按钮几何=宽度铺满单元格无缩进、高 26 居中。
  **改表格前先 `git show HEAD:project.py` 对照原实现，别自行加"优化"。**
- **重建必须还原滚动位置**：重建前记 `vbar.value()`，重建后 `QTimer.singleShot(0, lambda: bar.setValue(target))` 延迟设回（必须延到事件循环下一轮）；`scrollToBottom` 同理需延迟。
- **`table_update(delete=True, persist=True, scroll_to_bottom=False)`**：`scrollToBottom()` 仅 `scroll_to_bottom=True` 时执行（恰好三处：首开/新建保存/批量记录保存回调）；其余重建不得跳底。
- **`save()` 有「未变更跳过」**（`_last_written={'path','json'}`），**首次保存必须执行**；写文件统一 `_write_project_file(path)`。
- **`fhl_rw.write_fhl_file` 必须 `json.dumps` 后一次性 `f.write`**，**禁止 `json.dump`**。

## 悬停提示
- **2026-09-29：所有 `.setToolTip(...)` 悬停提示已整段注释（6 文件共 47 处：tle_source_window 9 / mutual_window 8 / satellite_map_window 7 / batch_project 5 / set 3 / satellite_window 15），便于日后启用。**
- **`toast_tip.py` 是动作型通知（复制/粘贴/撤销等反馈），不是悬停提示，未动**；`theme.py` 的 `QPalette.ToolTipBase/Text` 只是调色板角色，未动。
- `toast_tip.show_toast(text, parent=None, timeout=1000, kind='info')`：非模态、无边框、置顶、不抢焦点、跟随主题、1 秒自动关、多提示堆叠、父窗销毁一并销毁。**Windows 上分层窗口绝不能加 `QGraphicsDropShadowEffect`**（脏矩形越界），改用 1px 边框。
- 结果反馈类用 `toast_tip.show_toast`；二次确认/`QFileDialog`/格式错误/加解密/搜索/统计/多人日志/服务端/QRZ 等仍用对话框。

## 呼号统一大写（call_upper.py）
- `UpperCallDelegate` + `connect_callsign_upper(edit, field_getter)`（仅 m_call/o_call）；挂完 `setItemDelegateForRow` 须 `table._upper_call_delegate = delegate` 保引用。

## 通联录音：已移除
- 当前分支无该功能（`qso_rec.py` 不存在）。历史：`f84864f` 加入、`b6a9162` 删除；重建从 `f84864f` 取回再适配。

## 多人日志：加密与密钥
- 密码只做身份验证；密钥程序自主生成、非对称分发后再对称加密；**全帧加密**；首次连接核对指纹。**`remote_crypto.py`（纯 `cryptography`）是密码学唯一出处**。
- **密钥根 `_data_dir(fhl_path, key_dir)`**：显式 `key_dir` > `fhl_path` 目录 > cwd；内嵌 `key_dir='file'`→`file/keys/`，独立服务端→程序目录 `keys/`；**同端口不同来源也是两把密钥，换端口即换身份**。
- 重放防护用 **nonce 滑动窗口**，**不要**用序号计数器做 AAD（PEERS/SYNC 广播会合法跳帧→后续全 `InvalidTag`），必须支持乱序解密。
- **服务端必须先说话**（先发 HELLO 再读），否则互等 2 秒超时；握手失败回退旧明文 `AUTH`。
- `.gitignore` 必忽略：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、`F_HamLog_Remote_Log_Server_2.0.0/{keys/,main.fhl,password_xml.txt}`、`file/_key_backup_*/`。

## 多人日志：架构与生命周期
- 引擎 `remote_server.LogServer`（纯标准库）；客户端 `RemoteConnection`/`_SyncThread` 在 project.py；独立服务端目录**自带两份副本——改协议/密码学须三份同步**（根+该目录+打包脚本）。
- **退出必走 `RemoteConnection.shutdown()`，顺序不可换**：① `sync.stop()` → ② `_close_socket()`（QUIT+shutdown/close）→ ③ `sync.wait(3000)`。`_SyncThread.run()` emit 断开前须判 `self._running`。
- **Qt 关窗只隐藏、不触发 `destroyed`**：与窗口同生命周期的资源在 `backup.install_close_guard` 的 `on_close` 释放；`destroyed` 仅兜底，回调里**禁止界面操作**；判活 `_qt_alive()`。
- **`main.py` 只保留一个 `project_window` 引用**（新建回收旧窗口→旧房间死掉）；已加 `_confirm_replace_session()`，改动窗口管理必须保留。
- 服务端启动后禁用密码输入（含显示/隐藏），停止后恢复；发送按客户端加锁（`entry['_lock']`+`_send_entry`）。
- **默认端口 8000**，被占回退 `port=0`。**Windows 端口探测**：① 绝不设 `SO_REUSEADDR`；② 试探与 holder 完全相同地址（`0.0.0.0`）；③ **不要用 `connect_ex`**。
- **本机数据文件不是测试 playground**：`file/project_backup.fhl` 是真实数据；跑 `project.main` 的测试必须先备份字节、finally 还原。

## 独立服务端（F_HamLog_Remote_Log_Server_2.0.0）
- 启动即自动创建 `keys/`、`main.fhl`、`password_xml.txt`；分发只需一个 exe；`_app_dir()` 不能信 `sys.executable`/`__file__`（onefile 指向 `%TEMP%`）。
- 该 exe 带 `--windows-uac-admin`（非提权 `WinError 740`）：端到端验证要另打**去掉 uac-admin** 的临时包（不覆盖 `dist/`）；它是 git 跟踪文件，重打后需提交。

## 验证环境（离屏 GUI 冒烟）
- venv 可 `QT_QPA_PLATFORM=offscreen` 真实冒烟；主窗/卫星窗/互通窗/批量/独立服务端均可离屏。
- **坑**：槽里 `sys.exit()` 从 PySide6 C++ 边界直接终止进程 → 测试前 `sys.exit = lambda *a, **k: None`。
- 约定：测试/冒烟脚本统一放在 `test/` 目录（2026-10-02 由根目录迁入，原 `tests/` 仅含 1 个文件已合并删除）；命名 `__*_smoke.py` / `__*_probe.py` / `test_*.py`，结果 `__*_out.txt`（已被 `.gitignore` 覆盖）；**优先 monkeypatch 路径常量到临时文件**（`sp.TLE_SOURCES_PATH`/`sp.SETTINGS_PATH`/`smw.MARKERS_PATH`）。
  脚本靠 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 把项目根固定到 sys.path，移入子目录后仍可导入；内嵌子进程引导字符串里的单级 dirname（如 `__rl_autocreate_smoke.py` 的 DRIVER）**故意保留**，勿一并改成两级。
- **绝不能 `git checkout -- file/…` 还原 `file/` 数据文件**（用户正在用，可能已手工改）；测完核对并还原 `m_xml.txt`/`amateur.tle`/`sat_map_markers.txt`/`tle_sources.txt`。
- 造「导入星历」fixture：星选 `int(编号) <= 99999`（≥100000 是 Alpha-5，如 100093=`A0093`）；`'%05d'` 直写 6 位会溢出 5 列编号位。
- 提示从 `QMessageBox` 换 `toast_tip.show_toast` 后，旧 monkeypatch `QMessageBox.information` 的测试会**静默失效**→ 需同时 monkeypatch `toast_tip.show_toast`。

## Git 合并 `file/*.tle` 等数据文件
- `.tle` 冲突几乎总是「不同时刻同一批数据」：比三侧行数，**取更完整/更新一侧**（`git checkout --ours/--theirs -- file/amateur.tle`）。
- `m_xml.txt` 冲突通常只差 `sat_last_update` 时间戳 → 取较新值。
- `.workbuddy/memory/*.md` 追加型 → **双方内容全保留**，只删标记行。
- `project.py` 的 `_bk_snapshot(...)` 冲突 → 合并为 `_bk_snapshot(snap)` + 各自提示调用。

## 发布流程（GitHub Actions）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`。**默认分支 = `main`**；`develop` 是开发分支。
- **只有三个文件**：`main.yml`（手动发布，**唯一能发 Release**）、`preview.yml`（定时预览打包→Artifact）、`.github/inno/F HamLog 2.iss`。**没有 `releases.yml` / `preview-cleanup.yml`**（已被否）。
- **`main.yml`**：仅 `workflow_dispatch`，填 `version`，一次跑完 打包→安装包→兼容版 zip→回写运行分支→发 Releases（**默认草稿**）。命名自动推导；产物含远端日志服务端 exe。
- **产物回写**：安装包→`F HamLog 2 Inno Setup/F HamLog <display> setup.exe`；兼容版→`兼容版/F HamLog <display>兼容版.zip`。
  ⚠️ **历史产物在 `main` 上布局不同**：兼容版 zip 直接躺仓库根（`F HamLog 2.4兼容版.zip`，无 `兼容版/` 目录）；`兼容版/` 目录只在 `develop`。**取产物脚本必须双位置回退**（先 `兼容版/` 再仓库根）。
- **`preview.yml`（2026-09-27 定稿）**：触发 = `schedule: cron '0 20 * * *'`（北京 04:00）+ `workflow_dispatch`，**无 push**。`concurrency: preview`，`cancel-in-progress: false`。提交检测只看 `develop`（比本工作流上条 run 的 `createdAt` 之后的 `origin/develop` 提交数）。
  - 两条分支：`SHOULD_BUILD=true` 正常打包；`SHOULD_BUILD=false` **下载上一次 Artifact 当本次产物**（先 download→再删旧 Artifact→最后上传；查不到可复用→回退正常打包）。每次运行都有 Artifact。
  - 清理（无门控）：①按 `name` 删同名旧 Artifact 只留最新；②删「上次未真正打包」的 run（判 `Nuitka 独立打包` step conclusion=`skipped`，`success` 保留），全程 `continue-on-error`；DELETE 只对 **completed** run 生效，**必须排除 `SELF_RUN_ID`**。
  - 版本号 = `UTC-yyyyMMdd-HHmm`；AppName `F Ham Log 2 Preview`（独立 AppId，可与正式版共存）；不建 Release、不回写分支。
- **`workflow_dispatch`/`schedule` 只认默认分支上的工作流** → `preview.yml` 必须存在于 `main` 才会出现按钮/定时生效。
- 本机**无 `gh` CLI、无 token**（凭据 `git-credential-manager` 托管）→ 查/删 run 只能 CI 内用 `GITHUB_TOKEN`。
- **Release 说明留空由作者手填**：`gh release create` 不传 `--title/--notes`；已存在只 `gh release upload --clobber`，不 edit（幂等可重跑）。
- 安装位置：`.iss` 用 `DefaultDirName={autopf}\{#MyAppName}` + **显式 `PrivilegesRequired=admin`**（非管理员 `{autopf}` 变 `%LOCALAPPDATA%\Programs`）。正式版/预览版同级并存。`%TEMP%\is-*.tmp` 是 Inno 暂存，不是安装位置。
- 改脚本必记的坑、缓存策略、回写分支 git 序列、本地验证与 `.iss` 约定见 `DETAILS.md`。
