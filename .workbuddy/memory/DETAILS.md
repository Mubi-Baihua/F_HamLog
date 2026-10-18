# F HamLog 细节档案

> 由 MEMORY.md 分流出来的、可从代码复现的描述性细节。改协议/算法前先看这里。

## 主题系统（theme.py）
- 基线 = `6d48024`（2026-09-27 回退）：`_adopt_platform_palette()` 在目标明暗与平台调色板一致时
  **直接采用平台给的调色板**，不再自建兜底色。手动深色与系统深色因此是同一套原生色
  （Win11 深 `#1e1e1e`/浅 `#f3f3f3`）。
- 被否决的旧方案（勿再走）：`5e9fcbe` 的「深浅一律自建调色板 `#353535/#252525` + 全局
  `app.setStyleSheet` 覆盖输入控件」；`Fusion` 样式（用户：「太丑了」）。
- 取色 API：`hint_css()/warn_css()/link_css()`、`hint_color()/warn_color()/link_color()`、
  `subtle_bg()`、`border_color()`、`is_dark(widget)`；长期窗口用 `theme.watch_theme(控件, 回调)`。
- `theme_mode` 存 `m_xml.txt`，「设置」下拉即改即生效并落盘。
- 坑：① 控件 QSS 的 `background-color` 会**反写进该控件调色板**，取色要用未被染色的父/兄弟控件；
  ② **`app.palette()` 的拷贝不能直接 `setPalette`**（Qt 视为未变忽略），必须手工 `QPalette()` 补全；
  ③ **验证颜色生效必须看渲染像素**（`widget.grab().toImage().pixelColor(...)`），不能只读 `palette()`
  ——`windows11` 样式会给 `QLineEdit` 等硬绘白底、无视 `Base` 角色；
  ④ `theme._diag()` 诊断日志是 opt-in：`touch file/theme_debug.log` 开启，删掉即关闭。
- 注意：基线平台调色板的 `AlternateBase` 在 windows11 深色下给纯白，仅影响用了
  `setAlternatingRowColors` 的 `tle_source_window` 列表；主日志表格未用，无影响。

## 文件对话框
- 定稿：**一律原生**——调用处直接静态调 `QFileDialog.getOpenFileName/getOpenFileNames/getSaveFileName`
  （共 16 处）；`dialog_defaults.py` 只提供 `desktop_dir()`（默认打开=桌面）。
- 中文由系统给、深浅色跟随系统。**已被用户否决、勿再走**：Qt 自绘 + 汉化 + 补词条
  （自绘丢了原生对话框的中文、快速访问/OneDrive 侧栏、缩略图）。本机 Qt 6.11 根本不产出
  Win32 `#32770`，「原生 + DWM」是 no-op；Qt 自绘默认英文，必须 `installTranslator`。

## 主界面与文件结构
- `main.py` → `project.py`（主日志窗）；`batch_project.py` 批量、`set.py` 设置、
  `export_adi/output_adi/output_excel/input_*` 导入导出、`fhl_rw.py` 持久化。
- 内存日志 `file` = list[dict]，字段：date/time/m_call/o_call/freq(上行)/freq_rx(下行)/mode/
  prop_mode/sat_name/m_rst/o_rst/m_qth/o_qth/m_dig/o_dig/m_ant/o_ant/m_pow/o_pow/notes。
  **无 `record`**（通联录音已删）。主页表格 **14 列**，末列「更多」。
- `.fhl` = utf-8 JSON，可选 AES-GCM。设置 `file/m_xml.txt` 是 `eval` 的 dict，**一律 `.get` 读**。
- 不纳入主题化（勿误改）：`#remote_project.py`（历史备份、无引用）、
  `F_HamLog_Remote_Log_Server_2.0.0/main.py`（独立服务端，改后须重打包）。

## .fhla 扩展格式（2026-10-16）——**已内嵌进 `project.py`**（原独立模块 `fhla_rw.py`）

- **2026-10-16 晚：实现从 `fhla_rw.py` 整体搬进 `project.py`**（文件已删）。接口名一律没变，
  只是命名空间从 `fhla_rw.*` 变成 `project.*`：`read_project_file` / `save_project_file` /
  `is_fhla_path` / `write_fhla_file` / `read_fhla_file` / `describe_meta` / `normalize_meta` /
  `empty_meta` / `current_editor` / `current_version` / `fhla_project` / `detect_encrypted` /
  `standard_field_labels`。位置 = `FIELD_LABELS` 定义之后、`file/key` 全局之前（紧挨着它依赖的常量）。
  **`standard_field_labels()` 现在直接 `dict(FIELD_LABELS)`**（同文件，循环依赖不复存在）。
  `current_editor()` 里的 `app_path` 已在 `project.py` 顶部导入；`now_str()` 用本文件的 `time_` 别名。
  自检入口由 `python -m f_hamlog.fhla_rw` 改为 `project._fhla_selftest()`（**不带 `__main__` 守卫**，
  因为 `project.py` 的 `__main__` 守卫是启动 GUI，不能占用）。
  `main.py` / `batch_project.py` / `input_fhl.py` 三处调用点均已改成 `project.xxx`；后两者用
  **函数内延迟导入**（`project` 本身也以延迟方式引用它们，避免互相 import 时机纠缠）。
  打包注释同步（`pyproject.toml` 的模块清单不再列 `fhla_rw.py`）。

- 磁盘结构：`{"xml": 属性块, "project": 记录列表}`；未加密 = 普通 UTF-8 JSON（indent=4），
  加密 = `fhl_aes`（AES-256-GCM，与 `.fhl` 同一套）。`project` **就是** `.fhl` 的 list[dict]，
  老代码拿到的结构不变。
- 属性块键（顺序固定，未知键保留在末尾，前向兼容）：
  `format="fhla"` / `format_version=1` / `other_item` / `creator` / `last_editor` /
  `created_time` / `last_edit_time` / `last_version` / `encrypted`。
  时间格式 `%Y-%m-%d %H:%M:%S`；`last_version` 取 `f_hamlog.__version__`（**不硬编码**）。
- `other_item` = 自定义记录项目 `{字段键: 显示标签}`（等价于扩展一份 FIELD_LABELS）；
  `fhla_project.field_labels()` = 本文件 `FIELD_LABELS`（同文件直接取）+ 自定义项。
  **标准字段不被它覆盖**；记录里 FIELD_LABELS 之外的键**原样保留**（表格只显示固定 14 列，
  自定义字段留在数据里，往返不丢）。
- `encrypted` 只是**声明**：读取时以「文件字节能否 UTF-8 解出」为**准**（`detect_encrypted`），
  以磁盘实际状态覆盖声明值。加密文件无密钥时 `read_fhla_file(..., ask_key=False)` 返回 `(None, None)`。
- 「创建者」语义 = 第一次落盘的操作者；`mark_created` 幂等（已有创建者不覆盖）。
  **操作者 = 设置里自己填的呼号 `m_call`（大写去空白），没填才用系统用户名**
  （`project.current_editor()` = `my_call()` or `getpass.getuser()`）。
  ⚠️ 读设置一律走 `project.load_settings()`：`utf-8-sig`（**吃 BOM**）+ `ast.literal_eval` → `eval`
  兜底。旧的 `eval(open(..., encoding='utf-8'))` 遇到带 BOM 的设置文件会抛异常被 `except: pass`
  吞掉 → 呼号静默失效、属性里显示系统用户名（2026-10-17 用户报的现象）。
- **「打开即自动保存」不算一次编辑**：`project.main` 记「打开时的内容快照」`_fhla['open_json']`，
  写盘时 `touch=(当前快照 != open_json)` —— 一致则只刷 `last_version` + `encrypted`，
  真改过才算编辑、才刷 `last_editor` / `last_edit_time`。`write_fhla_file(touch=False)` 即该分支。
- 分派：`read_project_file` / `save_project_file` 按扩展名走（`.fhla` 走内嵌实现，其余 `fhl_rw`），
  `read_project_file` 返回三元组 `(records, key, meta)`——**`.fhl` 的 meta 恒为 None**（格式没变）。
- 接入点：`main.py open_project`（过滤器 + 分派 + 传 `fhla_meta`）；`project.py`
  另存为 / 恢复另存 / 导出选中 / 搜索结果导出 / 新建文件对话框（过滤器均含 `*.fhla`）、
  文件菜单「项目属性」（**`Alt+I`**，QMessageBox 展示 `describe_meta` 的行）、
  文件菜单「自定义日志字段」；`batch_project.py`
  的 `save_records_to_path/load_records_from_path` 改为按扩展名分派（返回三元组，回写带 meta）；
  `input_fhl.py`（导入日志吃 `.fhla`）。
- 容错：`project.main` 若收到 `.fhla` 整块 dict（带 `project`/`xml`），自动拆包收下记录+属性；
  否则会当空项目打开、随后自动保存把项目覆盖成空文件。
- **不在写盘时去读目标文件继承属性**：另存到别人建的 `.fhla` 上会抄走对方的创建者身份；
  属性只随「本项目自己的 meta」走。
- 验证：`tests/__fhla_smoke.py`（A 格式层 / B 主窗口 / C 另存为 / D 整块直传 / E 保存格式自选
  + 扩展名补全 / F 数据目录解析 / G 缺文件容错 / H 属性快捷键+自定义字段（含 `.fhl` 拒绝），
  **118 项**，离屏，全过）。
  自定义字段示例用 `wx`（天气）/ `rx_pwr`（接收功率）。词表补 15 条（2 条过滤器 + 13 条属性文案，
  见 `i18n_zh_en.py` 末节）+ 自定义字段一节。

- **「项目属性」快捷键 = `Alt+I`**（2026-10-17 定稿）：`props_action.setShortcut(
  QKeySequence('Alt+I'))`。曾试过 `Alt+Enter`（`Alt+Return` + `Alt+Enter` 两个都挂，因为 Qt 里
  Return（主键盘）与 Enter（小键盘区）不等价），**用户改用 `Alt+I` 后只剩一把键，不再需要双挂**。
  `Ctrl+I` 让给「反选」（主窗口/搜索窗口的选择菜单本来也用 `Ctrl+I`，之前是重复占用）。
  ⚠️ **描述按键一律写 `Return` / `Enter`，不写「回车」**（用户 2026-10-16 明确要求）。
  **`.fhl` 项目直接提示「不支持的格式」**（不再展示内存状态 + 提示保存为 .fhla）：
  `.fhl` 没有属性块，半展示会让人把内存状态当成文件属性。文案**逐段 `i18n.tr` 后再拼**。

- **自定义日志字段（other_item）的界面**（2026-10-16 追加）：
  - 「文件 → 自定义日志字段」= `project.manage_custom_fields()`：QTableWidget 两列
    （字段键 / 显示名称）内联编辑，「添加字段」= **插入空行直接编辑**（与 TLE 数据源窗口同一风格），
    「删除选中」按选中行倒序删，「保存更改」整体替换。
  - 字段键校验：`^[A-Za-z_][A-Za-z0-9_]*$`（要写进记录 JSON 当键）、不与 `FIELD_LABELS` 重名、
    不重复、显示名称非空；任一不合格 → `QMessageBox.warning` + **整体放弃**（不写盘）。
    整行空白（点了添加又没填）→ 静默忽略。
  - `project.custom_fields()` / `set_custom_fields(fields)`（`main()` 内闭包，另暴露在 `_perf_api`）：
    改完**立即落盘**（经 `_write_project_file`，顺带刷属性），因为属性只存在 `.fhla` 里。
  - **`.fhl` = 不受支持的格式，自定义字段一律不给**（2026-10-16 用户定稿，取消早先的「内存生效」半支持）：
    ① `manage_custom_fields()` 开头 `if not is_fhla_path(save_path)` → `QMessageBox.information`
    提示「不支持的格式」（与「项目属性」同一套口径，三段文案逐段 `i18n.tr` 后再拼）并 `return`，
    **不建窗口**；② `custom_fields()` 加同样的格式闸（`meta is None or not is_fhla_path(save_path)`
    → `{}`），否则「另存为 .fhl」之后录入窗口还会冒出一批无处保存的字段行；
    ③ 由此 **`.fhl` 下「新建日志 / 更多信息」恒为标准 20 行**。原有的「只在本次会话有效」提示
    QLabel 与 `.fhl` 分支 toast 一并删除，对应词表键也删（别再写回半支持）。
  - `_fhla['dirty']`：**属性块被用户改过**的标记。记录快照 `open_json` 只看记录，
    改字段定义不碰记录 → 必须单独记一笔，否则 `touch` 判不出版本/编辑时间该不该刷。
  - 「新建日志 / 更多信息」两个窗口：行顺序常量 `DIALOG_FIELDS`（20 行，取自 FIELD_LABELS，
    **顺序与旧版逐项一致**——行 2/3 挂呼号大写委托，自定义字段一律**追加在末尾**，不动行号）。
    自定义值留空 → `write_back_field(..., is_custom=True)` **把该键整个移除**（不往记录里塞空字段）；
    写入用 `cell_text(v)`（缺字段/None → 空串，避免 `str(None)='None'` 或直接 KeyError）。
  - `i18n.bind_cell_texts` 的文本序列要 **标准标签 + 自定义标签** 一起给（自定义标签是用户数据，
    翻不到就原样，正好）。
  - ⚠️ **批量记录窗口（`batch_project.py`）没接自定义字段**：它的 `translation_dict`/`KEYS` 是
    模块级全局（冻结列、i18n、写回都按 `KEYS` 索引行），且该窗口可以从主界面单独打开、
    **没有项目上下文**（可能没有 meta）。要接得先把 `KEYS` 变成"每窗口一份"，属单独改动。
- **保存时由用户当场选格式**（2026-10-16 加、2026-10-17 改默认）：
  `project.project_save_filters()` 返回**两条**过滤器，**顺序即默认**：
  第一条 `F HamLog A 项目 (*.fhla)`（**默认**，带宽属性），第二条 `F HamLog项目 (*.fhl)`
  （纯记录）；**逐段 i18n.tr 后再拼**。
  `project.complete_project_suffix(path, sel)` 按所选过滤器补扩展名
  （Qt 静态保存对话框**不会**替用户补后缀；已有 .fhl/.fhla 时原样返回）；
  **`sel` 为空也默认补 `.fhla`**，只有明确选了纯 .fhl 那条才补 `.fhl`。
  ⚠️ 判 `sel` 时注意：`'*.fhl'` 是 `'*.fhla'` 的前缀，必须先判 `.fhla` 再判 `.fhl`。
  ⚠️ 合并成一条 `(*.fhl *.fhla)` 时用户拿不到格式选择权，且输入不带扩展名的名字会落盘成
  **无扩展名文件**，再打开按 .fhl 处理、属性全丢 —— 所以必须两条。
  改动 5 处保存对话框：另存为 / 恢复另存 / 导出选中 / 导出搜索结果 / 新建文件；
  `batch_project` 的「另存为 F HamLog项目」同样两条。恢复另存的默认文件名已改 `恢复的项目.fhla`。
  **「打开」类对话框仍用合并的一条**（一次就能看到两种文件，更好用）。

### 显示名与迁移（2026-10-17 定稿）

- **显示名**（`project.py` 常量，所有过滤器都引用它们，别再写字符串字面量）：
  `SAVE_FILTER_FHLA = 'F HamLog 项目 (*.fhla)'`、`SAVE_FILTER_FHL = 'F HamLog 兼容项目 (*.fhl)'`、
  `OPEN_FILTER_BOTH = 'F HamLog 项目 (*.fhla *.fhl)'`（打开类对话框合并用）、
  `OPEN_FILTER_BOTH_ALL`（同上 + `;;All Files (*)`）。
  历史名「F HamLog A 项目」「F HamLog项目（带属性）」**已作废**，词表同步替换。
  菜单动作名「另存为 / 添加到 F HamLog项目」**不改**（那是动作不是格式名）。
- **打开 .fhl 的迁移提示**（`project.py` 三件套 + `main.open_project` 调用）：
  `fhla_sibling_path()`（`c.fhl` → `c.fhla`）、`migrate_fhl_to_fhla()`（写同名 .fhla，返回
  `(路径, 属性块)`，失败返回 `(None, None)`）、`ask_migrate_fhl()`（两个按钮「迁移 / 保持原样」，
  默认迁移、Esc = 保持原样；同名 .fhla 存在时在**同一个**提示里说明会覆盖，不再单独弹覆盖确认）、
  `offer_migration(parent, path, records, key, meta)`（一站式：问 → 迁移 → 返回实际打开路径与属性块）。
- 迁移语义：**写同名 .fhla → 读回来校验条数 → 删除原 .fhl**（2026-10-17 用户改为「自动删源文件」，
  之前是「原件保留」）；校验不过就不删、只提示「原 .fhl 已保留」。
  `key` 沿用 → 加密 .fhl 迁移后仍是加密 .fhla；创建者 = 本次操作者；迁移算一次编辑。
- **每次打开都问**，不做「不再提示」记忆、不加设置开关（用户明确要求「每次」）。
  **默认日志 `file/main.fhl` 也问**：`main.default_quick_project_path()` 优先 `file/main.fhla`
  → 迁移删掉 `main.fhl` 后，下次启动自然打开 `main.fhla`（全新安装时直接给 `.fhla` 路径）。
- 迁移失败**不中断打开**：提示「迁移失败」后照常打开原 .fhl。

## 日志字段定义：顺序 / 必填 / 主页显示（2026-10-17）

属性块新增两个**可选**键（用户没调整过就不写）：

```json
"field_order": ["date", "time", "m_call", "…", "wx", "接收功率"],
"field_meta": {"接收功率": {"required": true, "main": true}}
```

- `other_item` 仍是「键 → 显示名称」表；**新字段的键 = 首次创建时的名称**（撞名追加 `_2`，
  见 `make_field_key`）。改名只改名称，**记录里的键不动** → 改名不丢数据，也不会迁移旧值。
- `STANDARD_REQUIRED_KEYS = (date, time, m_call, o_call, freq, mode, m_rst, o_rst)`、
  `MAIN_DEFAULT_KEYS = 12 个历史列`：这是**默认值**，不是约束 —— 标准字段的 required / main
  在管理窗口里同样可改（2026-10-17 用户：「不管是什么都改」）。`field_meta` 里**只记偏离默认的键**，
  改回默认 = 删掉覆盖项；`normalize_field_meta` 因此「只保留写了的项」，不能补 False。
- 顺序是**一张总表**：标准 20 行 + 自定义字段混排 → 「新建日志 / 更多信息」的行序，
  **主页列序也用它**（2026-10-17 定稿：两边顺序一致，排一次两边都走）。因此**呼号大写委托
  必须按 key 找行号**（`keys_list.index('m_call')`），不能再写死行 2 / 3。
- 主页表格：`_main_cols()` 遍历 `field_entries()` 只取 main=True，「选择」45 恒首列、「更多」80
  恒末列；列宽走 `MAIN_COL_WIDTHS` / `CUSTOM_COL_WIDTH(110)` / `EXTRA_COL_WIDTH(90)`。
  默认列序下 传播模式 / 卫星名称 排在 调制模式 之前（跟录入窗口一致）。
- GUI：`manage_custom_fields()`（照 `DictEditorDialog` 版式：说明 + 表格 + 添加/删除/上移/下移/
  **恢复默认** /保存更改/关闭）。标准行名称 `Qt.ItemIsEditable` 关掉 + `theme.hint_color()` 灰显；
  删除标准行直接拒绝。`api` 暴露 `field_entries` / `custom_main_fields` / `set_field_defs` / `main_table`。
- **「恢复默认」`reset_defaults()`**：清表后按 `fields_from_meta(None)` 重填（20 标准行、历史顺序、
  默认勾选、无自定义字段）。**只改表格不落盘**，点「保存更改」才生效（一键抹掉全部字段定义太重，
  不做「点一下就写文件」）。`fields_to_meta()` 在顺序 == `standard_field_keys()` 时整个省掉
  `field_order` → 恢复默认后 xml 回到出厂状态（`other_item` 空、无 `field_order` / `field_meta`）。
- 管理窗口 620×560；名称列 `QHeaderView.Stretch`，勾选列固定 70 / 100（窗口变宽不留右侧空白）。
- `.fhl`：`field_entries()` 只返回标准 20 行（历史顺序），`custom_fields()` 恒空。

## 数据目录解析（paths.py）与「假 file/」劫持（2026-10-16 崩溃复盘）

- **症状**：主窗打不开。点「通联日志」→ `FileNotFoundError: <仓库根>\file\main.fhl`；
  新建项目 → `<仓库根>\file\pack_list.txt` 同样找不到（两个都指向**仓库根**而非 `src/f_hamlog`）。
- **根因链**：`backup.py` 的 `PROJECT_BACKUP/BATCH_BACKUP` 原本是 **cwd 相对**路径
  `file/project_backup.fhl`。在仓库根（或任何别的目录）跑一次应用、触发一次自动备份，
  就 `makedirs('file')` **凭空造出一个空的假 `file/`**。而 `paths._app_base_dir()` 的候选顺序
  是「cwd → exe 目录 → 模块目录」，**只要 cwd 下有 `file/` 就认**，于是此后从仓库根启动
  DATA_DIR 恒为仓库根，`file/` 里的真数据文件集体找不到。← 一次误写，永久生效。
- **修复（两处，缺一不可）**：
  1) **不再往 cwd 相对路径写任何数据**：`backup.py` 改 `app_path('file/...')` 绝对路径；
     `batch_project.add_to_default_log` 的 `os.path.join('file','main.fhl')` 同样改 `app_path`
     （它会把批量记录**写进错目录的 main.fhl**，属数据正确性问题）；
     `i18n.settings_path` / `theme.settings_path` 的兜底也改 `paths.app_path`（原来兜底是
     cwd 相对路径，同样能造出假 `file/`）。
  2) `paths._app_base_dir()` 加**身份标记** `_DATA_MARKERS = ('m_xml.txt', 'main.fhl',
     'amateur.tle', 'pack_list.txt')`：先在「`file/` 里至少有一个标记文件」的候选里挑，
     一个都不满足才退回旧的「有 `file/` 就认」（保留历史行为）。假 `file/`（只有
     `project_backup.fhl`）因此被挡掉。
- 容错：`project.main` 读 `file/pack_list.txt` 加 try/except（缺失/内容坏 → 按「无插件」）；
  `main.load_quick_project_data(path)`（新抽出的函数）在 `file/main.fhl` 不存在时返回 `([], None)`
  → 按空项目打开、首次保存时创建，不再抛 FileNotFoundError。
- **第二次加固（同日 23:25 复发）：候选顺序改成「exe 目录 → 模块目录 → cwd」，cwd 垫底。**
  复发经过：跑了一个「src 布局迁移前」的遗留测试（`tests/__req3_smoke.py`，它按**相对路径**
  写 `file/m_xml.txt`、`file/amateur.tle`），那个假 `file/` **长出了标记文件**，于是标记法失效、
  又被当成数据目录 → `list_time` 读到 `{'m_call': 'BA1ABC', ...}` 缺 `aouto_list` → KeyError。
  **教训：标记文件挡不住「会写标记的邻居」，可信来源只能是应用自己的目录**；
  要指定数据目录请用 `F_HAMLOG_DATA_DIR`（测试也可 monkeypatch `sp.SETTINGS_PATH` 等常量）。
  实测：从仓库根 / `src/f_hamlog` / 用户主目录启动，DATA_DIR 均为 `src/f_hamlog`；env 覆盖仍生效。
- **本机残留**：`D:\F-Dev\BIG\F_HamLog\file\`（2026-10-16 23:00 由该 bug 生成 + 23:25 被遗留测试
  写入 mock 数据）已于 23:28 **整个移到** `%TEMP%\fhl_stray_file_backup_20261016_232848\`
  （move 即备份，无删除；仓库根干净了）。里面只有：0 字节 `project_backup.fhl`、
  mock `m_xml.txt`（BA1ABC）、mock `amateur.tle`（MOCK-SAT-B），**不含真实用户数据**。
- 回归：`tests/__fhla_smoke.py` F 段（子进程分别以**仓库根**、一个**合成假 file/**、
  一个**带标记的合成假 file/** 为 cwd 回显 `paths.DATA_DIR`，须等于 `src/f_hamlog`）
  + G 段（缺 main.fhl / pack_list.txt 的容错）。

## 包结构：开发安装与「直跑」（2026-10-06 定稿）
- **定稿：开发环境用 `pip install -e .`，模块里不加任何 sys.path 守卫。** 2026-10-05 加过的
  23 处守卫已于 10-06 **全部撤销**（`git checkout`），只留 `__main__.py` 自身那一处——
  Nuitka 打包是 `--main=src/f_hamlog/__main__.py`，本身就是直跑路径。下方「守卫方案」保留为历史记录，**勿再照做**。
- 症状：`python src/f_hamlog/backup.py` → `ModuleNotFoundError: No module named 'f_hamlog'`。
  根因 = src 布局下**直跑文件时 `sys.path[0]` 是 `src/f_hamlog/`**，包本身不在 `sys.path` 上；
  `python -m f_hamlog`、打包后的 exe、`python src/f_hamlog/__main__.py` 都不受影响（后者自带守卫）。
- 历史方案（**已否决，勿再走**）：凡「**任意位置**（含函数体内延迟导入）存在对 `f_hamlog` / `f_hamlog.*` 的绝对导入」的模块，
  在文件顶部 docstring 之后、首个 import 之前插入同款守卫（与 `__main__.py` 一致）::

      # 直跑支持：`python src/f_hamlog/xxx.py`（把 src/ 加入 sys.path；正常导入 / 打包时为无操作）
      if __package__ in (None, ""):
          import os, sys
          sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

  已加 **23 个**：backup / batch_project / export_adi / fhl_rw / fhla_rw /
  （`fhla_rw.py` 已于 2026-10-16 并入 `project.py`，该文件不复存在）i18n / input_HAM_tolls /
  input_adi / input_fhl / main / mutual_window / output_adi / output_excel / pack_set / project /
  remote_server / satellite_auto_update / satellite_map_window / satellite_window / set / theme /
  tle_source_window / toast_tip。`__main__.py` 早有守卫。
- **无需守卫的 9 个叶子模块**：`__init__ / call_upper / data_factory / dialog_defaults / fhl_aes /
  i18n_zh_en / paths / remote_crypto / satellite_pred`（不 import 包内模块，直跑本来就正常）。
- 判定要用 **AST**（`ast.walk` 找 Import/ImportFrom），**别用字符串搜索**：`call_upper.py`、
  `i18n.py`、`toast_tip.py`、`theme.py` 的 docstring 里有 `from f_hamlog import ...` 的**使用示例**。
- 改这批文件时的两个坑：① **沿用文件自身换行风格**（工作区是 CRLF；插入时写 `'\n'` 会造成混合换行，
  虽然 git blob 是 LF、`git diff` 只显示新增行，但工作区得干净）；② `fhla_rw.py` 曾残留旧式
  `import fhl_rw`（平级导入，直跑时能过、被 import 时反而炸）→ 已统一为 `from f_hamlog import fhl_rw`。
- **定稿做法（2026-10-06）**：`pip install -e . --no-deps` → pip 26 生成的
  `__editable__.f_hamlog-<ver>.pth` **内容只有一行 `D:\F-Dev\BIG\F_HamLog\src`**
  （path-based，无 import hook）≡ 把 `src` 持久化进该 venv 的 `sys.path`（等价 `PYTHONPATH=src`）。
  只对该 venv 生效 → **换 venv / 换机器 / 别人 clone 之后必须重装一次**（README 已写明「从源码运行」）。
  会在源码树留 `src/f_hamlog.egg-info/`（已加进 `.gitignore`）；项目 venv 无 setuptools →
  需联网（build isolation）或先装 `setuptools wheel` 再 `--no-build-isolation`。
- `pyproject.toml` 打包配置**显式声明**（不再 `packages.find`）：`packages = ["f_hamlog"]`
  + `[tool.setuptools.package-data]` 白名单（F_HamLog.ico / amateur.tle / sat_radio_dict.txt /
  tqsl_dict.txt / world_land.json / python-3.13.11-amd64.exe）。**刻意排除**个人与运行时数据：
  m_xml.txt、main.fhl 与 *_backup.fhl、keys/、known_server_keys.txt、remote_rooms/、pack_list.txt、
  sat_map_markers.txt、tle_sources.txt。**新增子包**（带 `__init__.py` 的目录）时要在 `packages` 里补一项；
  包内 .py 模块无需登记，随包自动包含。配置里另附一份模块清单注释（备查阅）。
- 校验口径（2026-10-06）：`pip wheel` 产物含 **33 个模块 + 6 个资源**；`pip install -e .` 后
  直跑 `backup/theme/i18n` 退出码 0、任意 cwd `import f_hamlog` 成功；包内除 `__main__.py` 外
  已无 `__package__ in (None, "")`；全部模块 `py_compile` 通过。

## 设置键（file/m_xml.txt）
m_call / m_qth / m_dig / aouto_save / aouto_list / m_lat / m_lon / m_alt /
sat_auto_update / sat_update_hours(1–168) / sat_last_update / sat_b_lat / sat_b_lon / sat_b_alt /
sat_mu_el_a / sat_mu_el_b / sat_mu_dur / sat_mu_filter / sat_mu_sats / sat_map_hours(1~24 默认 3) /
sat_dur(1~240) / sat_sats / mu_sats / **theme_mode**。
**星历数据源不在其中**（独立文件 `file/tle_sources.txt`）。

## 卫星模块 API
- `satellite_pred.py` 用 `skyfield`+`numpy` 做全部天文计算（SGP4、仰角/方位、过境），离线 `load.timescale(builtin=True)`。
- `twoline2rv` 返回包装 `EarthSatellite` 的 `Satrec`，含 `.name/.satnum/._earth_sat`；另有 `observe`、`subpoint`（→lat/lon/alt）、`ground_track`（批量星下点+台站仰角）、`predict_passes`（find_events 求 AOS/MAX/LOS，`duration_sec` 秒级）、`fetch_amateur_tle`、`parse_tle_text`、`SATE_BANDS`、`app_path(rel)`。
- `satellite_window.py`：过境预测 GUI，由 `project.py`「卫星」菜单或 `main.py`「卫星过境」按钮打开；每行「记录」按钮经 `quick_log_callback`→`project.new` 预填；工具栏「编辑转发器」(`sat_radio_dict.txt`)/「TQSL映射」(`tqsl_dict.txt`)/「星历自动更新」复选框。
- `satellite_auto_update.py`：`main.py` 启动时 `AutoTleUpdater(window).start()` 常驻，QTimer 每小时巡检 `should_update_now()`，到间隔由后台线程 `_FetchThread` 调 `fetch_amateur_tle(force=True)` 刷新 `file/amateur.tle`。
- 星历数据源（TLE 下载来源）：独立文件 `file/tle_sources.txt`（`TLE_SOURCES_PATH`，每行一个地址、`#` 注释），独立窗口 `tle_source_window.py`（`main(window=None, on_save=None)`；列表双击就地编辑、非法/重复地址回滚、改动即时落盘）。`parse_tle_sources_text`/`load_tle_source_file`/`save_tle_sources`/`drop_legacy_tle_sources`/`is_valid_tle_source` 均在 `satellite_pred.py`；`load_tle_sources()` 读取顺序 = 独立文件 → 旧设置键 `sat_tle_sources`（`m_xml.txt`，仅兼容读）→ `DEFAULT_TLE_SOURCES`。`fetch_amateur_tle(sources=[...])` 按序下载，同编号取靠前源。
  - **决策要点（已定稿，别再改回去）**：「添加」= 直接插入空行并进入**内联编辑**（不弹 `QInputDialog`），
    已有空行时只聚焦、不重复创建；启用/禁用**写在同一个文件**（地址前加 `#` 即禁用），
    **全部被禁用时返回空列表**（不偷偷回落到默认源）。
  - **数据源一视同仁，无 URL 特判**（celestrak 也只是普通条目）；**延迟探测自动进行**
    （打开窗口 / 改完 / 新增 / 恢复默认都自动测），**没有「测试延迟」按钮**；
    延迟结果只存进 `_ROLE_DELAY` 供 delegate 自绘，**绝不写进 `item.text()`**。
  - 默认源顺序（越靠前优先级越高）：live.ariss.org/iss.txt → r4uab.ru/satonline.txt →
    amsat.org/tle/current/nasabare.txt → celestrak.org/…GROUP=active&FORMAT=csv → db.satnogs.org/api/tle/?format=3le。
  - 下载/导入一律**按 NORAD 编号增量更新**：同编号替换、新编号追加、**旧的一律保留**。
  - `iter_tle_records()` 兼容 **3LE / 2LE / Celestrak OMM CSV**（CSV 按列**重建** TLE 两行）。
- 通联预测算法：`visibility_windows()`（按最低仰角的连续可见窗口）+ `predict_mutual_passes()`（两站窗口交集，交集内采样得两站最大仰角/方位/最佳时刻）+ `great_circle_km()`。
- 地图：`open_map(parent, sats, home, station_b, selected_name, source, min_elev=0.0)`；纯 QPainter 等距圆柱投影（不引 matplotlib）；陆地 `file/world_land.json`；海洋/陆地/网格缓存成 QPixmap，动态层（轨迹/当前位置/覆盖区/台站/图例）每帧叠加。已修：多圈轨迹重合、南极洲接缝、极地覆盖区绘制。
- **地图与来源单向同步**（地图窗改参数不回写来源窗），`sat_map_hours`（1~24，默认 3）与 `sat_dur` 独立落盘并广播；画布已主题化（深浅两套）。
- 打包：**必带 `--include-package-data=skyfield` + `--include-data-dir=file=file`**；所有数据路径走 `satellite_pred.app_path()`（否则打包后找不到 TLE/字典/地图数据）。
- 入口：`project.py`「卫星」菜单 →「通联预测」(Ctrl+Shift+E)；`main.py` 启动器「卫星过境」「通联预测」。
- **卫星名匹配规则两处必须同步改**：① 选择框搜索；② `lookup_transponder()` 第 6 层兜底
  （`normalize_sat_name`/`sat_name_match`/`parse_sat_keywords`）。
- 选择对话框另两条硬约束：**隐藏行必须用 `QListWidget.setRowHidden(row, hide)`**（`setHidden()` 不触发重排）；
  **超限时 `accept()` 不关闭**（`reset_requested=True` + `reject()`，调用方 `while True:` 重开）。

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

## 历史：已移除的功能
- **通联录音**：当前分支（含 `develop`/`develop-English`）**无此功能**，`qso_rec.py` 不存在。
  历史：`f84864f` 加入、`b6a9162` 删除；若需重建，从 `f84864f` 取回再适配当前主表格委托架构。

## 验证环境（离屏 GUI 冒烟）
- venv 已装 PySide6-Essentials+cryptography+skyfield+numpy，可 `QT_QPA_PLATFORM=offscreen` 做真实 GUI 冒烟（建窗/后台线程/读表/点按钮）。
- **`project.py` 主窗口也可以离屏跑**（旧记录的“硬崩溃”不成立，实测 exit 0）：`project.main(QMainWindow(), 数据, 路径, key_=…, recovered=…)` 同步跑完建表 / `table_update` 自动保存 / close guard 关闭分支。做法是 patch 掉全部模态与 IO：`QMessageBox.exec`+`clickedButton`（在 exec 里按按钮文本记下 `_fake_clicked` 再返回）、`QMessageBox.information/warning`、`QFileDialog.getSaveFileName`（返回预定路径并计数）、`fhl_rw.write_fhl_file`（记录 `(path, data)` 以统计落盘次数）。样例见 `test_recover_save_smoke.py`。
  **坑**：槽函数里的 `sys.exit()`（如 `esave`）会从 PySide6 的 C++ 边界直接终止进程，`try/except SystemExit` 与 `finally` 都拦不到 → 测试前临时 `sys.exit = lambda *a, **k: None`（该场景必须用 if/else 分支而非依赖 `sys.exit()` 中断流程）。
- `main/satellite_window/mutual_window/batch_project`、独立服务端 `main.py` 均可正常离屏。
- 测完务必核对并还原 `file/m_xml.txt`（测试脚本可能写入坐标残留）。注意 `m_lat/m_lon=0,0` 时打开卫星窗口会先弹「设置观测站」引导框，抢在待测提示框前面。
- **离屏测「嵌套模态消息框」**（`QMessageBox.exec()` 由 `accept()` 内部弹出）：
  ① 必须显式触发 `QTimer.singleShot(150, dlg.accept)`，否则消息框不出现；
  ② 点击用**独立 `QTimer()` 对象**轮询（`setInterval(50)`+`timeout.connect`），**不要用链式 `singleShot`**（模态嵌套后不再触发→挂死）；
  ③ 找按钮**必须限定 `isinstance(w, QMessageBox) and w.isVisible()`**（`topLevelWidgets()` 会返回主对话框自身，点到隐藏控件不触发槽）；
  ④ 被拦下后对话框**故意保持打开**，测试需再补一次点击（如「取消」）结束 `exec()`；
  ⑤ 抓第二个框要用 `delay_ms` 跳过第一个框；
  ⑥ **标准按钮 `text()` 带助记符**（实测 `'&Yes'`/`'&No'`），按文本 `=='Yes'` **点不到**，必须用 `w.button(QMessageBox.StandardButton.Yes)` 按 role 匹配（自定义 `addButton` 的按钮无 `&`，可按文本）；
  ⑦ 测「开窗即弹提示」时 `main()` 里的同步模态会阻塞主线程 → 用 `QTimer.singleShot(80, lambda: main(None))` 延迟触发。见 `test_max_selected_smoke.py`。
- **两进程真机回归**：仓库根 `__mp_host.py`（房主：开房→写端口+指纹→轮询状态）与 `__mp_guest.py`（客户端：等端口→**经 `verify_fingerprint` 走真实核对路径**→加入→经真实表格加记录→轮询）；先跑 host（后台）再跑 guest，读 `__host_log.txt`/`__guest_log.txt`。**单进程无法验证同步**（`project.file` 是模块级全局，两个窗口共用）。

## 独立服务端细节（F_HamLog_Remote_Log_Server_2.0.0）
- 启动即自动创建 `keys/`（当前端口长期密钥 `server_<端口>.fhlkey`）、`main.fhl`（`[]`）、`password_xml.txt`（默认 `000000`）；`_ensure_runtime_files()` 返回失败项文字，由 `__init__` 写进事件日志（只读目录下也能开窗）。分发只需一个 exe。
- `_app_dir()` 的正确解析顺序：① `os.environ['NUITKA_ONEFILE_DIRECTORY']`（引导程序给的 exe 目录）→ ② `sys.argv[0]`、`sys.executable` 的目录 → ③ `__file__` 目录。**不能信 `sys.executable`/`__file__`**：Nuitka onefile 下两者都指向 `%TEMP%\onefile_<PID>_…`（退出即清理），且 `sys.frozen` 不存在（只有 `'__compiled__' in globals()` 为 True）。启动时事件日志打印「数据目录：…」。
- `main.py` **必须自己 `import remote_crypto`**（曾漏，导致密钥创建被静默跳过）。
- 该 exe 带 `--windows-uac-admin`：非提权进程启动会 `WinError 740`；要端到端验证就另打一个**去掉 uac-admin** 的临时测试包（不覆盖 `dist/` 正式产物）。
- 客户端「多人日志管理」窗：可最小化的非模态 `QDialog`（`project.open_multiplayer_manager`，640×640），`window._mp_dialog` 单例复用。

## 发布流程细节（GitHub Actions）
- 仓库 `github.com/Mubi-Baihua/F_HamLog`，**默认分支 `main`**。
- **只有三个文件**：`main.yml`（手动发布，**唯一能发 Release**，填 `version`）、
  `preview.yml`（cron `0 20 * * *` 定时预览打包→Artifact，**无 push**）、
  `.github/inno/F HamLog 2.iss`（CI 专用 Inno 脚本）。
  **没有** `releases.yml` / `preview-cleanup.yml`（已被否）。
- **产物保存位置（回写分支用）**：安装包 → `F HamLog 2 Inno Setup/F HamLog <display> setup.exe`；
  兼容版 → `兼容版/F HamLog <display>兼容版.zip`。提交信息 `打包 <version> [skip ci]`。
  ⚠️ **历史产物在 `main` 上直接躺仓库根**（`F HamLog 2.4兼容版.zip`，无 `兼容版/` 目录，
  该目录只在 `develop`）→ **取产物脚本必须双位置回退**（先 `兼容版/` 再仓库根）。
- **`main.yml`** 手动 `workflow_dispatch`，一次跑完：Nuitka 打包 → Inno 6 安装包 → 兼容版 zip
  → **回写运行分支** → 发 Releases（**默认草稿**）。
- **`preview.yml`（2026-09-27 定稿）** = `schedule: cron '0 20 * * *'`（北京 04:00）+ `workflow_dispatch`，
  **无 push**；`concurrency: preview` 且 `cancel-in-progress: false`；提交检测**只看 `develop`**
  （比本工作流上条 run 的 `createdAt` 之后 `origin/develop` 的提交数）。
  两条分支：`SHOULD_BUILD=true` 正常打包；`=false` **下载上次 Artifact 当本次产物**
  （download → 删旧 Artifact → 上传；查不到可复用则回退正常打包）→ **每次运行都有 Artifact**。
  清理（无门控）：① 按 `name` 删同名旧 Artifact 只留最新；② 删「上次未真正打包」的 run
  （判 `Nuitka 独立打包` step conclusion=`skipped`，`success` 保留），全程 `continue-on-error`；
  DELETE 只对 **completed** run 生效且**必须排除 `SELF_RUN_ID`**。
  版本号 = `UTC-yyyyMMdd-HHmm`；AppName/主程序 exe = `F Ham Log 2 Preview`（AppId 独立 GUID，
  可与正式版共存）；**不建 Release、不回写分支**。
  ⚠️ `workflow_dispatch`/`schedule` **只认默认分支上的工作流** → `preview.yml` 必须存在于 `main`。
- 本机**无 `gh` CLI、无 token**（凭据由 `git-credential-manager` 托管）→ 查/删 run 只能在 CI 内用 `GITHUB_TOKEN`。
- 命名推导（`-replace '\.0$',''` 得 display）：安装包 `F HamLog 2.4 setup.exe`、兼容版
  `F HamLog 2.4兼容版.zip`；Release 附件沿用点号 `F.HamLog.2.4.setup.exe` / `F.HamLog.2.4.zip`，
  外加仓库内已打包的 `F_HamLog_Remote_Log_Server_2.0.0.exe`（不重打包）。安装包内部 AppVersion 用完整版本。
- `.iss`：AppId 与本地一致故升级关系不变（正式版默认 GUID `{{9C87FCB8-…}`）；路径走 `RepoRoot`，
  Version/包名/ExeName/**AppName**/**AppId** 由 `/D` 注入；`.github/inno/ChineseSimplified.isl`
  内置中文语言文件（运行器 Inno 6.7.1 不带非官方中文包），`.gitattributes` 锁 CRLF。
  - `MyAppName` 可注入的写法：`#ifdef MyAppName` → `#define MyAppNamePreview` 短路，
    再 `#ifndef MyAppNamePreview` 兜底 `#define MyAppName "F HamLog 2"`
    （ISPP 对已定义再 `#ifndef` 会打警告）。
  - `[INI]` 段在 `{app}\file\version.txt` 写版本标识，**必须带 destructive 标志**
    `Flags: uninsdeleteentry createkeyifdoesntexist`——否则 Inno 的 [INI] 是**追加**语义，
    重复安装会把键堆叠多份。见 daily log 2026-09-27「续15」的实测。
- 缓存：pip、Nuitka 辅助工具、`.venv`（按 `第三方模块.txt` 哈希）、`main.build`（按 `*.py` 哈希）。
- **改脚本必记的坑**：① PowerShell 里紧跟中文的变量必须写 `${var}`（`"$display兼容版"` 会被当成
  一个变量名，值静默变空——已实测）；② `VersionInfo.ProductVersion` 由系统补尾部空格，比较前必须 `.Trim()`；
  ③ `GITHUB_ENV`/摘要用 `[System.IO.File]::AppendAllLines`+`UTF8Encoding($false)`（统一 `shell: pwsh`）；
  ④ 多行文本数组不要 `[string[]]` 强转（会被拼成一行），用 `List[string]` 逐行 `Add`；
  ⑤ 7-Zip 打包 `Push-Location main.dist; 7z a -tzip <dst> *`；
  ⑥ `nuitka.__version__` 在 4.x 已移除，用 `importlib.metadata.version('nuitka')`；
  ⑦ `run:` 双引号串里别写 `${{ }}`，用 `$env:GITHUB_REPOSITORY`/`$env:GITHUB_SHA`。
- **回写分支的 git 序列**（必须 `fetch` + `checkout -B` 让工作区与远程一致，否则非快进推送失败）：
  `git fetch origin $GITHUB_REF_NAME` → `git checkout -B <b> origin/<b>` → 复制产物 →
  `git add -- <仅两个产物路径>` → `git diff --cached --quiet` 判幂等 → `commit` → `push origin HEAD:<b>`。
  bot 身份用 `-c user.name/user.email` 传，不改全局 config。已用临时裸远程演练非快进/幂等/再提交三种情形。
- **本地验证方法**：PyYAML 解析工作流 → 抽 `run` → `[Parser]::ParseFile` 查语法
  （**目标路径必须内联进命令串**：`ParseFile('')` 恒「无错误」→ 假通过）；
  再用桩 `gh.cmd` 前置 `PATH` 演练各步。本机已装 Inno 6.7.3 与 7-Zip。
  本机 PowerShell 工具**无法启动 GUI 安装程序**（小探针包也会超时），GUI 安装验证另想办法。

## 卫星选择对话框：搜索/置顶/超限机制
- `SatelliteSelectDialog` 搜索过滤预计算 `self._norm`，计数显示「匹配 N / 共 M 颗」，全选/全不选**只作用于可见项**；维护 `self._row_names`（行号→卫星名）以便按行号隐藏；过滤后 `scrollToItem(首个匹配项, PositionAtTop)`。**搜索期间被隐藏但已勾选的项，点「确定」仍保留在 `get_selected()`（有意设计）**。
- 未搜索时已选置顶：搜索框为空时 `_filter` 末尾调 `_reorder_pin_selected()` 把已勾选项物理重排到顶部（已选在前、保持各自原相对顺序）并同步 `_row_names`；`itemChanged`→`_on_item_changed` 勾选一变即重排（新勾选自动跳顶），`self._reordering` 守卫防递归；搜索中不重排。取出 item 用尾部 `takeItem(count-1)`（O(1)/次）而非 `takeItem(0)`（O(N)/次），整体 O(N)，避免数千颗时 O(N²)。
- `clamp_selected_count(n)` → `(保留集合, 裁掉数)`。
- `SatelliteSelectDialog.accept()` 超限不关闭：置 `self.reset_requested=True` + `super().reject()`；两处调用方（`satellite_window`/`mutual_window` 的 `open_select`）用 `while True:` 循环——`Accepted`→裁剪+break；`Rejected && reset_requested`→`selected_names=set()` 后**关窗重开**；否则 return。`_persist()/run_prediction()/推地图` 移出循环只跑一次。**原因**：原地对数千项 `setCheckState` 会逐次触发 `itemChanged`→重排+刷新标签，O(N²) 卡顿。旧的 `_clear_all_selected()` 已删除。
- `m_xml` 中的自选超限不再静默裁剪：两处 `main()` 读 `sat_sats`/`mu_sats` 后先 `clamp_selected_count` 兜底（防卡）并记 `_oversized_from_settings`，`win.show()` 之后弹提示，选清除则 `selected_names.clear()` + `_persist()`。
- 计数标签 = `self._count_base` 缓存基数 + `　已选 N 颗`，超限追加「，超过上限 250 颗」并转红。
- `import_tle()` **不再自动勾选**（保持用户原有勾选），导入结果按 NORAD 编号增量并入并写回星历缓存，同样受上限约束。测试 `test_max_selected_smoke.py`（36 项，含重开循环模拟与 m_xml 超限提示三分支）。

## 主表格性能优化（2026-09-28）——测试钩子与离屏坑
- `project.main` 末尾暴露 `window._perf_api`：`table_update / set_all_rows_checked /
  invert_rows_checked / get_selected_row_indexes / get_selected_records / checked_rows / get_table`。
  离屏脚本用它驱动 main 内部闭包（这些闭包无法从外部直接拿到）。
- **测跑 `project.main` 的脚本必须把 `backup.PROJECT_BACKUP` 重定向到临时目录**
  （`backup.PROJECT_BACKUP = os.path.join(tmpdir,'project_backup.fhl')`），否则会把生成数据
  写进用户真实 `file/project_backup.fhl`（踩过，已 `git checkout --` 还原）。
- 离屏脚本应 `atexit` 还原 `file/m_xml.txt` 并清掉 `*.func_bak` 等临时备份。
- `get_selected_records()` 在未勾选任何行时会弹模态 `QMessageBox.warning` → 离屏脚本会**卡死**；
  测试需临时 monkeypatch `QMessageBox.warning` 为 no-op。
- `project_others()` 打开的「更多信息」窗口在 offscreen 下**可以**驱动：调
  `api['project_others'](row)` → `app.processEvents()` → 从 `app.topLevelWidgets()`
  里按标题 `'更多信息'` 拿到窗口，改 `QTableWidget` 单元格再点「保存更改 / 删除日志」都可行
  （`__delete_select_smoke.py`、`__inplace_edit_smoke.py` 都是这么做的）。
  早前"会阻塞事件循环"的说法不成立，别按它绕过 GUI 断言。
- **输出经管道（`| tail`/`head`）时的 SIGPIPE/SIGTERM 假象**：脚本其实跑完了，
  只是被管道提前关闭杀掉；判定结果请用 `grep` 抓 `RESULT=`/`通过` 行，别只看退出码。

## 大型项目性能（2026-10-18 第二轮）

**度量脚本（tests/，全部离屏、自动还原 `file/m_xml.txt`）**

| 脚本 | 用途 |
|---|---|
| `__perf_long_fhl_bench.py [N]` | 打开 / 重建 / 全选反选 / 就地刷新 / 判脏 / tick / 保存 |
| `__perf_tick_bench.py [N]` | 判脏、定时器、保存、撤销点拷贝的 A/B 对照（新旧版本各跑一次） |
| `__perf_micro_bench.py [N]` | deepcopy vs 浅拷贝 vs json.dumps vs 排序 的裸成本 |
| `__perf_profile_update.py [N]` / `__perf_profile_open.py [N]` | cProfile 火灾图（重建 / 打开） |
| `__inplace_edit_smoke.py` | 就地刷新 / 就地删除 / 撤销 / 判脏 / 文件格式 回归（22 项） |

**A/B 实测**（离屏，同一台机器）

| 操作 | 1 万条 旧→新 | 5 万条 旧→新 |
|---|---|---|
| 打开项目（`main()` 含建表） | 1.51 s → 0.62 s | 8.77 s → 3.20 s |
| `table_update` 整表重建 | 0.60 s → 0.44 s | 3.67 s → 2.80 s |
| 编辑一条（保存更改） | ≈0.73 s → ≈0.02 s | ≈4.4 s → ≈0.05 s |
| 删一条 | ≈0.73 s → 0.014 s | ≈4.4 s → ≈0.02 s |
| 未保存自动备份定时器（每次 tick） | 108 ms → 7 ms | 558 ms → 41 ms |
| `save()` 未变化（跳过写盘） | 54 ms → 15 ms | 288 ms → 166 ms |
| 记一次撤销点 | 129 ms → 7.6 ms | 743 ms → 54 ms |

**做了什么**

1. **内容比较从 JSON 字符串换成值快照**：`_content_snap()` = `[dict(r) for r in file]`，
   基线 `_bk_state['last'/'local']` / `_fhla['open_snap']` / `_last_written['snap']` 都存快照，
   用 `==` 比（C 层深比较、键序无关、脏时立即短路）。恢复项目哨兵值 `''` → `None`。
2. **`snapshot_before` / undo / redo 用逐条浅拷贝**替代 `copy.deepcopy`（值全是不可变标量）。
3. **撤销栈双重限流**：步数 300 + 栈内记录总数 10 万（5 万条项目 300 步曾要 3.6 GB）。
4. **就地刷新一行**（`table_refresh_row`）：改普通字段时只重写该行 14 个单元格；
   **排序键 date/time 变了必须整表重建**（`project_others.save_changes` 负责判断）。
5. **就地删行**（`table_remove_rows`）：≤200 行走 `removeRow`，超过走整表重建。
6. **打开项目只建一次表**：原来 `table_update(delete=False)` + `table_update(scroll_to_bottom=True)`
   连建两遍（1.4 s 里 1.2 s 是这两次建表）。
7. **`_fill_rows` 微优化**：每行先建齐 item 再挂 + 填充期间 `gc.disable()`（+20%），
   `finally` 里按原状态恢复。
8. **远程同步比较**去掉两侧 `json.dumps(sort_keys=True)`，直接 `new_list == file`。

**仍未做（有意的取舍）**：整表重建剩下的成本是 70 万个 `QTableWidgetItem` 构造，
属 QTableWidget 固有；要再快只能换 `QAbstractTableModel + QTableView`，改动面涉及
委托 / 勾选 / 搜索窗 / 复制粘贴，风险远大于收益，暂不碰。

**硬约束**：文件格式（`.fhl` / `.fhla`）**一个字节都没改**——落盘仍走
`write_fhl_file` / `write_fhla_file`，`__inplace_edit_smoke.py` 显式断言 `.fhl` 顶层
仍是记录数组、字段集合不变；`__fhla_smoke.py` 属性块相关 173/174 与改动前完全一致。

## 多语言（i18n）实现细节

文件：`i18n.py`（机制）、`i18n_zh_en.py`（词表 `TRANSLATIONS`，约 600 条）。
思路：**中文是源语言**，不做 `tr()` 侵入式改造，界面文字在**显示时**查词表翻译。

- 三层：词表 dict → `translate_widget()`（识别 QLabel/QAbstractButton/QGroupBox/
  QMenu/QAction/占位符/windowTitle/QComboBox/QListWidget/QTabWidget/QTreeWidget/
  QTableView 横+纵表头）→ `install(app)` 装的 `_LanguageFilter` 事件过滤器
  （`QEvent.Show` 翻顶层窗、`QEvent.LanguageChange` 重译）。
- 模板匹配：值里写 `{}`（如 `'已删除 {} 条日志。': 'Deleted {} log(s).'`），
  把 f-string / `%` 格式化后的动态文案反查模板再翻。模板需中文侧 ≥ `_MIN_TEMPLATE_CJK=2`
  个汉字；按 pattern 长度降序匹配；**占位符捕获到的片段会递归再翻**（`_translate_inner`，
  深度上限 `_MAX_TEMPLATE_DEPTH=4`）——状态栏那种「几段拼起来」的文案靠这个。
  递归**不能**按「是否含汉字」短路：反方向英文→中文时片段是英文，也要再翻。
- `en2zh` 用 `setdefault` 只登记首个译法；`translate()` 幂等，中英来回切能还原。
- Qt 自带翻译：`install`/`set_language` 里 `_apply_qt_translator()` 加载
  `PySide6/translations/qtbase_zh_CN.qm` / `qtbase_en.qm`（先 remove 再 install 并保引用）。
- `_send_language_change(app)` 显式给所有顶层窗 `sendEvent(LanguageChange)`
  （Qt 只在装/卸翻译器时自动派发，且**对象上的过滤器先于 app 上的过滤器**，
  所以 `watch_language` 的回调里先自己 `translate_tree(obj)` 再回调）。
- 持久化：`file/m_xml.txt` 键 `language`，值 `zh`/`en`（`read_settings/save_language/
  load_language`，只改自己这个键）。`LANG_LABELS=(('zh','简体中文'),('en','English'))`
  ——语言名一律用**母语写法**，故意不进词表。
- `install(app)` 调用点：`main.py` / `set.py` / `project.py` / `batch_project.py` /
  `pack_set.py` / `satellite_window.py` / `mutual_window.py` / `satellite_map_window.py` /
  `tle_source_window.py` 的 `__main__`（紧跟 `theme.init_app(app)`）。
- **动态文案漏斗**：卫星过境/通联预测里 `_status_set(text)=status.setText(i18n.tr(text))`；
  `tle_source_window` 的 `_set_status`/`_set_item_delay` 开头 `text = i18n.tr(text)`；
  `project.MoreButtonDelegate.paint` 里 `btn_opt.text = i18n.tr(self._text)`；
  `project._set_title`、批量记录列头、地图信息栏都显式 `i18n.tr(...)`。
- **文件对话框必须调用处翻**：原生静态 `QFileDialog.getOpen/SaveFileName`、
  `getExistingDirectory` 的标题与过滤器不走控件树。
- **整条拼完再翻会漏翻**：多段中文抢同一模板，长的先匹配、把后面的中文吞进 `{}`。
  所以计数标签与状态栏改成**逐段 `i18n.tr` 后再拼**（`satellite_window._refresh_selected_count`、
  `on_done` 的 `obs_info`/`sel_info`）。
- **写在「单元格」里的固定文案**（不是表头）`translate_widget` 翻不到——它只翻 model 表头，
  而主日志表上万单元格逐个扫会拖慢重建。这类用
  `i18n.bind_cell_texts(window, table, texts, col=0)`：按**中文原文**重设 + `watch_language` 跟随，
  中英来回切**幂等还原**。接入点：`project.new()`（新建日志）与 `project.project_others()`
  （更多信息），传 `list(translation_dict.values())`（与行序一致）。**新增同类窗口照此接入。**
- **冻结列（`batch_project.FrozenTableWidget`）x = 竖向表头宽度**，而竖向表头宽度随**行标签
  文字**变化（切语言时 中→英 76→124）。**只在 `resizeEvent` 里重算不够**：窗口够宽时切语言
  不触发 resize，x 停在旧值 → 整列错位正好一个表头宽度。已改为监听
  `verticalHeader().geometriesChanged` / `horizontalHeader().geometriesChanged` /
  `model().headerDataChanged`，**`QTimer.singleShot(0)` 延后一轮**再 `updateFrozenGeometry()`
  （表头宽度要到本轮布局结束才更新，立刻量是旧值），`_frozen_geom_pending` 合并多次请求。
  复现/验证：`test/__batch_frozen_i18n_probe2.py`（窄窗 resize / 宽窗不 resize 两种都要 dx=0）。
- ⚠️ **路径隐患**：`set.py`（13/43/57/77/83 行）与 `project.py`/`batch_project.py` 读设置用的是
  **硬编码相对路径 `file/m_xml.txt`**，**绕过 `theme.settings_path()`（= `sp.SETTINGS_PATH`）**；
  而 `i18n.save_language` 走 `theme.settings_path()`。→ **冒烟只 patch `sp.SETTINGS_PATH` 不够**，
  必须同时 `os.chdir(临时目录)` 或**备份字节后还原**（`file/m_xml.txt` 曾被污染出 `language` 键）。
- 窗口尺寸：`i18n.fit_window(win, base_w, base_h)`（中文严格用基准尺寸＝历史尺寸；
  英文取「基准」与 `minimumSizeHint+24/+8` 的较大者，`setFixedSize`）、
  `i18n.fit_min_width(win, minimum)`（可自由缩放的地图窗只抬最小宽度）。
  **必须在 `show()` 之后调用**——Show 事件才会触发翻译，先量后翻会按中文尺寸定死。
  - `启动器 main.py`：英文下另算按钮宽度（`sizeHint()`）并按需放大 grid 与窗口，
    中文完全不改（575×375、105/220px）。
  - `星历数据源`：中文 660×430，英文按内容放宽（约 830）。
  - `设置 set.py`：中文 770×475；**语言下拉与「保存更改」并作一行**
    （左「语言:」+下拉、中间 `addStretch(1)`、右侧靠边放按钮；冒烟 12 项见
    `test/__set_lang_row_smoke.py`）。**不要**把语言下拉塞进上方那行
    （开关+星历间隔+颜色模式已占满 770px，会挤压控件）。英文约 1059×475。
- 词表工具（`test/`）：
  - `__i18n_extract.py`：AST 抽源码中文字符串 → `__i18n_ui_out.txt`
  - `__i18n_check.py`：查重复键 / 残留 `%` / 词表有源码没有 / 源码未收录
  - `__i18n_apply.py`：幂等批量套用（`add(f, old, new, n)` 逐条校验命中次数）
  - `__i18n_smoke.py`：离屏冒烟（引擎单测 + 9 个窗口三阶段扫描 + 尺寸打印）
  - `__i18n_fit_probe.py`：单窗尺寸/最宽控件探针
- **写这类冒烟脚本的坑**：
  - 静态 `QFileDialog.getOpen/SaveFileName`、`QMessageBox.information/warning/question`
    内部自带模态循环，**替换 `QDialog.exec` 拦不住**，必须替换静态方法本身
    （`project.main` 会在 `save_path==''` 时弹原生「新建文件」→ 直接传一个临时路径跳过）。
  - `os._exit()` 跳过缓冲区 flush → 日志要**逐行写文件并 flush**；
    并挂 `faulthandler.dump_traceback_later(90, exit=True)` 看门狗定位卡点。
  - `satellite_window.main(None)` / `mutual_window.main(None)` **无视传入窗口、自建
    QMainWindow** → 要按「新出现的顶层窗口」定位再扫描。
  - 扫描只统计**可见**控件（未显示的对话框/隐藏标签页由 Show 事件补翻），
    并分别按方向判定：英文阶段找「仍为中文」，切回中文阶段找「仍是英文」（`text in en2zh`）。
  - `test/__theme_mode_smoke.py` 的 `boxes` = 设置窗里**所有** QComboBox 且被当作
    「同一行」控件；新增语言下拉后要改成 `boxes[:1]`（只取颜色模式那个）。

## toast_tip.py 宽度自适应（2026-10-02 定稿）

- `need_w = QFontMetrics.horizontalAdvance(text) + _PAD_X*2 + _SLACK_X`（单行完整显示所需）
  → `w = min(max(need_w, _MIN_W), _max_toast_width())`：**比当前窄就保持当前宽度，
  比当前宽就加宽**；超过上限（`clamp(屏幕宽×0.8, 440, 900)`）才折行。
- 高度 = `label.heightForWidth(w) + _H_EXTRA`（该 API 的高度**含 QSS padding**：
  单行 24 = 文字 12 + 上下 12）。
- **改宽度只改 `toast_tip.py` 顶部常量区**（`_MIN_W`/`_MAX_W`/`_MAX_ABS`/`_SLACK_X`/`_PAD_X`）。
- **别再退回 `label.width()` 口径**：`wordWrap=True` 时它给的是折行后的宽度，
  长文案会被压成窄卡片而不是加宽。

## 多人日志：退出顺序与线程（细节）

- **退出必走 `RemoteConnection.shutdown()`，顺序不可换**：
  ① `sync.stop()` → ② `_close_socket()`（QUIT + shutdown/close）→ ③ `sync.wait(3000)`。
- `_SyncThread.run()` emit「断开」前必须判 `self._running`。
- 服务端启动后禁用密码输入（含显示/隐藏），停止后恢复；
  发送按客户端加锁（`entry['_lock']` + `_send_entry`）。
- 默认端口 8000，被占回退 `port=0`。**Windows 端口探测**：① 绝不设 `SO_REUSEADDR`；
  ② 试探与 holder 用完全相同地址（`0.0.0.0`）；③ **不要用 `connect_ex`**。
- `.gitignore` 必忽略：`file/keys/`、`keys/`、`*.fhlkey`、`file/known_server_keys.txt`、
  `F_HamLog_Remote_Log_Server_2.0.0/{keys/,main.fhl,password_xml.txt}`、`file/_key_backup_*/`。

## 发布流程：`.iss` 与 PowerShell 补充
- `.iss` 用 `DefaultDirName={autopf}\{#MyAppName}` + **显式 `PrivilegesRequired=admin`**。
- **`[Files]` 的 `Source` 必须与 dist 里真实存在的文件一致，否则 ISCC 直接 `Compile aborted`**
  （2026-10-18 事故：默认日志已从 `main.fhl` 改成 `main.fhla`，`.iss` ④ 的种子仍写 `main.fhl`
  → 「Source file ... main.fhl does not exist」，白跑 54 分钟构建才失败）。
  改动 `src/f_hamlog/file/` 里被 `[Files]` 点名的文件后，必须同步 `.iss`。
- **默认日志种子的运行时条件**：④ 的 `main.fhla` 种子带 `Check: NeedSeedMainFhla`，
  `[Code]` 里 `Result := not FileExists(ExpandConstant('{app}\file\main.fhl'))` ——
  升级用户已有带数据的 `main.fhl` 时不再种空 `.fhla`（否则 `main.default_quick_project_path()`
  优先 `.fhla`，用户会以为记录被清空，也不再触发迁移提示）。② 的排除表同时也排除了 `main.fhl,main.fhla`。
- **本机试编译（不打包、不安装）**：用
  `C:\Users\13577\AppData\Local\Programs\Inno Setup 6\ISCC.exe`，先造一个「与 CI 同形的假 dist」
  （`<tmp>/dist/F HamLog 2.exe` + `dist/file/` 放 `main.fhla`、**不要放** `main.fhl`），再
  `/DSourceDistDir=<tmp>\dist /DOutputDirPath=<tmp>\out /DRepoRoot=<repo>` 编译。
  Git Bash 下必须 `export MSYS2_ARG_CONV_EXCL="*"`，否则 `/D...` 参数会被当路径转换 →
  「You may not specify more than one script filename」。
- **运行时验证 `Check:` 是否生效**：复制一份 `.iss` 把 `PrivilegesRequired` 改成 `lowest`、删掉
  `[Icons]` 两行与 `[INI]` 行（避免写开始菜单/注册表），`/DChineseMessagesFile=<repo>\.github\inno\ChineseSimplified.isl`
  编译，然后 `setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /NOICONS /DIR=<tmp>\A`：
  A（空目录）应出现 `file\main.fhla`；B（预置 `file\main.fhl`）应**没有** `main.fhla` 且 `main.fhl` 保留。
  测完用 `unins000.exe /VERYSILENT` 卸载再删目录。

## Git 合并 `file/` 数据文件（冲突处理口径）
- `.tle` 冲突几乎总是「不同时刻同一批数据」：比三侧行数，**取更完整/更新一侧**。
- `m_xml.txt` 冲突通常只差 `sat_last_update` 时间戳 → 取较新值。
- `.workbuddy/memory/*.md` 是追加型 → **双方内容全保留**，只删 `<<<<<<<`/`=======`/`>>>>>>>` 标记行。
- `project.py` 的 `_bk_snapshot(...)` 冲突 → 合并为 `_bk_snapshot(snap)` + 各自提示调用。
- **绝不能 `git checkout -- file/…`** 还原数据文件（用户正在用，可能已手工改）。

## 运行日志（app_log.py）——2026-10-17 新增
- **入口装配**：`__main__.py`（import main **之前**）与 `main.main()` 开头各调一次 `app_log.setup()`（幂等）。
  落盘 `app_path('file/log')`，按天一个文件 `F_HamLog_YYYY-MM-DD.log`，**只留三天**（启动时清更早的）；
  C 层崩溃栈单独 `F_HamLog_crash_YYYY-MM-DD.log`（faulthandler 常开句柄）。
- **四路来源**：根 logger + `sys.stdout/stderr` 换成 `_StreamTee`（print 也进日志，stdout=INFO、stderr=ERROR）
  + `sys.excepthook` / `threading.excepthook`（完整 traceback）+ `faulthandler` / `qInstallMessageHandler`。
- 两条硬约束：**日志自己不能把程序带崩**（全部 try 兜住、`logging.raiseExceptions=False`、Tee 用
  `threading.local` 防「写失败 → stderr 回灌 → 再失败」的递归）；**窗口版 exe 下 `sys.stdout` 是 None**，
  Tee 必须支持原流为 None（只记日志）。
- `_excepthook` 只调用**定制**的旧钩子；默认钩子改为直接写 `sys.__stderr__`，否则同一段 traceback 会经
  Tee 在日志里出现两遍。
- 打包命令加 `--noinclude-data-files="file/log/*.log"`；`.gitignore` 已忽略 `src/f_hamlog/file/log/`。
  验证：`tests/__app_log_smoke.py`（21 项）。

## 过境 / 通联视图（satellite_sky_window.py，2026-10-18 素色定稿）
- 极坐标天空图。两个预测窗口的**行内「视图」按钮**是唯一数据入口。
- 布局 = 「素色天空图（1 或 2 张并排）+ 右侧 `PANEL_W` 面板『过境数据』（方位角 / 仰角 / 距离 / 高度 +
  进度条 + 图例）」；数据走普通 QLabel，圆盘只画图。
- **配色一律从 `QPalette` 混合**：Highlight 给轨迹 / 箭头 / 卫星，WindowText 给文字，Base 给盘底，
  `theme.blend` 出网格与太阳；**禁止写死颜色**；换主题靠 `theme.watch_theme` 重取。
- **素色定稿**：不做阴影 / 光晕 / 渐变 / 圆角；状态只用一个着色文字，进度条方头，面板无描边无底色，
  可通联只是把线画粗（2.4× 线宽，不压暗其余轨迹）。
- `QTimer` 每秒 `follow` 刷新，拖滑块即退出实时。数据层 `sp.sky_track()`（一次矢量算 240 点）+
  `sp.sun_altaz()` / `sp.moon_altaz()`（纯解析，无 bsp 星历）；**skyfield 没有 `ts.utc(jd=...)`**，
  JD 一律 `ts.from_datetime(jd_to_datetime(jd))`，`Time.utc_datetime()` 对数组返回 ndarray。
- 通联视图的「双方全部过境」：入口传 `emphasis=(可通联起,止)` + `auto_spans=True`，每站用 `_pass_span()`
  求自己的 AOS→LOS 取轨迹，时间轴取并集（轨迹算完再按采样点扩一次轴，因为 `jd_to_datetime` 只到微秒）；
  可通联段加粗（2.4× 线宽，无光晕），图例多一行「可通联」。
- 两个窗口工具栏的「过境视图」：有选中用选中行，没有就自动取最近一次（优先未结束的最近一次，否则刚过去
  的那次）并 `selectRow()` 高亮；只有表格为空才弹「还没有过境结果」。
- **窗口是独立顶层窗口**（`SkyWindow(None, ...)`，来源窗口只存 `_source` 用来定初始位置）：有父对象就会
  变成「被拥有的窗口」，Windows 下最小化来源窗口时会跟着一起最小化（`MapWindow(None, ...)` 同理）。
- **经纬度 0° 是合法坐标**（赤道 / 本初子午线）：不得用「经纬度均为 0 → 视为未设置」去拦截
  （曾各弹一个 QMessageBox，2026-10-18 移除）。

## 自定义日志字段：落盘键与行为（配合 §日志字段定义）
- 入口「文件 → 自定义日志字段」：说明 + 表格 + 添加 / 删除 / 上移 / 下移 / **恢复默认** / 保存更改 / 关闭。
  **只填字段名称**（键 = 首次创建时的名称，撞名 `_2`；改名只改显示名，记录键不动 → 不丢数据）。
- 整表含**标准 20 行**（名称灰显不可改 / 删，但可一起排队）；**这张表的顺序 = 「新建日志 / 更多信息」行序
  = 主页列序**（一处排序三处跟着走）→ 呼号大写委托**按 key 找行号，不能写死行 2/3**。
- 「必填」「在主页显示」**所有字段都能改**（默认值 = `STANDARD_REQUIRED_KEYS` / `MAIN_DEFAULT_KEYS`）；
  改回默认即删覆盖项，**xml 里只记偏离默认的键**。
- 落盘：`other_item`（键→名称）+ `field_order` + `field_meta`。**「恢复默认」只重置表格，点「保存更改」
  才写盘**；顺序回到历史默认时 `field_order` 整个省掉（文件回到出厂状态）。
- **`.fhl` 一律不给**：管理窗口拒绝、`custom_fields()` 恒空、录入窗口只 20 行。
