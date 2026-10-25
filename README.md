# 业余无线电台通联日志 · F HamLog

> **语言 / Language：** 中文 · [English](#amateur-radio-qso-log--f-hamlog)

---

## 基本功能

### 编辑日志
支持基本的业余无线电台通联日志的记录。
支持从 ADI 文件导入导出。
支持从 HAM 个人工具导入。
支持导出为表格。

### 卫星通联
支持预测卫星过境。
支持预测任意两地可通联的卫星过境。

### 加密日志
支持使用 AES 加密日志。

### 支持安装插件
可以自行编写插件，并安装。

### 远程日志
支持编辑远程服务器上的日志。

**1.8.0~2.3.0 版本（包括 1.8.0 和 2.3.0）不支持远程日志。如需使用，请自行构建 [#remote_project.py](https://github.com/Mubi-Baihua/F_HamLog/blob/main/%23remote_project.py)。**

**不同版本的 F HamLog 需要不同的远程日志服务端，请直接从该 F HamLog 版本的 Releases 页下载对应的服务端。**

2.4.0 及以上版本的远程日志不需要单独搭建一个服务端，你可以直接使用 F HamLog 创建远程日志房间。

---

## 重要提示
1. 2.3.0 以上版本支持覆盖安装，自动保留原有数据。但仍建议在安装前手动备份默认通联日志。
2. 请定期手动备份默认通联日志。
3. 强烈不建议手动修改 F HamLog 项目文件，在使用插件前请确认插件来自可信的开发者。
4. 2.8.0 及以后版本的 **Releases 不再附带「兼容版」压缩包**（免安装、解压即用），请下载该版本的安装包安装。此前版本仍在其 Releases 页面保留兼容版压缩包。

---

## 预览版
每天凌晨 GitHub Actions 会自动打包预览版。可以在[这里](https://github.com/Mubi-Baihua/F_HamLog/actions/workflows/preview.yml)下载最新构建的预览版。
目前仅提供最新版本的预览版下载。
预览版与正式版数据各不互通，可以通过 设置 > 从其他版本导入数据 同步数据。

> [!WARNING]
> 预览版的部分功能不稳定，可能损坏某些文件，使用预览版时请做好备份。

---

## 从源码运行（开发）

源码采用 src 布局：包在 `src/f_hamlog/`（入口 `src/f_hamlog/__main__.py`）。开发时先把项目以**可编辑方式**装进虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .            # 依赖已装好时可加 --no-deps 只装项目本体
```

`pip install -e .` 会往虚拟环境里写一条路径记录（`__editable__.f_hamlog-*.pth`，内容就是 `src` 的绝对路径），效果等同于常驻的 `PYTHONPATH=src`。因此：

- 任何工作目录下都能 `import f_hamlog`，也能用 `python -m f_hamlog` 启动；
- 可以直接运行包内文件来调试，例如 `python src/f_hamlog/project.py`；
- **换环境（新建 venv、换机器、别人 clone 之后）需要重新执行一次 `pip install -e .`**，这一步不会自动发生。

安装后三种启动方式等价：

```powershell
f-hamlog                          # pip 注册的命令行入口
python -m f_hamlog
python src/f_hamlog/__main__.py
```

几点说明：

- 安装会在源码树里生成 `src/f_hamlog.egg-info/`（元数据），已在 `.gitignore` 中忽略，**不要提交**。
- 运行产生的数据（`src/f_hamlog/file/` 下的设置、日志、密钥等）仍在源码目录中，不受安装影响。
- 发布不通过 pip 分发：正式版用根目录 `打包.txt` 里的 Nuitka 命令构建独立 exe，见仓库的 GitHub Actions 工作流。

---

## 相关技术文档

### 插件开发

可查看[示例插件](https://github.com/Mubi-Baihua/F_HamLog/blob/main/F%20%E6%A0%BC%E5%BC%8F%E4%BC%98%E5%8C%96.fhlpypack)。

#### 插件主体结构
```
XML:{"describe":"<插件的描述>","pack version":"<插件的版本>","available fhl version":["<插件适配的F HamLog版本>","<插件适配的F HamLog版本 2>"],"producer":"<开发者>"}
python:
#你的python代码
```

#### 插件 python 代码

##### 输入

运行时 F HamLog 会把当前项目写在 python 文件的工作目录下，**两份都提供**，编码均为 utf-8，且**一律是解密后的明文**（加密项目也会先解密再交给插件）：

| 文件名 | 内容 |
| --- | --- |
| `input.fhl` | 纯记录数组（老接口，与以往完全一致） |
| `input.fhla` | `{"xml": 属性块, "project": 记录数组}`，与磁盘上的 `.fhla` 同构；`xml.encrypted` 恒为 `false`，可据此读取自定义字段定义（`other_item` / `field_order` / `field_meta`）等项目属性 |

只想改记录时读 `input.fhl` 就够了；需要用到项目属性（自定义字段）时读 `input.fhla`。两者来自同一份项目，记录部分完全一致。属性块里各键的含义见下文「[FHLA 文件格式（.fhla）](#fhla-文件格式fhla)」。

示例输入代码：
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

# 纯记录（老接口）
with open(f"{abs_path}/input.fhl", "r", encoding="utf-8") as f:
    file_list = json.load(f)  

# 记录 + 项目属性（.fhla 结构，已解密）
with open(f"{abs_path}/input.fhla", "r", encoding="utf-8") as f:
    project = json.load(f)
```

##### 输出

运行时 F HamLog 会读取 python 文件工作目录下的 `output.fhla` 与 `output.fhl`（utf-8），**哪个存在就用哪个，`.fhla` 优先**（两个都写时只用 `output.fhla`，`output.fhl` 被忽略）：

| 文件名 | 生效范围 |
| --- | --- |
| `output.fhla` | `{"xml": 属性块, "project": 记录数组}`：记录与项目属性（自定义字段定义等）一起替换 |
| `output.fhl` | 纯记录数组：只替换记录，项目属性保持原样（老插件行为不变） |

- 只改记录时**不要**写 `output.fhla`——它优先，会连属性块一起覆盖。
- `output.fhla` 存在但内容不合法时，会提示「无法解析」并**保持项目原样**，不会退回去用 `output.fhl`。
- 结构不对（例如把 `{"xml":…, "project":…}` 写进 `output.fhl`）会提示「不是记录列表」，同样保持项目原样。
- 一次运行结束后，`input.fhl` / `input.fhla` / `output.fhl` / `output.fhla` 都会被删除。
- 老版本 F HamLog 只认 `output.fhl`：需要兼容旧版时请只写 `output.fhl`。

示例输出代码：
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

# 只改记录（老接口，任何版本都认）
with open(f"{abs_path}/output.fhl", "w", encoding="utf-8") as f:
    json.dump(file_list, f, ensure_ascii=False, indent=2)

# 或者：记录 + 属性一起写（优先于 output.fhl）
project["project"] = file_list
with open(f"{abs_path}/output.fhla", "w", encoding="utf-8") as f:
    json.dump(project, f, ensure_ascii=False, indent=4)
```

#### 插件打包
将插件文件保存为 `*.fhlpypack` 文件。编码使用 utf-8。

### FHL 文件格式
FHL 文件格式为 json 文件。编码使用 utf-8。

> [!WARNING]
> 强烈不建议手动修改 F HamLog 项目文件！

参考文件：
```json
[
    {
    "date": "2026-01-27",
    "time": "11:27",
    "m_call": "BI8SQL",
    "o_call": "BD8SE",
    "freq": "438.7",
    "freq_rx": "438.7",
    "mode": "FM",
    "prop_mode": "SAT",
    "sat_name": "SO-50",
    "m_rst": "59",
    "o_rst": "59",
    "m_qth": "昆明",
    "o_qth": "成都",
    "m_dig": "UV-K5",
    "o_dig": "DM9100",
    "m_ant": "原装",
    "o_ant": "原装",
    "m_pow": "H",
    "o_pow": "H",
    "notes": "中继点名"
  },
  {
    "date": "2026-01-03",
    "time": "13:42",
    "m_call": "BI8SQL",
    "o_call": "BG8SVJ",
    "freq": "438.7",
    "freq_rx": "438.7",
    "mode": "FM",
    "prop_mode": "SAT",
    "sat_name": "ARISS",
    "m_rst": "59",
    "o_rst": "59",
    "m_qth": "昆明",
    "o_qth": "西南林业大学",
    "m_dig": "IC-705",
    "o_dig": "IC-9700",
    "m_ant": "原装",
    "o_ant": "771",
    "m_pow": "H",
    "o_pow": "M",
    "notes": "测试设备"
  }
]
```

字典中字段对应的中文：
```json
{
    "date": "日期",
    "time": "时间",
    "m_call": "己方呼号",
    "o_call": "对方呼号",
    "freq": "频率",
    "freq_rx": "接收频率",
    "mode": "调制模式",
    "prop_mode": "传播方式",
    "sat_name": "卫星名称",
    "m_rst": "己方接收信号",
    "o_rst": "对方接收信号",
    "m_qth": "己方QTH",
    "o_qth": "对方QTH",
    "m_dig": "己方设备",
    "o_dig": "对方设备",
    "m_ant": "己方天线",
    "o_ant": "对方天线",
    "m_pow": "己方功率",
    "o_pow": "对方功率",
    "notes": "备注"
}
```

#### FHLA 文件格式（.fhla）

`.fhla` 是 F HamLog 的**默认项目格式**（文件对话框中显示为「F HamLog 项目」），在 `.fhl` 纯记录格式之外，额外保存项目属性与自定义字段。

结构为顶层两个键的 JSON（`utf-8` 编码）：

```json
{
  "xml": {
    "last_editor": "BI8SQL",
    "last_edit_time": "2026-10-18 10:30:00",
    "last_version": "2.7.0",
    "encrypted": false,
    "format": "fhla",
    "format_version": 1,
    "other_item": {"wx": "天气"},
    "field_order": ["date", "time", "m_call", "o_call", "freq", "freq_rx", "mode", "prop_mode", "sat_name", "m_rst", "o_rst", "m_qth", "o_qth", "m_dig", "o_dig", "m_ant", "o_ant", "m_pow", "o_pow", "notes"],
    "field_meta": {"wx": {"required": false, "main": true}}
  },
  "project": [
    { "date": "2026-01-27", "time": "11:27", "m_call": "BI8SQL", "o_call": "BD8SE", "freq": "438.7", "freq_rx": "438.7", "mode": "FM", "prop_mode": "SAT", "sat_name": "SO-50", "m_rst": "59", "o_rst": "59", "m_qth": "昆明", "o_qth": "成都", "m_dig": "UV-K5", "o_dig": "DM9100", "m_ant": "原装", "o_ant": "原装", "m_pow": "H", "o_pow": "H", "notes": "中继点名" }
  ]
}
```

- `project`：**与 `.fhl` 完全相同的记录数组**，每条记录的字段含义见上表；旧版 F HamLog 也读得懂 `.fhl`。
- `xml`（项目属性块）：
  - `last_editor` / `last_edit_time`：上一次编辑的人与时间；
  - `last_version`：上次打开所用的 F HamLog 版本；
  - `encrypted`：加密状态（`true` 时整份文件为 AES-GCM 密文，不再是上面的明文 JSON）；
  - `format` / `format_version`：固定为 `"fhla"` / `1`；
  - `other_item`：自定义字段「键 → 显示名」映射；`field_order`：全部字段的顺序（含标准字段）；`field_meta`：各字段的「必填 / 是否主页显示」，仅记录偏离默认的项。
- 项目属性（Alt+I）与自定义日志字段只在 `.fhla` 上可用；`.fhl` 不含这些，打开时会提示「不支持的格式」。
- 兼容性：把 `.fhl` **改名**为 `.fhla` 后即可被识别（内容一个字节未变，程序会把纯记录自动包成 `{xml:{}, project:[...]}`）；但属性块会在首次保存前保持为空，保存一次后补全。也可在打开 `.fhl` 时按提示「迁移」为 `.fhla`（迁移成功会删除原 `.fhl`）。

##### Coded by [BI8SQL](https://mubi-baihua.pages.dev/)

---

# Amateur Radio QSO Log · F HamLog

> **Language:** [中文](#业余无线电台通联日志--f-hamlog) · English

---

## Basic Features

### Edit Log
Supports basic logging of amateur radio QSO records.
Supports import/export from ADI files.
Supports import from HAM personal tools.
Supports export to spreadsheets.

### Satellite Contacts
Supports predicting satellite passes.
Supports predicting satellite passes visible to any two locations.

### Encrypted Log
Supports encrypting the log with AES.

### Plugin Support
You can write and install your own plugins.

### Remote Log
Supports editing logs on a remote server.

**Versions 1.8.0~2.3.0 (including 1.8.0 and 2.3.0) do not support remote logs. If you need it, build [#remote_project.py](https://github.com/Mubi-Baihua/F_HamLog/blob/main/%23remote_project.py) yourself.**

**Different versions of F HamLog require different remote log servers. Please download the matching server directly from that F HamLog version's Releases page.**

Remote logs in version 2.4.0 and above do not require a separate server — you can create a remote log room directly with F HamLog.

---

## Important Notes
1. Version 2.3.0 and above supports overwrite installation, automatically preserving existing data. However, it is still recommended to manually back up the default log before installing.
2. Please manually back up the default log regularly.
3. Manually modifying F HamLog project files is strongly discouraged. Before using a plugin, make sure it comes from a trusted developer.
4. Starting with 2.8.0, the **Releases page no longer includes the "compatible" (portable, no-install) zip**; please download the installer for that version instead. Earlier versions keep their compatible zips on their own Releases pages.

---

## Preview Builds
GitHub Actions automatically builds a preview every night. You can download the latest preview build [here](https://github.com/Mubi-Baihua/F_HamLog/actions/workflows/preview.yml).
Currently only the latest version's preview is available.
Preview and stable builds keep separate data. You can sync data via Settings > Import data from other versions.

> [!WARNING]
> Some features in preview builds are unstable and may corrupt certain files. Please back up your data when using a preview build.

---

## Running from Source (Development)

The source uses a src layout: the package lives in `src/f_hamlog/` (entry point `src/f_hamlog/__main__.py`). Install it into a virtual environment in **editable** mode first:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .            # add --no-deps if the dependencies are already installed
```

`pip install -e .` writes a path entry into the environment (`__editable__.f_hamlog-*.pth`, containing the absolute path of `src`), which is equivalent to a permanent `PYTHONPATH=src`. As a result:

- `import f_hamlog` works from any working directory, and `python -m f_hamlog` launches the app;
- individual modules can be run directly for debugging, e.g. `python src/f_hamlog/project.py`;
- **after switching environments (a new venv, another machine, a fresh clone) you must run `pip install -e .` again** — it is not automatic.

Once installed, these three are equivalent:

```powershell
f-hamlog                          # console script registered by pip
python -m f_hamlog
python src/f_hamlog/__main__.py
```

Notes:

- The install creates `src/f_hamlog.egg-info/` metadata in the source tree; it is already covered by `.gitignore` and must not be committed.
- Runtime data (settings, logs, keys under `src/f_hamlog/file/`) stays in the source directory and is unaffected by the install.
- Releases are not distributed as pip packages: official builds use the Nuitka command in `打包.txt` to produce a standalone exe (see the GitHub Actions workflows).

---

## Technical Documentation

### Plugin Development

See the [example plugin](https://github.com/Mubi-Baihua/F_HamLog/blob/main/F%20%E6%A0%BC%E5%BC%8F%E4%BC%98%E5%8C%96.fhlpypack).

#### Plugin Structure
```
XML:{"describe":"<plugin description>","pack version":"<plugin version>","available fhl version":["<compatible F HamLog version>","<compatible F HamLog version 2>"],"producer":"<developer>"}
python:
# your python code
```

#### Plugin Python Code

##### Input
At runtime, F HamLog writes the current project into the working directory of the python file, **both files are provided**, encoded in utf-8, and always **decrypted plain text** (encrypted projects are decrypted before being handed to the plugin):

| File | Content |
| --- | --- |
| `input.fhl` | Plain array of records (the legacy interface, unchanged) |
| `input.fhla` | `{"xml": meta block, "project": records}`, the same shape as an on-disk `.fhla`; `xml.encrypted` is always `false`, so plugins can read project properties such as custom field definitions (`other_item` / `field_order` / `field_meta`) |

Read `input.fhl` if you only need the records; read `input.fhla` when you need project properties (custom fields). Both come from the same project, and their record arrays are identical. The meaning of each meta key is described in [FHLA File Format (.fhla)](#fhla-file-format-fhla) below.

Example input code:
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

# Plain records (legacy interface)
with open(f"{abs_path}/input.fhl", "r", encoding="utf-8") as f:
    file_list = json.load(f)  

# Records + project properties (.fhla shape, decrypted)
with open(f"{abs_path}/input.fhla", "r", encoding="utf-8") as f:
    project = json.load(f)
```

##### Output
At runtime, F HamLog looks for `output.fhla` and `output.fhl` in the working directory of the python file (utf-8). **Whichever exists is used, and `.fhla` wins** (if both are written, only `output.fhla` is read and `output.fhl` is ignored):

| File | What it replaces |
| --- | --- |
| `output.fhla` | `{"xml": meta block, "project": records}`: replaces both the records and the project properties (custom field definitions, etc.) |
| `output.fhl` | Plain array of records: replaces the records only, project properties stay as they were (legacy behaviour unchanged) |

- To change records only, do **not** write `output.fhla` — it takes priority and would overwrite the meta block too.
- If `output.fhla` exists but is invalid, F HamLog reports that it cannot be parsed and **leaves the project untouched**; it does not fall back to `output.fhl`.
- A wrong structure (for example a `{"xml":…, "project":…}` written to `output.fhl`) reports "not a list of records" and also leaves the project untouched.
- After each run, `input.fhl` / `input.fhla` / `output.fhl` / `output.fhla` are all deleted.
- Older F HamLog versions only read `output.fhl`: write `output.fhl` alone when you need to stay compatible with them.

Example output code:
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

# Records only (legacy interface; understood by every version)
with open(f"{abs_path}/output.fhl", "w", encoding="utf-8") as f:
    json.dump(file_list, f, ensure_ascii=False, indent=2)

# Or: records + properties together (takes priority over output.fhl)
project["project"] = file_list
with open(f"{abs_path}/output.fhla", "w", encoding="utf-8") as f:
    json.dump(project, f, ensure_ascii=False, indent=4)
```

#### Plugin Packaging
Save the plugin file as a `*.fhlpypack` file, encoded in utf-8.

### FHL File Format
The FHL file format is a JSON file, encoded in utf-8.

> [!WARNING]
> Manually modifying F HamLog project files is strongly discouraged!

Reference file:
```json
[
    {
    "date": "2026-01-27",
    "time": "11:27",
    "m_call": "BI8SQL",
    "o_call": "BD8SE",
    "freq": "438.7",
    "freq_rx": "438.7",
    "mode": "FM",
    "prop_mode": "SAT",
    "sat_name": "SO-50",
    "m_rst": "59",
    "o_rst": "59",
    "m_qth": "昆明",
    "o_qth": "成都",
    "m_dig": "UV-K5",
    "o_dig": "DM9100",
    "m_ant": "原装",
    "o_ant": "原装",
    "m_pow": "H",
    "o_pow": "H",
    "notes": "中继点名"
  },
  {
    "date": "2026-01-03",
    "time": "13:42",
    "m_call": "BI8SQL",
    "o_call": "BG8SVJ",
    "freq": "438.7",
    "freq_rx": "438.7",
    "mode": "FM",
    "prop_mode": "SAT",
    "sat_name": "ARISS",
    "m_rst": "59",
    "o_rst": "59",
    "m_qth": "昆明",
    "o_qth": "西南林业大学",
    "m_dig": "IC-705",
    "o_dig": "IC-9700",
    "m_ant": "原装",
    "o_ant": "771",
    "m_pow": "H",
    "o_pow": "M",
    "notes": "测试设备"
  }
]
```

Chinese meanings of the dictionary fields:
```json
{
    "date": "Date",
    "time": "Time",
    "m_call": "Own callsign",
    "o_call": "Other party's callsign",
    "freq": "Frequency",
    "freq_rx": "Receive frequency",
    "mode": "Modulation mode",
    "prop_mode": "Propagation mode",
    "sat_name": "Satellite name",
    "m_rst": "Own RST received",
    "o_rst": "Other party's RST received",
    "m_qth": "Own QTH",
    "o_qth": "Other party's QTH",
    "m_dig": "Own equipment",
    "o_dig": "Other party's equipment",
    "m_ant": "Own antenna",
    "o_ant": "Other party's antenna",
    "m_pow": "Own power",
    "o_pow": "Other party's power",
    "notes": "Notes"
}
```

#### FHLA File Format (.fhla)

`.fhla` is the **default project format** of F HamLog (shown as "F HamLog Project" in the file dialog). On top of the plain-record `.fhl` format, it additionally stores project properties and custom fields.

It is a JSON file (utf-8) with two top-level keys:

```json
{
  "xml": {
    "last_editor": "BI8SQL",
    "last_edit_time": "2026-10-18 10:30:00",
    "last_version": "2.7.0",
    "encrypted": false,
    "format": "fhla",
    "format_version": 1,
    "other_item": {"wx": "Weather"},
    "field_order": ["date", "time", "m_call", "o_call", "freq", "freq_rx", "mode", "prop_mode", "sat_name", "m_rst", "o_rst", "m_qth", "o_qth", "m_dig", "o_dig", "m_ant", "o_ant", "m_pow", "o_pow", "notes"],
    "field_meta": {"wx": {"required": false, "main": true}}
  },
  "project": [
    { "date": "2026-01-27", "time": "11:27", "m_call": "BI8SQL", "o_call": "BD8SE", "freq": "438.7", "freq_rx": "438.7", "mode": "FM", "prop_mode": "SAT", "sat_name": "SO-50", "m_rst": "59", "o_rst": "59", "m_qth": "昆明", "o_qth": "成都", "m_dig": "UV-K5", "o_dig": "DM9100", "m_ant": "原装", "o_ant": "原装", "m_pow": "H", "o_pow": "H", "notes": "中继点名" }
  ]
}
```

- `project`: **the same record array as `.fhl`** — each record's fields are listed in the table above; older F HamLog versions can still read `.fhl`.
- `xml` (project property block):
  - `last_editor` / `last_edit_time`: the person and time of the last edit;
  - `last_version`: the F HamLog version used when last opened;
  - `encrypted`: encryption flag (when `true`, the whole file is an AES-GCM ciphertext instead of the plain JSON above);
  - `format` / `format_version`: fixed to `"fhla"` / `1`;
  - `other_item`: custom-field "key → display name" map; `field_order`: order of all fields (including the standard ones); `field_meta`: per-field "required / shown on home page" flags, recording only entries that differ from the default.
- Project properties (Alt+I) and custom log fields are available only on `.fhla`; `.fhl` lacks them and will show an "unsupported format" message when opened.
- Compatibility: **renaming** a `.fhl` to `.fhla` makes it recognizable immediately (the content is unchanged — the app wraps the plain list into `{xml:{}, project:[...]}` automatically). However, the property block stays empty until the first save, after which it is filled in. You can also choose "migrate" when opening a `.fhl` to convert it to `.fhla` (the original `.fhl` is deleted after a successful migration).

##### Coded by [BI8SQL](https://mubi-baihua.pages.dev/)
