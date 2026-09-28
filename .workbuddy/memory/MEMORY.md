# F HamLog 项目长期记忆

> 细节档案（主题/对话框/发布流程/卫星 API/加密协议/离屏测试坑等可复现描述）见同目录 `DETAILS.md`；
> 逐次改动过程见 `YYYY-MM-DD.md`。本文件只留**约定、决策与踩坑要点**。

## 基本约定
- PySide6 桌面应用，版本 2.4，Nuitka 打包独立 exe。文件结构见 `DETAILS.md`。
- 本机 shell 部分可用（PortableGit shim 缺 `dirname`/`cat`）：`ls/head/tail/wc/rm/git` 可用。
  文件读写优先 Glob/Grep/Read/Edit；命令输出写文件再 Read。
  项目 venv `D:\F-Dev\BIG\F_HamLog\.venv\Scripts\python.exe`（worktree 在 C 盘、venv 在 D 盘，用绝对路径）。

## 主题系统（theme.py）——基线 = 6d48024
- **浅/深一律采用平台原生调色板，不自建兜底色**。`5e9fcbe` 的「自建调色板 + 全局 QSS 覆盖」
  与 `Fusion` 样式**均已被用户否决，勿再走**。
- **应用保持系统原生样式（windows11）**。界面颜色一律走 `theme.py` 取色，**禁止写死**。
- **验证颜色必须看渲染像素**（`grab()`），不能只读 `palette()`。其余取色 API 与坑见 `DETAILS.md`。

## 文件对话框——定稿：一律原生，别自绘
- 调用处静态调 `QFileDialog.getOpen/SaveFileName(...)`；`dialog_defaults.py` 只有 `desktop_dir()`。
- **Qt 自绘 + 汉化方案已被用户否决**（丢中文/快速访问/缩略图）；本机 Qt 6.11 无原生 `#32770`，
  「原生+DWM」是 no-op。详见 `DETAILS.md`。

## 卫星功能
- `satellite_pred.py`（skyfield+numpy 离线）。打包必带 `--include-package-data=skyfield`
  + `--include-data-dir=file=file`；数据路径走 `satellite_pred.app_path()`。
- 上限：预测 `MAX_PREDICT_HOURS=240`（`clamp_predict_hours()`）；自选
  `MAX_SELECTED_SATELLITES=250`（`clamp_selected_count()` 取排序后前 N）。
- **星历数据源 = 独立文件 `file/tle_sources.txt` + 独立窗口 `tle_source_window.py`**（入口在 `set.py`）。
  - 读取顺序：独立文件 → 旧键 `sat_tle_sources`（仅兼容读）→ `DEFAULT_TLE_SOURCES`；冲突取靠前源。
  - **「添加」= 直接插入空行并进入内联编辑**（不弹 `QInputDialog`）；已有空行时聚焦不重复创建。
  - **启用/禁用写在同一文件里**：地址前加一个 `#` 即禁用。**全被禁用时返回空列表**（不偷偷启用默认源）。
  - **数据源一视同仁**，**没有 URL 特判**。
  - **延迟探测自动进行**（打开/改完地址/新添加/恢复默认），**没有「测试延迟」按钮**；
    延迟只进 `_ROLE_DELAY` 供 delegate 自绘，**绝不写进 `item.text()`**。
- **内置默认源（2026-09-27 用户指定，越靠前优先级越高）**：live.ariss.org/iss.txt →
  r4uab.ru/satonline.txt → amsat.org/tle/current/nasabare.txt →
  celestrak.org/…GROUP=active&FORMAT=csv → db.satnogs.org/api/tle/?format=3le。
- **`iter_tle_records()` 兼容 3LE / 2LE / Celestrak OMM CSV**（CSV 按列**重建** TLE 两行）。
  重建规则与实测对照见 `DETAILS.md` 与 `__csv_tle_smoke.py`。
- **下载/导入一律「按 NORAD 编号增量更新」**（`merge_update_satellites`）：同编号替换、新编号追加、
  **旧的一律保留**。「导入星历」**不自动勾选**。
- 入口：project「卫星→通联预测」(Ctrl+Shift+E)；main「卫星过境」「通联预测」。
- **地图画布已主题化**（深浅两套；浅色=灰白极简）。地图与来源**单向同步**；
  `sat_map_hours` 与 `sat_dur` 独立落盘并广播。

## 卫星名匹配与选择对话框
- `normalize_sat_name`/`sat_name_match`/`parse_sat_keywords` 用于①选择框搜索②`lookup_transponder`
  第 6 层兜底；**改匹配规则两处须同步**。
- **隐藏行必须 `QListWidget.setRowHidden(row,hide)`**（`QListWidgetItem.setHidden()` 不触发重排）。
- 未搜索时已选置顶（`_reordering` 守卫）；计数标签**必须由 `self._count_base` 缓存重建**。
- 超限提示统一走 `prompt_over_limit_selection(...)`；`accept()` 超限不关闭 →
  `reset_requested=True`+`reject()`，调用方 `while True:` 重开。测试 `test_max_selected_smoke.py`。

## 主表格（project.py）——长日志性能定稿
- **勾选列 / 「更多」列一律用自绘委托**（`CheckColumnDelegate`/`MoreButtonDelegate`），
  **禁止再逐行 `setCellWidget` 塞 QWidget/QCheckBox/QPushButton**（10000 行 = 2 万控件 → 卡死）。
- **勾选状态唯一权威 = 闭包集合 `_checked_rows`**；委托只回调 `on_toggle(row, checked)`
  （主表 `_tbl_check_toggle`、搜索窗 `_sr_toggle`），**委托不直接改 model**（否则 item 与集合分叉）。
- 表格统一由 `_new_table()` + `_fill_rows()` 构建（冻结刷新、批量 setItem）。
  列定义常量 `_TABLE_HEADERS/_TABLE_COL_WIDTHS/_TABLE_FIELDS`，主表与搜索窗共用。
- **UI 必须与旧版逐项一致（用户硬要求）**：14 列**全部显式设宽**（`_TABLE_COL_WIDTHS=[45,80,70,90,90,70,80,90,90,80,80,120,120,80]`）；
  **不启用 `stretchLastSection`**；**不强制行高**（旧 `setDefaultSectionSize(24)` 本就是注释掉的，行高走 Qt 默认）；
  委托外观对齐旧控件（勾选指示器走 `PM_IndicatorWidth`；
  「更多」按钮几何 = **宽度铺满单元格无左右缩进**、高度 26 居中，对应旧 `QPushButton.setFixedHeight(26)` 铺满整格）。
  **改表格前先 `git show HEAD:project.py` 对照原实现，别自行加"优化"。**
- 全选/反选/取消选择 = 集合运算 + 批量写回，**不再逐行 findChild**。
- **`table_update(delete=True, persist=True, scroll_to_bottom=False)`**：
  `scrollToBottom()` **只在 `scroll_to_bottom=True`** 时执行。传 True 的**恰好三处**：
  ① 首次打开项目（`table_update(delete=False)` + `table_update(scroll_to_bottom=True)`）；
  ② `new()` 保存 —— 「新建日志」窗口（Ctrl+N）；
  ③ `append_to_project()` —— 卫星「记录」/「批量记录」保存回调。
  其余重建（排序/编辑/删除/**点「更多」保存**/导入/撤销/远程同步）**不得跳底**，须保持当前滚动位置。
- **重建必须还原滚动位置**（否则每次新建 QTableWidget 都回顶部）：重建前记
  `table.verticalScrollBar().value()`，重建后 **`QTimer.singleShot(0, lambda: bar.setValue(target))`**
  延迟设回——**必须延到事件循环下一轮**，否则视口高度未定会被布局重置回顶部。
  `scrollToBottom` 同理需延迟（同步调用会少滚 1 行）。行数变少时 setValue 自动收敛，无需 clamp。
- **`table_update` 的重建耗时可接受（~0.6s/万行）**；行数 ≥2000 时显示 `WaitCursor`。
- **`save()` 有「未变更跳过」**：靠 `_last_written={'path','json'}` 判「同路径+同内容」；
  **首次保存必须执行**（勿简化为只比对 `_bk_state`，否则破坏「普通项目打开即自动保存一次」）。
  写文件统一走 `_write_project_file(path)`（返回快照供 `_bk_snapshot(snap)` 复用）。
- **`fhl_rw.write_fhl_file` 必须 `json.dumps` 后一次性 `f.write`**，
  **禁止 `json.dump(data, f)`**（上千条起会退化为几十万次小 write）。
- 测试钩子：`project.main` 末尾 `window._perf_api`（见 `DETAILS.md`/当日日志）。

## 呼号统一大写（call_upper.py）
- `UpperCallDelegate` + `connect_callsign_upper(edit, field_getter)`（仅 m_call/o_call）；
  接入点见 `DETAILS.md`。挂完 `setItemDelegateForRow` 必须
  `table._upper_call_delegate = delegate` 保引用。

## 通联录音：已移除（勿照旧版记忆实现）
- 当前分支无该功能（`qso_rec.py` 不存在）。历史：`f84864f` 加入、`b6a9162` 删除；
  重建从 `f84864f` 取回再适配。

## 多人日志：加密与密钥
- 需求：密码只做身份验证；密钥程序自主生成、非对称分发后再对称加密内容；**全帧加密**；
  首次连接核对指纹。协议字段/握手见 `DETAILS.md`。
  **`remote_crypto.py`（纯 `cryptography`）是密码学唯一出处**。
- **密钥根 `_data_dir(fhl_path, key_dir)`**：显式 `key_dir` > `fhl_path` 目录 > cwd；
  内嵌 `key_dir='file'`→`file/keys/`，独立服务端→程序目录 `keys/`。
  **同端口不同来源也是两把密钥；换端口即换身份**。
- 重放防护用 **nonce 滑动窗口**，**不要用序号计数器做 AAD**（PEERS/SYNC 广播会让客户端合法跳帧
  → 后续全 `InvalidTag`）；必须支持乱序解密。
- **服务端必须先说话**（先发 HELLO 再读），否则互等到 2 秒空闲超时；握手失败回退旧明文 `AUTH`。
- **`.gitignore` 必须忽略**：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、
  `F_HamLog_Remote_Log_Server_2.0.0/{keys/,main.fhl,password_xml.txt}`、`file/_key_backup_*/`。

## 多人日志：架构与生命周期
- **功能只写一次**：引擎 `remote_server.LogServer`（纯标准库）；客户端 `RemoteConnection`/`_SyncThread`
  在 project.py；独立服务端目录**自带两份副本——改协议/密码学须三份同步**（根 + 该目录 + 打包脚本）。
- **退出必走 `RemoteConnection.shutdown()`，顺序不可换**：① `sync.stop()` → ② `_close_socket()`
  （QUIT + shutdown/close）→ ③ `sync.wait(3000)`。`_SyncThread.run()` emit 断开前必须判 `self._running`。
- **Qt 关窗只隐藏、不触发 `destroyed`**：与窗口同生命周期的资源必须在 `backup.install_close_guard`
  的 `on_close` 里释放（「取消」分支不调用）；`destroyed` 仅兜底，回调里**禁止界面操作**。
  判活用 `_qt_alive()`（`shiboken6.isValid`）。
- **表格刷新**：`table_update(delete=True, persist=True)`；远程同步用 `persist=False`。
- **文案**：在线人数一律「在线用户」；「服务端信息」属「服务端」分组；客户端管理窗只读无退出按钮；
  服务端**启动后禁用密码输入**（含「显示/隐藏」），停止后恢复。
- **服务端发送按客户端加锁**（`entry['_lock']` + `_send_entry`）。
- **默认端口 8000**，被占回退 `port=0`。**Windows 端口占用探测**：bind 探测——① 绝不能设
  `SO_REUSEADDR`；② 必须试探与 holder 完全相同的地址（`0.0.0.0`）；③ **不要用 `connect_ex`**。
- 空闲判定 2 秒；连接 socket 保持阻塞，**不要** settimeout。心跳见 `DETAILS.md`。
- **`main.py` 只保留一个 `project_window` 引用**：新建窗口会回收旧窗口 → 旧房间静默死掉；
  已加 `_confirm_replace_session()`，**改动窗口管理必须保留**。
- **「未保存更改」双基线**（多人日志下服务端=已保存）与关闭守卫文案见 `DETAILS.md`。
- **本机数据文件不是测试 playground**：`file/project_backup.fhl` 是用户真实数据；
  任何会跑 `project.main` 的测试必须先备份字节、finally 还原。

## 独立服务端（F_HamLog_Remote_Log_Server_2.0.0）
- 启动即自动创建 `keys/`、`main.fhl`、`password_xml.txt`；分发只需一个 exe；
  `_app_dir()` 不能信 `sys.executable`/`__file__`（onefile 下指向 `%TEMP%`）——见 `DETAILS.md`。
- 该 exe 带 `--windows-uac-admin`（非提权启动 `WinError 740`）：端到端验证要另打**去掉 uac-admin**
  的临时包（不覆盖 `dist/`）。它是 git 跟踪文件，重打后需提交。

## 验证环境（离屏 GUI 冒烟）
- venv 可 `QT_QPA_PLATFORM=offscreen` 真实冒烟；主窗/卫星窗/互通窗/批量/独立服务端均可离屏。
- **坑**：槽里的 `sys.exit()`（如 esave）会从 PySide6 的 C++ 边界直接终止进程 → 测试前临时
  `sys.exit = lambda *a, **k: None`。
- 约定：冒烟脚本命名 `__*_smoke.py`，结果写 `__*_out.txt`（已被 `.gitignore` 覆盖）。
  **优先把路径常量 monkeypatch 到临时文件**（`sp.TLE_SOURCES_PATH`/`sp.SETTINGS_PATH`/
  `smw.MARKERS_PATH`）。
- 测完核对并还原 `file/m_xml.txt`（及 `file/amateur.tle`、`file/sat_map_markers.txt`、
  `file/tle_sources.txt`）；`m_lat/m_lon=0,0` 时卫星窗口会先弹「设置观测站」抢在待测提示前。
- **绝对不要用 `git checkout -- file/…` 还原 `file/` 下的数据文件**：那是用户**正在使用**的数据，
  随时可能被用户手工改过。宁可保留改动也不要 checkout。
- 造「导入星历」fixture：星必须选 `int(编号) <= 99999`——≥100000 是 Alpha-5（100093 写作
  `A0093`），`'%05d'` 直写 6 位数会溢出 5 列编号位、被错位解析。
- 其余离屏坑（嵌套模态消息框、FakeWorker、两进程真机回归）见 `DETAILS.md`。

## 发布流程（GitHub Actions）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`。**默认分支 = `main`**（`origin/HEAD → main`）；
  `develop` 是开发分支（定时预览的提交检测只看它）。
  **只有三个文件**：`main.yml`（手动发布，**唯一能发 Release 的工作流**）、
  `preview.yml`（定时预览打包 → Artifact）、`.github/inno/F HamLog 2.iss`。
  **没有 `releases.yml`**（曾试建，2026-09-27 用户否决并已删除，勿再引入）。
  **没有 `preview-cleanup.yml`**（伴随工作流方案曾被否，用户改选「单文件+下次运行清理」，勿再引入）。
- **`main.yml`**：**仅手动**（`workflow_dispatch`）触发，只填 `version`，一次跑完打包 → 安装包
  → 兼容版 zip → **回写运行分支** → 发 Releases（**默认草稿**，`draft` 输入默认 `'true'`）。
  命名自动推导。它是唯一能发 Release 的工作流。产物含远端日志服务端 exe。
- **产物回写位置**：安装包 → `F HamLog 2 Inno Setup/F HamLog <display> setup.exe`；
  兼容版 → `兼容版/F HamLog <display>兼容版.zip`。
  ⚠️ **但历史产物在 `main` 上布局不同**：兼容版 zip 直接躺在**仓库根目录**
  （`F HamLog 2.4兼容版.zip`，**没有 `兼容版/` 文件夹**），`兼容版/` 目录只在 `develop` 上。
  → **任何按固定路径取产物的脚本都必须双位置回退**（先 `兼容版/`，再仓库根）。
- **`preview.yml`**（**2026-09-27 定稿**）：
  - **触发 = `schedule: cron '0 20 * * *'`（UTC 20:00 = 北京 04:00）+ `workflow_dispatch`**。
    **没有 `push` 触发**。`concurrency: group: preview`，`cancel-in-progress: false`。
  - `permissions: contents: read` + **`actions: write`**（删旧 Artifact/删旧 run）；
    跨 run 下载 Artifact 还需 `actions: read`（`GITHUB_TOKEN` 默认具备）。
  - **提交检测只看 `develop`**：起点 = 本工作流上一条历史 run 的 `createdAt`
    （`gh run list --workflow=preview.yml --limit=1 --json createdAt`），
    再 `git rev-list --count --since="<createdAt>" origin/develop`。
    首次查不到历史 → 视为有新提交，正常打包。
  - **两条分支（核心）**：
    - `SHOULD_BUILD=true`（有新提交）→ 正常打包 Nuitka + Inno + zip。
    - `SHOULD_BUILD=false`（无新提交）→ **下载上一次的产物当本次产物**：
      `gh api .../actions/artifacts?name=<ARTIFACT_NAME>&per_page=1` 取
      `.artifacts[0].workflow_run.id` → `GITHUB_ENV.PREV_RUN_ID`
      → `actions/download-artifact@v4`（**必须带 `github-token` + `run-id`**）到 `preview_assets/`。
      **查不到可复用产物 → 回退为正常打包**。
    - → **每次运行都会有 Artifact**，不再有「空跑」概念。
  - **⚠️ 顺序铁律**：复用分支必须 **先下载 → 再删旧 Artifact → 最后上传**。
  - **门控**：`解析版本号` / `删除上一份预览产物` / `上传预览产物` / `写入构建摘要` **无门控**
    （两分支都跑）；`准备上传文件` **仅打包分支**（复用分支的文件已由 download 放好，勿清除）。
  - **清理（无门控，每次跑）**：①按 `name` 删同名旧 Artifact（只留最新一份）；
    ②**删「上次未真正打包」的 run 记录**——判据 =
    `gh api .../runs/{id}/jobs --jq '.jobs[].steps[]|select(.name=="Nuitka 独立打包")|.conclusion'`
    为 `skipped`（复用型 run）；`success` 的保留。全程 `continue-on-error` 静默容错。
  - **删 run 的硬限制**：DELETE 只对 **completed** 的 run 生效，**运行中的 run 删不掉自己**
    → 所有「删记录」都只能删**历史** run（`SELF_RUN_ID` 必须排除当前这次）。
  - 版本号 = 运行时间 `UTC-yyyyMMdd-HHmm`，主程序 exe 与 AppName 均为 `F HamLog 2 Preview`
    （独立 AppId `{2AF71D4C-...}`，可与正式版共存）；**不建 Release、不回写分支**。
- **`workflow_dispatch`（手动按钮）与 `schedule`（定时）只认默认分支上的工作流定义**。
  默认分支 = `main`。故 `preview.yml` 必须存在于 `main` 才会出现 "Run workflow" 按钮、
  定时才会生效（曾因只在 `develop` 而「无法手动运行」）。
- 本机 **无 `gh` CLI、无 GitHub token**（凭据由 `git-credential-manager` 托管）→
  查 run 状态 / 删 run 只能在 Actions 页面或 CI 内用 `GITHUB_TOKEN` 做。
- **Release 说明留空、由作者手填**：`gh release create <tag>` **不传** `--title/--notes/--generate-notes`；
  已存在只 `gh release upload --clobber`，**不 edit**（幂等可重跑）。
- **安装位置**：`.iss` 用 `DefaultDirName={autopf}\{#MyAppName}` + **显式 `PrivilegesRequired=admin`**
  （`{autopf}` 只在管理员模式才解析为 `C:\Program Files`；非管理员模式会变 `%LOCALAPPDATA%\Programs`）。
  正式版 → `C:\Program Files\F HamLog 2`，预览版 → `C:\Program Files\F HamLog 2 Preview`，两者同级并存。
  **`%TEMP%\is-*.tmp` 是 Inno 的正常暂存目录，不是安装位置**（用户曾误认为"装到 temp"）。
- **改脚本必记的坑、缓存策略、回写分支的 git 序列、本地验证方法与 `.iss` 约定**见 `DETAILS.md`。
