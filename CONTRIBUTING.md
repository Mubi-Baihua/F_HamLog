# 为 F HamLog 贡献力量

> **语言 / Language：** 中文 · [English](#contributing-to-f-hamlog)

首先，感谢你愿意花时间为 F HamLog（业余无线电通联日志）做贡献！🎉

无论是报告一个 bug、提出一个新功能、完善文档，还是直接提交代码，你的每一份帮助都让这个项目变得更好。

本文档说明**如何参与贡献**以及**这个项目是怎么组织的**。在动手之前，请花几分钟通读，能让你的贡献更容易被接受，也能少走弯路。

---

## 目录

- [贡献方式](#贡献方式)
- [行为准则](#行为准则)
- [报告问题与提出建议](#报告问题与提出建议)
- [开发环境搭建](#开发环境搭建)
- [项目结构](#项目结构)
- [核心架构说明](#核心架构说明)
- [代码规范](#代码规范)
- [测试](#测试)
- [提交 Pull Request](#提交-pull-request)
- [打包与发布](#打包与发布)
- [数据文件与安全](#数据文件与安全)
- [许可证](#许可证)

---

## 贡献方式

你不必是编程高手才能帮忙。以下方式都同样有价值：

| 方式 | 说明 |
| --- | --- |
| 🐞 **报告 Bug** | 使用 [Bug report 模板](.github/ISSUE_TEMPLATE/bug_report.md) 提交 issue |
| 💡 **功能建议** | 使用 [Feature request 模板](.github/ISSUE_TEMPLATE/feature_request.md) 提交 issue |
| 📝 **改进文档** | 修正 README / 本文档中的错误、补充说明 |
| 🔌 **编写插件** | 为 F HamLog 编写 `.fhlpypack` 插件（见 [README](README.md#插件开发)） |
| 🧑‍💻 **提交代码** | 修复 bug、实现功能、性能优化、重构 |
| 🌏 **翻译 / 本地化** | 改进界面文案、语言文件 |
| ⭐ **反馈与传播** | 点亮 Star、分享给其他 Ham |

> [!IMPORTANT]
> **请勿在未沟通的情况下进行大规模重构或重命名。** 这类改动影响面大、评审成本高，建议先在 issue 中讨论方案，达成一致后再动手。

---

## 行为准则

参与本项目即表示你同意遵守我们的 [行为准则（CODE_OF_CONDUCT.md）](CODE_OF_CONDUCT.md)。
请在所有交流（issue、PR、讨论）中保持友善与尊重。

---

## 报告问题与提出建议

在提交 issue 之前，请先搜索[已有 issue](https://github.com/Mubi-Baihua/F_HamLog/issues)，避免重复。

提交 Bug 时，**尽量提供可复现的信息**，这能极大加速定位：

- 你使用的 **F HamLog 版本**（正式版 / 预览版，及版本号）
- **操作系统**（如 Windows 11 23H2）与是否为**深色模式**
- **复现步骤**（从打开软件到出错，一步一步写清楚）
- **预期行为**与实际行为
- **截图 / 录屏**（界面问题强烈建议附带）
- 出错时的**报错信息或日志**

功能建议请说明：**你想解决什么问题**、期望的交互方式，以及有没有考虑过的替代方案。

> [!WARNING]
> 报告中请**不要粘贴任何密钥、密码、`file/keys/` 内容或私人通联记录**。这些属于敏感数据（见[数据文件与安全](#数据文件与安全)）。

---

## 开发环境搭建

### 前置要求

- **Python 3.13**（项目当前开发/打包使用 3.13.x）
- **Windows**（发布目标平台；界面基于 PySide6，跨平台可运行但未做保证）
- **Git**

### 依赖安装

第三方依赖清单见仓库根目录的 [`第三方模块.txt`](第三方模块.txt)：

```text
pyside6
pandas
openpyxl
nuitka
skyfield
numpy
cryptography
matplotlib
```

建议使用虚拟环境（仓库使用 `.venv/`，已被 `.gitignore` 忽略）：

```bash
python -m venv .venv
# Windows (Git Bash)
.venv/Scripts/python.exe -m pip install -r 第三方模块.txt
```

> 运行程序本体只需要 `pyside6`、`skyfield`、`numpy`、`cryptography`、`openpyxl`、`pandas`。
> `nuitka` 仅打包时需要，`matplotlib` 目前未被核心代码引用。

### 运行

```bash
.venv/Scripts/python.exe main.py
```

程序启动后会弹出主界面，运行数据（日志、星历缓存、设置）默认读写仓库根目录下的 `file/` 目录。

---

## 项目结构

```
F_HamLog/
├── main.py                     # 程序入口：主菜单窗口
├── project.py                  # 【核心】主通联日志窗口（最大、最复杂）
├── batch_project.py            # 批量记录窗口
├── set.py                      # 设置窗口（同时作为多个子窗口入口）
│
├── satellite_window.py         # 卫星过境预测窗口
├── mutual_window.py            # 互通过境预测窗口（两地可通联卫星）
├── satellite_map_window.py     # 卫星地图窗口（含世界地图绘制）
├── satellite_pred.py           # 【核心】天体/轨道计算（SGP4、仰角/方位、过境）
├── satellite_auto_update.py    # 启动时的 TLE（星历）定时自动更新
├── tle_source_window.py        # 星历数据源管理窗口
│
├── remote_server.py            # 多人日志服务端引擎（纯标准库）
├── remote_crypto.py            # 多人日志密码学（X25519 + HKDF + AES-GCM）
│
├── theme.py                    # 主题系统：浅色/深色/跟随系统（取色唯一出处）
├── toast_tip.py                # 轻量非模态提示条（动作反馈）
├── call_upper.py               # 呼号自动大写（表格委托）
├── dialog_defaults.py          # 文件对话框默认目录（桌面）
│
├── fhl_rw.py                   # .fhl 文件读写（JSON + 可选加密）
├── fhl_aes.py                  # AES-GCM 加解密（按密码加密日志）
├── backup.py                   # 未保存内容自动备份与关闭守卫
│
├── input_adi.py                # 从 ADI(ADIF) 导入
├── input_fhl.py                # 从 FHL 导入
├── input_HAM_tolls.py          # 从 "HAM 个人工具" 导入
├── export_adi.py               # 导出 ADIF（供 TQSL / LoTW 签名）
├── output_adi.py               # 导出 ADI
├── output_excel.py             # 导出为 Excel 表格
├── pack_set.py                 # 插件运行环境辅助（检测系统 Python 等）
│
├── file/                       # 运行时数据（见下方说明）
├── test/                       # 离屏（offscreen）冒烟测试与探针脚本
├── .github/
│   ├── workflows/              # GitHub Actions：main.yml（发布）、preview.yml（预览）
│   ├── ISSUE_TEMPLATE/         # issue 模板
│   └── inno/                   # CI 专用 Inno Setup 脚本 + 中文语言文件
├── F HamLog 2 Inno Setup/      # 本地打包的安装包产物
├── 兼容版/                     # 各版本"兼容版" zip 产物
├── F_HamLog_Remote_Log_Server_2.0.0/   # 独立服务端（自带 remote_* 副本，见下）
├── README.md / CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / LICENSE
└── 打包.txt / 第三方模块.txt / #remote_project.py
```

### 主要模块职责

| 模块 | 职责 | 备注 |
| --- | --- | --- |
| `main.py` | 入口、主菜单、启动时恢复/清理 | 各窗口的强引用声明在模块级 |
| `project.py` | 主日志窗口、表格、多人日志客户端 | 最核心、最庞大，改动需谨慎 |
| `satellite_pred.py` | 全部天文计算 | `skyfield` + `numpy`，离线运行 |
| `theme.py` | 所有界面取色 | **禁止在其它模块写死颜色** |
| `fhl_rw.py` | `.fhl` 读写 | 必须一次性写入，不用 `json.dump` |
| `remote_server.py` / `remote_crypto.py` | 多人日志服务端与密码学 | 纯标准库 / `cryptography` |
| `test/` | 离屏 GUI 冒烟测试 | 命名约定见[测试](#测试) |

### 其它目录说明

- **`file/`** —— 运行时数据目录：日志、星历缓存（`amateur.tle`）、设置（`m_xml.txt`）、
  星历数据源（`tle_sources.txt`）、地图标记、密钥（`keys/`）等。**其中部分是真实用户数据，不要随意改写。**
- **`F HamLog 1` ~ `F HamLog 2.1`** —— 历史版本快照，仅作归档，不参与构建。
- **`#remote_project.py`** —— 历史备份文件（文件名以 `#` 开头），当前无任何代码引用，请勿修改。
- **`F_HamLog_Remote_Log_Server_2.0.0/`** —— 可独立分发的服务端。**它自带 `remote_server.py` /
  `remote_crypto.py` 的副本**，若改动协议或密码学，需要**三处同步**（仓库根 + 该目录 + 打包脚本）。

---

## 核心架构说明

### 数据格式

- **`.fhl` 文件** = UTF-8 编码的 **JSON**，内容为 `list[dict]`，每个 dict 是一条通联记录。
- 字段定义见 [README 的 FHL 文件格式](README.md#fhl-文件格式)（如 `date` / `m_call` / `o_call` /
  `freq`（上行）/ `freq_rx`（下行）/ `sat_name` / `notes` 等）。
- 可选使用密码进行 **AES-GCM** 加密（见 `fhl_aes.py`）。
- **设置文件** `file/m_xml.txt` 是一个可用 `eval` 解析的 dict，读取时**一律用 `.get(...)`**。

### 界面约定

- 全部基于 **PySide6**，样式保持**系统原生**（Windows 11）。
- 颜色**只从 `theme.py` 取**，界面需同时适配浅色与深色。**验证颜色必须看渲染像素**
  （`widget.grab()`），不能只读 `palette()`。
- 文件对话框**一律使用原生** `QFileDialog.getOpenFileName / getSaveFileName`，默认目录为桌面
  （`dialog_defaults.desktop_dir()`）。
- 结果反馈类提示用 `toast_tip.show_toast(...)`；二次确认、格式错误、加解密等仍用对话框。

### 多人日志（远程/局域网）

- 服务端先说话（先发 `HELLO`），客户端回 `HELLO_ACK`；首次连接需**核对密钥指纹**（TOFU）。
- 密码只用于身份验证；会话密钥随机生成、经 ECDH 分发，随后对称加密全帧。
- 密钥根目录由显式 `key_dir` 决定（内嵌服务端 → `file/keys/`；独立服务端 → 程序目录 `keys/`）。
- **这些密钥与信任记录绝不能入库**（见 [`.gitignore`](.gitignore)）。

---

## 代码规范

本项目没有引入自动格式化工具，请**跟随现有代码风格**：

1. **语言与命名**：界面文案、注释、变量名使用中文或清晰的英文；避免无意义的英文后缀。
2. **主题**：**禁止在任何模块写死界面颜色**，一律通过 `theme.py` 取色，保证深浅色一致。
3. **文件对话框**：新增的文件打开/保存，使用 `QFileDialog` 原生静态方法，默认目录走 `dialog_defaults`。
4. **QSS `background-color` 会反写进控件调色板** —— 取色时请从未被染色的父/兄弟控件取值。
5. **性能**：主表格上万行时，**禁止逐行 `setCellWidget`**，改用自绘委托；勾选状态以闭包集合为唯一权威。
6. **持久化**：`.fhl` 写入必须 `json.dumps` 后一次性 `f.write`，**不要用 `json.dump`**。
7. **注释**：对"为什么这么做"的非常规实现请写明原因（很多坑已有先例，避免后人重蹈覆辙）。
8. **提交信息**：使用简短、能说明改动的中文描述（参考 `git log` 中既有风格）。

> [!TIP]
> 改动前建议先 `git log` / 阅读相关模块注释，很多"看起来多余"的写法其实是踩坑后的修复。

---

## 测试

项目使用**离屏（offscreen）GUI 冒烟测试**验证真实窗口行为。所有测试脚本统一放在 `test/` 目录。

命名约定：

| 前缀 | 用途 |
| --- | --- |
| `__*_smoke.py` / `test_*_smoke.py` | 冒烟测试：建窗、点按钮、读表、断言 |
| `__*_probe.py` | 探针：探查某个行为/数值 |
| `test_*.py` | 其它测试 |
| `__*_out.txt` / `__*_out.png` | 测试输出（已被 `.gitignore` 忽略） |

运行方式（关键：指定离屏平台）：

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe test/__toast_smoke.py
```

编写测试时请注意：

- 脚本应通过 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 将**项目根**加入 `sys.path`。
- **优先把路径常量 monkeypatch 到临时文件**（如 `satellite_pred.TLE_SOURCES_PATH`、
  `smw.MARKERS_PATH`），避免污染真实数据。
- **绝不能对 `file/` 下的数据文件执行 `git checkout --` 还原**（用户可能正在使用）；测完请核对并手动还原。
- 提示若已从 `QMessageBox` 改为 `toast_tip.show_toast`，测试需同时 monkeypatch `toast_tip.show_toast`。
- 槽函数中的 `sys.exit()` 会被 PySide6 的 C++ 边界直接终止进程，测试前需 `sys.exit = lambda *a, **k: None`。

提交代码前，请**至少运行与你改动相关的冒烟测试**，并确保通过。

---

## 提交 Pull Request

1. **Fork** 本仓库，并从 `develop` 分支创建你的工作分支（`develop` 是开发分支，`main` 为稳定分支）。
2. 保持改动**聚焦**：一个 PR 解决一个问题，避免混入无关的格式化或重命名。
3. 本地**自测通过**（见[测试](#测试)），必要时补充测试。
4. 更新相关文档（README / 本文档 / 代码注释）。
5. 提交 PR 时，请说明：**改了什么、为什么改、如何验证**，并关联相关 issue（如 `Closes #123`）。
6. 耐心等待评审，根据反馈进行修改。

> [!NOTE]
> 分支策略：功能开发合并到 `develop`，`main` 用于发布稳定版本。

---

## 打包与发布

发布由 GitHub Actions 自动化完成，相关文件：

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/main.yml` | **手动**发布：打包 → 生成安装包 → 兼容版 zip → 回写分支 → 发布 Release（默认草稿） |
| `.github/workflows/preview.yml` | **定时**（每天）打包预览版，产出 Artifact，不建 Release |
| `.github/inno/F HamLog 2.iss` | CI 专用 Inno Setup 脚本（版本号/包名等由命令行注入） |

本地打包主程序（命令见 [`打包.txt`](打包.txt)），使用 **Nuitka**：

```bash
nuitka --standalone --output-filename="F HamLog 2" --main=main.py \
  --windows-icon-from-ico=file\F_HamLog.ico --msvc=latest \
  --windows-console-mode=disable --enable-plugin=pyside6 \
  --include-package=skyfield --include-package-data=skyfield \
  --include-package=numpy --include-module=remote_crypto \
  --windows-uac-admin --include-data-dir=file=file/
```

> [!CAUTION]
> 打包**必须**带上 `--include-package-data=skyfield` 与 `--include-data-dir=file=file/`，
> 否则星历数据与图标会在运行时缺失。

独立服务端的打包命令见 `F_HamLog_Remote_Log_Server_2.0.0/打包-服务端.txt`。
若你改动了 `remote_*` 协议或密码学，**必须同步三处副本并重新打包服务端**。

---

## 数据文件与安全

- 仓库内 `file/project_backup.fhl`、`file/amateur.tle` 等可能包含**真实数据**，请勿当作测试 playground。
  跑测试前先备份字节，结束时还原。
- **以下内容绝不入库**（已被 `.gitignore` 忽略，请勿强行提交）：
  - `file/keys/`、`keys/`、`*.fhlkey`（长期私钥）
  - `file/known_server_keys.txt`（信任库）
  - `F_HamLog_Remote_Log_Server_2.0.0/{keys/, main.fhl, password_xml.txt}`
  - `file/remote_rooms/`（会话日志）
- 若你**发现安全漏洞**，请参考 [SECURITY.md](SECURITY.md)，**不要**在公开 issue 中披露细节。

---

## 许可证

本项目采用 **GNU General Public License v3.0**，详见 [LICENSE](LICENSE)。
你提交的贡献将被视为在相同许可证下授权给本项目。

---

再次感谢你的贡献！如有疑问，欢迎在 issue 中提出。73！📻

---
---

# Contributing to F HamLog

> **Language:** [中文](#为-f-hamlog-贡献力量) · English

First of all, thank you for taking the time to contribute to F HamLog (Amateur Radio QSO Log)! 🎉

Whether you report a bug, suggest a new feature, improve the documentation, or submit code directly, every bit of help makes this project better.

This document explains **how to contribute** and **how the project is organized**. Please take a few minutes to read it before you start — it will make your contribution easier to accept and help you avoid common pitfalls.

---

## Table of Contents

- [Ways to Contribute](#ways-to-contribute)
- [Code of Conduct](#code-of-conduct)
- [Reporting Issues and Suggestions](#reporting-issues-and-suggestions)
- [Setting Up the Development Environment](#setting-up-the-development-environment)
- [Project Structure](#project-structure)
- [Core Architecture](#core-architecture)
- [Coding Conventions](#coding-conventions)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Packaging and Release](#packaging-and-release)
- [Data Files and Security](#data-files-and-security)
- [License](#license)

---

## Ways to Contribute

You don't have to be an expert programmer to help. All of the following are equally valuable:

| Way | Description |
| --- | --- |
| 🐞 **Report a Bug** | File an issue using the [Bug report template](.github/ISSUE_TEMPLATE/bug_report.md) |
| 💡 **Suggest a Feature** | File an issue using the [Feature request template](.github/ISSUE_TEMPLATE/feature_request.md) |
| 📝 **Improve Docs** | Fix mistakes or add explanations in the README / this document |
| 🔌 **Write Plugins** | Write `.fhlpypack` plugins for F HamLog (see [README](README.md#plugin-development)) |
| 🧑‍💻 **Submit Code** | Fix bugs, implement features, optimize performance, refactor |
| 🌏 **Translate / Localize** | Improve UI text and language files |
| ⭐ **Feedback & Spread the Word** | Star the repo, share it with other hams |

> [!IMPORTANT]
> **Do not carry out large-scale refactoring or renaming without prior discussion.** Such changes have a wide impact and a high review cost. Please discuss the approach in an issue first and reach agreement before starting.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct (CODE_OF_CONDUCT.md)](CODE_OF_CONDUCT.md).
Please stay friendly and respectful in all interactions (issues, PRs, discussions).

---

## Reporting Issues and Suggestions

Before filing an issue, please search [existing issues](https://github.com/Mubi-Baihua/F_HamLog/issues) to avoid duplicates.

When reporting a bug, **provide reproducible information whenever possible** — it dramatically speeds up diagnosis:

- The **F HamLog version** you use (stable / preview, and the version number)
- Your **operating system** (e.g. Windows 11 23H2) and whether you are in **dark mode**
- **Steps to reproduce** (from launching the app to the error, step by step)
- **Expected behavior** vs. actual behavior
- **Screenshots / screen recordings** (strongly recommended for UI issues)
- Any **error messages or logs**

For feature suggestions, please explain: **what problem you want to solve**, the interaction you expect, and any alternatives you have considered.

> [!WARNING]
> Please **do not paste any keys, passwords, contents of `file/keys/`, or private QSO records** in your report. These are sensitive data (see [Data Files and Security](#data-files-and-security)).

---

## Setting Up the Development Environment

### Prerequisites

- **Python 3.13** (the project currently develops/packages with 3.13.x)
- **Windows** (the release target; the UI is built on PySide6 and can run cross-platform, but this is not guaranteed)
- **Git**

### Installing Dependencies

The third-party dependency list is in [`第三方模块.txt`](第三方模块.txt) at the repo root:

```text
pyside6
pandas
openpyxl
nuitka
skyfield
numpy
cryptography
matplotlib
```

Using a virtual environment is recommended (the repo uses `.venv/`, which is ignored by `.gitignore`):

```bash
python -m venv .venv
# Windows (Git Bash)
.venv/Scripts/python.exe -m pip install -r 第三方模块.txt
```

> Running the app itself only requires `pyside6`, `skyfield`, `numpy`, `cryptography`, `openpyxl`, and `pandas`.
> `nuitka` is only needed for packaging, and `matplotlib` is currently not referenced by the core code.

### Running

```bash
.venv/Scripts/python.exe main.py
```

The main window will appear. Runtime data (logs, ephemeris cache, settings) is read from and written to the `file/` directory under the repo root by default.

---

## Project Structure

```
F_HamLog/
├── main.py                     # Entry point: main menu window
├── project.py                  # [Core] main QSO log window (largest, most complex)
├── batch_project.py            # Batch-record window
├── set.py                      # Settings window (also the entry to several sub-windows)
│
├── satellite_window.py         # Satellite pass prediction window
├── mutual_window.py            # Mutual-pass prediction window (satellites visible to two locations)
├── satellite_map_window.py     # Satellite map window (includes world map rendering)
├── satellite_pred.py           # [Core] astronomy/orbit computation (SGP4, elevation/azimuth, passes)
├── satellite_auto_update.py    # Scheduled TLE (ephemeris) auto-update at startup
├── tle_source_window.py        # Ephemeris data-source manager window
│
├── remote_server.py            # Multi-user log server engine (pure standard library)
├── remote_crypto.py            # Multi-user log cryptography (X25519 + HKDF + AES-GCM)
│
├── theme.py                    # Theme system: light/dark/follow-system (single source of color)
├── toast_tip.py                # Lightweight non-modal toast (action feedback)
├── call_upper.py               # Auto-uppercase callsigns (table delegate)
├── dialog_defaults.py          # Default directory for file dialogs (Desktop)
│
├── fhl_rw.py                   # .fhl file read/write (JSON + optional encryption)
├── fhl_aes.py                  # AES-GCM encryption/decryption (password-based log encryption)
├── backup.py                   # Auto-backup of unsaved content and close guard
│
├── input_adi.py                # Import from ADI (ADIF)
├── input_fhl.py                # Import from FHL
├── input_HAM_tolls.py          # Import from "HAM personal tools"
├── export_adi.py               # Export ADIF (for TQSL / LoTW signing)
├── output_adi.py               # Export ADI
├── output_excel.py             # Export to an Excel spreadsheet
├── pack_set.py                 # Plugin runtime helper (detects system Python, etc.)
│
├── file/                       # Runtime data (see below)
├── test/                       # Offscreen smoke tests and probe scripts
├── .github/
│   ├── workflows/              # GitHub Actions: main.yml (release), preview.yml (preview)
│   ├── ISSUE_TEMPLATE/         # Issue templates
│   └── inno/                   # CI-only Inno Setup script + Chinese language file
├── F HamLog 2 Inno Setup/      # Locally built installer artifacts
├── 兼容版/                     # Per-version "compatible" zip artifacts
├── F_HamLog_Remote_Log_Server_2.0.0/   # Standalone server (bundles remote_* copies, see below)
├── README.md / CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / LICENSE
└── 打包.txt / 第三方模块.txt / #remote_project.py
```

### Main Module Responsibilities

| Module | Responsibility | Notes |
| --- | --- | --- |
| `main.py` | Entry point, main menu, startup recovery/cleanup | Window strong references are declared at module level |
| `project.py` | Main log window, table, multi-user log client | Most core and largest; change with care |
| `satellite_pred.py` | All astronomy computation | `skyfield` + `numpy`, runs offline |
| `theme.py` | Color source for the whole UI | **Never hardcode colors in other modules** |
| `fhl_rw.py` | `.fhl` read/write | Must write in one shot; do not use `json.dump` |
| `remote_server.py` / `remote_crypto.py` | Multi-user log server and cryptography | Pure standard library / `cryptography` |
| `test/` | Offscreen GUI smoke tests | Naming conventions in [Testing](#testing) |

### Other Directories

- **`file/`** — runtime data directory: logs, ephemeris cache (`amateur.tle`), settings (`m_xml.txt`),
  TLE sources (`tle_sources.txt`), map markers, keys (`keys/`), etc. **Some of it is real user data — do not modify it casually.**
- **`F HamLog 1` ~ `F HamLog 2.1`** — historical version snapshots, archived only; not part of the build.
- **`#remote_project.py`** — a historical backup file (name starts with `#`); currently referenced by no code — do not modify.
- **`F_HamLog_Remote_Log_Server_2.0.0/`** — a standalone, distributable server. **It bundles its own copies of
  `remote_server.py` / `remote_crypto.py`**, so if you change the protocol or cryptography you must **keep three
  copies in sync** (repo root + that directory + the packaging script).

---

## Core Architecture

### Data Format

- **`.fhl` files** = UTF-8 **JSON**, containing a `list[dict]` where each dict is one QSO record.
- Field definitions are in [the FHL file format section of the README](README.md#fhl-file-format) (e.g. `date` / `m_call` /
  `o_call` / `freq` (uplink) / `freq_rx` (downlink) / `sat_name` / `notes`).
- Logs can optionally be encrypted with a password using **AES-GCM** (see `fhl_aes.py`).
- The **settings file** `file/m_xml.txt` is a dict parseable with `eval`; when reading it, **always use `.get(...)`**.

### UI Conventions

- Everything is built on **PySide6**, keeping the **system-native** style (Windows 11).
- **Colors are taken only from `theme.py`**, and the UI must support both light and dark. **Verify colors by reading
  rendered pixels** (`widget.grab()`), not just `palette()`.
- File dialogs **always use the native** `QFileDialog.getOpenFileName / getSaveFileName`, defaulting to the Desktop
  (`dialog_defaults.desktop_dir()`).
- Use `toast_tip.show_toast(...)` for result/feedback toasts; keep dialogs for confirmations, format errors,
  encryption/decryption, etc.

### Multi-user Log (Remote / LAN)

- The server speaks first (sends `HELLO`), the client replies with `HELLO_ACK`; the first connection requires
  **verifying the key fingerprint** (TOFU).
- The password is used only for authentication; a session key is generated randomly, distributed via ECDH, and used
  to symmetrically encrypt every frame.
- The key root directory is determined by an explicit `key_dir` (embedded server → `file/keys/`; standalone server →
  the program directory's `keys/`).
- **These keys and trust records must never be committed** (see [`.gitignore`](.gitignore)).

---

## Coding Conventions

The project does not use an automatic formatter — please **follow the existing style**:

1. **Language & naming**: use Chinese or clear English for UI text, comments, and variable names; avoid meaningless English suffixes.
2. **Theme**: **never hardcode UI colors in any module** — always take colors from `theme.py` so light/dark stay consistent.
3. **File dialogs**: for any new open/save dialog, use the native `QFileDialog` static methods with the default directory from `dialog_defaults`.
4. **QSS `background-color` is written back into the widget's palette** — when sampling colors, read from an unstained parent/sibling widget.
5. **Performance**: with tens of thousands of rows, **never use per-row `setCellWidget`** — use a custom delegate; keep the checked state authoritative in a closure set.
6. **Persistence**: writing `.fhl` must `json.dumps` and then `f.write` in one shot — **do not use `json.dump`**.
7. **Comments**: for unconventional implementations, explain "why" (many pitfalls already have precedent — don't make successors repeat them).
8. **Commit messages**: use short Chinese descriptions that explain the change (follow the existing style in `git log`).

> [!TIP]
> Before changing anything, run `git log` / read the relevant module comments — many "seemingly redundant" patterns are actually fixes for past pitfalls.

---

## Testing

The project uses **offscreen GUI smoke tests** to verify real window behavior. All test scripts live in the `test/` directory.

Naming conventions:

| Prefix | Purpose |
| --- | --- |
| `__*_smoke.py` / `test_*_smoke.py` | Smoke tests: build windows, click buttons, read tables, assert |
| `__*_probe.py` | Probes: inspect a specific behavior/value |
| `test_*.py` | Other tests |
| `__*_out.txt` / `__*_out.png` | Test output (ignored by `.gitignore`) |

How to run (key: specify the offscreen platform):

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe test/__toast_smoke.py
```

When writing tests, please note:

- The script should add the **repo root** to `sys.path` via `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`.
- **Prefer monkeypatching path constants to temp files** (e.g. `satellite_pred.TLE_SOURCES_PATH`, `smw.MARKERS_PATH`) to avoid polluting real data.
- **Never run `git checkout --` on files under `file/` to restore them** (the user may be using them); check and restore manually after testing.
- If a prompt has been changed from `QMessageBox` to `toast_tip.show_toast`, the test must also monkeypatch `toast_tip.show_toast`.
- `sys.exit()` inside a slot is caught at PySide6's C++ boundary and terminates the process directly; before testing, set `sys.exit = lambda *a, **k: None`.

Before submitting code, please **run at least the smoke tests related to your change** and make sure they pass.

---

## Submitting a Pull Request

1. **Fork** this repository and create your working branch from `develop` (`develop` is the development branch, `main` is stable).
2. Keep changes **focused**: one PR solves one problem; do not mix in unrelated formatting or renames.
3. Make sure it **passes locally** (see [Testing](#testing)), and add tests where needed.
4. Update related documentation (README / this document / code comments).
5. When opening the PR, explain: **what changed, why, and how to verify it**, and link the related issue (e.g. `Closes #123`).
6. Wait patiently for review and revise based on feedback.

> [!NOTE]
> Branch strategy: feature development is merged into `develop`; `main` is used to publish stable releases.

---

## Packaging and Release

Releases are automated by GitHub Actions. Related files:

| File | Purpose |
| --- | --- |
| `.github/workflows/main.yml` | **Manual** release: build → generate installer → compatible zip → write back to branch → publish Release (draft by default) |
| `.github/workflows/preview.yml` | **Scheduled** (daily) preview build, produces an Artifact, no Release |
| `.github/inno/F HamLog 2.iss` | CI-only Inno Setup script (version/name etc. injected via the command line) |

Building the main program locally (command in [`打包.txt`](打包.txt)) uses **Nuitka**:

```bash
nuitka --standalone --output-filename="F HamLog 2" --main=main.py \
  --windows-icon-from-ico=file\F_HamLog.ico --msvc=latest \
  --windows-console-mode=disable --enable-plugin=pyside6 \
  --include-package=skyfield --include-package-data=skyfield \
  --include-package=numpy --include-module=remote_crypto \
  --windows-uac-admin --include-data-dir=file=file/
```

> [!CAUTION]
> Packaging **must** include `--include-package-data=skyfield` and `--include-data-dir=file=file/`,
> otherwise the ephemeris data and icons will be missing at runtime.

The standalone server build command is in `F_HamLog_Remote_Log_Server_2.0.0/打包-服务端.txt`.
If you change the `remote_*` protocol or cryptography, **you must keep the three copies in sync and rebuild the server**.

---

## Data Files and Security

- `file/project_backup.fhl`, `file/amateur.tle`, etc. may contain **real data** — do not treat them as a test playground.
  Back up the bytes before running tests and restore them when done.
- **Never commit the following** (already ignored by `.gitignore`; do not force-add them):
  - `file/keys/`, `keys/`, `*.fhlkey` (long-term private keys)
  - `file/known_server_keys.txt` (trust store)
  - `F_HamLog_Remote_Log_Server_2.0.0/{keys/, main.fhl, password_xml.txt}`
  - `file/remote_rooms/` (session logs)
- If you **find a security vulnerability**, refer to [SECURITY.md](SECURITY.md) and **do not** disclose details in a public issue.

---

## License

This project is licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE).
Your contributions are considered licensed to this project under the same license.

---

Thank you again for your contribution! If you have any questions, feel free to ask in an issue. 73! 📻
