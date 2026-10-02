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

---

## 预览版
每天凌晨 GitHub Actions 会自动打包预览版。可以在[这里](https://github.com/Mubi-Baihua/F_HamLog/actions/workflows/preview.yml)下载最新构建的预览版。
目前仅提供最新版本的预览版下载。
预览版与正式版数据各不互通，可以通过 设置 > 从其他版本导入数据 同步数据。

> [!WARNING]
> 预览版的部分功能不稳定，可能损坏某些文件，使用预览版时请做好备份。

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
运行时 F HamLog 会将当前文件放在 python 文件的工作目录下。名称为：`input.fhl`。编码使用 utf-8。

示例输入代码：
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

with open(f"{abs_path}/input.fhl", "r", encoding="utf-8") as f:
    file_list = json.load(f)  
```

##### 输出
运行时 F HamLog 会读取 python 文件的工作目录下的输出文件。名称为：`output.fhl`。编码使用 utf-8。

示例输出代码：
```python
from pathlib import Path

abs_path = Path(__file__).resolve().parent

with open(f"{abs_path}/output.fhl", "w", encoding="utf-8") as f:
    json.dump(file_list, f, ensure_ascii=False, indent=2)
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

##### Coded by [BI8SQL](https://mubi-baihua.github.io/)

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

---

## Preview Builds
GitHub Actions automatically builds a preview every night. You can download the latest preview build [here](https://github.com/Mubi-Baihua/F_HamLog/actions/workflows/preview.yml).
Currently only the latest version's preview is available.
Preview and stable builds keep separate data. You can sync data via Settings > Import data from other versions.

> [!WARNING]
> Some features in preview builds are unstable and may corrupt certain files. Please back up your data when using a preview build.

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
At runtime, F HamLog places the current file in the working directory of the python file, named `input.fhl`, encoded in utf-8.

Example input code:
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

with open(f"{abs_path}/input.fhl", "r", encoding="utf-8") as f:
    file_list = json.load(f)  
```

##### Output
At runtime, F HamLog reads the output file in the working directory of the python file, named `output.fhl`, encoded in utf-8.

Example output code:
```python
from pathlib import Path

abs_path = Path(__file__).resolve().parent

with open(f"{abs_path}/output.fhl", "w", encoding="utf-8") as f:
    json.dump(file_list, f, ensure_ascii=False, indent=2)
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

##### Coded by [BI8SQL](https://mubi-baihua.github.io/)
