# F HamLog 安装器 · 开发者说明

一个独立的小工具：**装最新版 F HamLog**、**按需下载指定版本**（命令行可用
`download --all` 整批收），顺手把 GitHub 的访问加速带上。界面是 PySide6，命令行是同一个内核。

它不是主程序的一部分，但**下载与安装这两步刻意不自立门户** —— 全部复用
`src/f_hamlog/check_update.py`。理由很实在：那套「动态分块并行 + 镜像测速择优 +
走镜像后抽样比对官方字节 + 失败退回单线程」调过好几轮，抄一份到这边，改一处忘一处，
很快就变成两个脾气不同的下载器。

---

## 一、它和主程序是什么关系

| 事情 | 谁负责 | 说明 |
| --- | --- | --- |
| 下载安装包 | `f_hamlog.check_update.download()` | 分段并行、镜像、校验、失败降级 |
| 启动安装包 | `f_hamlog.check_update.run_installer()` | `/SILENT /CLOSEAPPLICATIONS /NORESTART` |
| 版本列表 | 本包 `github.py` | `api.github.com` 不在 check_update 的镜像名单里，只能自己走 |
| 挑哪个文件 | 本包 `releases.py` | 仓库里还躺着服务端 exe、便携 zip、1.x 的「壳」setup |
| 存放与记账 | 本包 `download.py` | 按版本分目录 + `manifest.json` |

**硬约定**：`check_update.py` 仍然只有一份。安装器要的行为差异通过参数表达
（`download(..., prefer='mirror'|'direct')`），不在那边写死「安装器专用」的分支。

---

## 二、模块职责

```
src/f_hamlog_installer/
├── __init__.py     版本号（__version__）+ 这个包干什么
├── __main__.py     python -m 入口：无参数开界面，有参数走命令行
├── config.py       仓库/接口地址、默认目录、环境变量名
├── github.py       版本列表接口：直连 → 镜像回退 → 本地缓存
├── releases.py     整理版本、排序、挑安装包（setup / msi / 服务端 / 便携）
├── download.py     下载计划、跳过已完成、manifest 记账、校验
├── install.py      拉起安装包（复用 check_update.run_installer）
├── cli.py          命令行：list / latest / download / install / verify / cache
├── gui.py          Qt 界面：版本表、进度、加速设置、关于页
└── README.md       本文件（只给开发者看，界面不读它）
```

依赖方向是单向的：`gui.py` / `cli.py` → `download.py` → `check_update.py`。
**`download.py` 以下不许 import Qt**：这样命令行、离屏测试、以后打控制台版 exe
都不必拖着一整个 GUI 栈。

---

## 三、跑起来

图形界面（默认）：

```bat
set PYTHONPATH=%CD%\src
.venv\Scripts\python.exe -m f_hamlog_installer
```

界面两个页：

* **版本列表** —— 全部版本、类型、大小、发布日期、本地状态；左上角**蓝底的
  「下载并安装最新版」**是主操作（`AccentButton` 用系统强调色填充，深浅色都跟系统走），
  一步下载 + 静默安装，「下载所选」只收包，**界面上不提供「下载全部版本」**
  （一次几十个包、好几 GB，误点代价太大；要整批收在命令行用 `download --all`），
  「删除本地包」把选中版本的
  本地文件和 manifest 记录一起删掉（不弹确认 —— 删的是能重下的缓存，状态栏回报删了
  几个、释放多少）；表格**只选格子不整行刷蓝**，选中哪一版，下面的「发布说明」就把
  该版 release 正文整段渲染出来（Markdown，长文滚动，不摘要不截断，默认占窗口下半部
  约三分之一，可拖动分隔条）；顶部可切换加速方式、存放目录、填 token（旁边「这是什么」
  有完整说明）。
* **关于** —— 反馈邮箱、版本更新页、GitHub 仓库、安装器版本和 `Coded by BI8SQL`，
  与主程序设置页底部是同一套信息（链接色取系统调色板的 Link 角色，深浅色都跟系统走）。

> 界面里**没有**「只用本地缓存」开关：10 分钟内的缓存本来就直接用，再摆一个开关只会
> 让人以为不勾就会一直联网。命令行仍保留 `--offline`（CI / 断网排查用）。

命令行（带参数就走命令行，一次都不会弹窗）：

```bat
python -m f_hamlog_installer list
python -m f_hamlog_installer latest
python -m f_hamlog_installer install 2.9.1 --yes
python -m f_hamlog_installer download --all
python -m f_hamlog_installer download 2.9.1 v1.0.0 --mirror on
python -m f_hamlog_installer verify
python -m f_hamlog_installer cache clear
```

| 命令 | 做的事 |
| --- | --- |
| `list` | 列全部版本：类型、大小、发布日期、本地有没有 |
| `latest` | 只看最新正式版 |
| `download [版本...]` | 下指定版本；不带参数=最新，`--all`=全部，`--dry-run`=只列计划 |
| `install [版本]` | 下完就装；`--gui` 走向导，默认静默；`-y` 不再确认 |
| `verify` | 按 manifest 核对本地安装包（大小 + 摘要） |
| `cache show\|clear` | 看/清版本列表缓存 |

`--mirror auto|on|off`、`--out DIR`、`--token`、`--offline`、`--refresh`
这五个既是全局选项，也能写在子命令后面（子命令里的默认值用 `SUPPRESS`，
不会把前面写的值顶掉）。

---

## 四、目录与环境变量

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `F_HAMLOG_RELEASES_DIR` | 历史版本存放目录 | `%LOCALAPPDATA%\F_HamLog\releases` |
| `F_HAMLOG_INSTALLER_CACHE` | 版本列表缓存目录 | `%LOCALAPPDATA%\F_HamLog\installer\cache` |
| `GITHUB_TOKEN` / `GH_TOKEN` | 提高接口额度（60/小时 → 5000/小时） | 空 |

落盘结构：

```
releases/
├── 2.9.1/F.HamLog.2.9.1.setup.exe
├── 1.9.0/F.HamLog.1.9.msi
└── manifest.json
```

1.4～1.9 的安装包**全叫 `setup.exe`**，所以必须按版本分目录，否则互相覆盖。
manifest 用「版本/文件名」当键，记大小、sha256、来源地址、下载时间。

---

## 五、GitHub 加速是怎么做的

分两层，别混：

**1) 安装包本体** —— 交给 `check_update.choose_source()`：
直连和 4 个镜像同时跑同一个测速窗口，镜像只有比直连快 30% 才换；
走了镜像，下完还会跟官方地址抽样比对头/中/尾三块字节，被替换的内容会被发现并回退直连。

**2) 版本列表（api.github.com）** —— `github.py` 自己走一遍：
镜像都是「前缀式」代理，把原始 URL 拼在镜像地址后面即可。能通的镜像会被记住
（`_sticky`），后续请求先试它，省掉「每次都从头失败一遍」的几秒钟。

镜像名单**只有一处**：`check_update.MIRROR_PREFIXES`。要加镜像改那里就够，
安装器这边用 `mirror_prefixes()` 现取，不抄常量。

三种模式：

* `auto`（默认）—— 测速择优；
* `on` —— 强制走镜像（仍挑最快的、仍要求支持 Range）；
* `off` —— 只用直连，**一个探测请求都不发**（排查网络时最干净）。

缓存：版本列表存一份 JSON，10 分钟内直接复用；断网/被墙时 `--offline` 也能用它
列出全部版本、把没下完的补齐 —— 只有 `download` 真正要新版本信息时才会联网。

---

## 六、版本与安装包的判定

* **排序**：`tag_name` 去掉 `v` 前缀后转成数字元组，`v1.0.0` 和 `1.0.0` 等价；
  认不出的排最后（但保留，不丢版本）。
* **最新**：非 draft、非 prerelease 里版本号最大的那个；一个正式版都没有才退回预览版。
* **哪些是客户端安装包**：
  * 名字里带 `remote` / `server` 的**不是**（仓库里一直挂着服务端 exe）；
  * `.zip` 是免安装版，默认不下（`--assets all` 也不含 zip）；
  * 1.x 的 `setup.exe` 只有 550 KB，那是**联网下载器的壳**，真正的完整包是同版本的
    `msi`（33～64 MB）—— 所以 2.x 挑 setup，1.x 自动改挑 msi；
  * 判错只会多下一次或少下一次，不会下成别的软件。

---

## 七、下载与记账

* 本地已有**大小一致**的文件就跳过（不联网、不重下 70 MB），`--force` 才重下；
* `check_update.download()` 一律以 `force=True` 调用：那边认包看的是「exe 名称 +
  全局缓存目录」，这里是一个版本一个目录，让它再插一手反而会拿到
  `%LOCALAPPDATA%\F_HamLog\update` 里别的版本的包；
* 下完核对字节数，对不上立刻删掉重来，不把半截文件留给下一次；
* manifest 每下完一个文件就落盘一次，进程被 Ctrl+C 掐掉也不会丢记账；
* **GitHub 不给官方 sha256**，摘要只能「自证」——首次下载后记下，之后 `verify`
  用它对本地文件。它能发现磁盘损坏/被替换，不能证明发布者身份。

---

## 八、安装

`install.run()` 按扩展名分两路：

* **Inno Setup exe（2.x）** → `check_update.run_installer()`：`/SILENT
  /CLOSEAPPLICATIONS /NORESTART`，只藏「下一步」，仍有进度窗；
* **msi（1.x）** → `msiexec /i <包> /qb /norestart`。直接把 .msi 交给 `Popen`
  会报「不是有效的 Win32 应用程序」，必须由 Windows Installer 服务解释；
  `/qb` 是「基本界面 + 进度条」，比 `/qn` 全静默更容易看出卡在哪。

有两个参数**看着有用、实际不能用**，别再往里加：

* `/SUPPRESSMSGBOXES`：Inno 在「已装版本比本包新」时会弹「另一个版本已安装，是否
  继续」，抑制消息框会按默认值答「否」并直接退出（码 2），用户只看到「什么都没发生」；
* `/LOG=<路径>`：Inno 的 `/LOG=` **不吃引号**，而 `subprocess` 给含空格的参数会自动
  加引号 → Inno 把引号当成文件名的一部分，直接弹
  「Error creating log file: 文件名、目录名或卷标语法不正确」并中止安装。
  要排查就走完整向导（`--gui` 或界面上的「改用安装向导」），错误显示在安装器界面上。

UAC 都由安装程序自己申请，**这里不额外提权** —— 双重提权会被系统拒绝。只有
`Popen` 抛 `WinError 740`（清单要求管理员、进程拿不到提升）时才退回
`ShellExecuteExW(verb="runas")`，让 shell 去提权并把退出码取回来。

`--gui` 走完整向导（要改安装路径时用）；`--no-wait` 拉起就返回；默认等结束并回报
退出码（`install.code_text()` 把 1/1602/1603/1618/1638/3010/1223 翻成人话，
3010 算成功但需要重启，1223 是 UAC 被取消）。

**界面一律在后台线程里等**（`_InstallThread`）：在界面线程里 `wait()`，UAC 一弹
窗口就假死。等回来再按退出码给结论 —— 以前 `wait=False`、不看返回码，用户只能看到
「已启动」，装没装上无从判断。失败时弹框说明常见原因（UAC 没点「是」、被安全软件拦、
包不完整），并可直接「改用完整安装向导」再试，真实错误会显示在安装器自己的界面上。

安装前会读注册表卸载项，若本机已装同一版本，确认框里先说明「继续是覆盖安装，
用户数据不会被删」，避免用户以为重复安装会清掉日志。

注意 `/SILENT` 遇到「完成」页或重启提示仍可能停下，所以自动安装别指望它一定 0 秒返回。

---

## 九、打成 exe

```bat
set PYTHONPATH=%CD%\src
.venv\Scripts\python.exe -m nuitka --standalone --enable-plugin=pyside6 ^
  --windows-console-mode=disable --output-folder-name=installer ^
  --include-package-data=f_hamlog_installer ^
  src\f_hamlog_installer\__main__.py
```

几个已经在主程序上踩过的坑，这里同样适用：

* **必须给 `PYTHONPATH=<repo>\src`**，否则打出空壳 exe（打包成功 ≠ 产物可用）；
* **不要写 `--include-module=包.模块`**（点分名会 FATAL），靠 import 自然收进来；
* 产物目录用 `--output-folder-name` 固定，后续脚本/安装器别去猜名字；
* `--include-package-data` 只是为了把 `README.md` 一起带走（当文档分发）；界面不读它，
  不带也不会影响「关于」页。

---

## 十、开发约定

1. **不要在 `download.py` 以下 import Qt**；命令行与 GUI 共用同一个内核。
2. **不要在 `check_update.py` 里加「安装器专用」分支**。要差异就传参
   （`prefer`）——那边的默认行为必须仍然是主程序自己的行为。
3. **镜像名单只有一个出处**（`MIRROR_PREFIXES`）；新增加速站点先在那里加，
   再回来更新本文件第五节的说明。
4. **不猜版本**：用户给的版本号对应多个 tag 时报错并列出候选，别自作主张。
5. **界面不写死颜色**：用系统调色板与语义控件（`QLabel` 的 `PlaceholderText` 角色、
   链接色），深浅色主题都不会出现「深底深字」。也不上全局 QSS、不用 Fusion。
6. **表格列显式设宽**，不启用 `stretchLastSection`，不逐行塞 `setCellWidget`。
7. **改完跑一遍冒烟**（不需要真下载，别浪费流量）：

```bat
set PYTHONPATH=%CD%\src
python -m f_hamlog_installer list
python -m f_hamlog_installer download --all --dry-run
python -m f_hamlog_installer install --dry-run
python -m f_hamlog_installer verify
```

真实下载拿最小的历史版本试（1.x 的 msi 30 MB 上下）：

```bat
python -m f_hamlog_installer download v1.0.0 --out %TEMP%\fhl_test
```

---

## 十一、已知边界

* 未登录 GitHub 接口 60 次/小时；`--all` 一次就翻 3 页左右，正常够用；
  反复调试请 `--offline`（走缓存）或配 `GITHUB_TOKEN`。
* GitHub 不给官方摘要，「已下载」状态只按大小判断；要绝对把握就跑 `verify`。
* 1.x 的 550 KB `setup.exe` 会自动换成 msi；如果你**确实**要那个壳，
  用 `download 1.9.0 --assets all`。
* 安装包要管理员权限；标准用户会看到 UAC，拒绝则安装不会开始（退出码非 0）。
