# -*- coding: utf-8 -*-
"""Qt 图形界面：版本表、加速设置、下载进度、开发者说明。

这里只做「把内核摆出来」的事：下载、记账、安装全在 ``download.py`` /
``install.py`` 里。界面本身不联网、不写安装包，只读/写一份自己的偏好设置。

**颜色一律走系统调色板**：不写 QSS、不写死色值、不用 Fusion，次要文字用
``QPalette.PlaceholderText`` 角色。这样浅色/深色主题下都不会出现「深底深字」，
也不需要把主程序那套主题模块拖进来（它会连带 import 星历的重依赖）。
"""

import json
import os
import sys
import threading

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
                               QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QSizePolicy, QSplitter, QStyle,
                               QStyleOptionButton, QTabWidget, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from f_hamlog import bg_thread
from f_hamlog import check_update as cu

from . import __version__, config, download, github, install, releases

PREFS_NAME = 'gui.json'

# 列宽写死：不启用 stretchLastSection，也不让 Qt 自己伸缩（列的语义是固定的）
_COLUMNS = (('版本', 110), ('类型', 90), ('大小', 110), ('发布', 120), ('本地', 170))

_BTN_HEIGHT = 32                 # 按钮行统一高度：主按钮高一档才不显得参差

# 「GitHub token 是什么」的完整解释（界面上那个「这是什么」按钮弹它）
_TOKEN_HELP = """\
**GitHub token 是一串个人访问令牌**（Personal Access Token），相当于给这个安装器
办的一张只读门禁卡：GitHub 看到它就知道请求来自你，给的接口额度更高。

**为什么会有这个输入框**

安装器要读本仓库的版本列表。GitHub 对未登录调用限制为每小时 60 次，反复点
「刷新列表」很容易用完，界面就会提示接口报错。填了 token 之后是每小时 5000 次。

**要不要填**

一般不用填。只有反复刷新、真的遇到「接口额度用尽」时，再去申请一个。

**怎么弄（约 1 分钟）**

1. 打开 <https://github.com/settings/tokens>
2. 点 Generate new token → Generate new token (classic)
3. Note 随便填；Expiration 选 7 天；Scopes 一个都不用勾
   （读公开仓库不需要任何权限）
4. 生成后复制那串 ghp_ 开头的字符，粘贴到输入框

**注意**

* token 等同于密码，不要发给别人；
* 本安装器只把它放在内存里，关掉窗口就没了，不会写进任何文件；
* 如果填了 token 仍然报额度问题，多半是 token 过期了，重新生成一个。
"""


def _blend(a, b, t):
    """把颜色 ``a`` 往 ``b`` 混 ``t``（0~1）。用于悬停/按下时微调亮度。"""
    t = max(0.0, min(1.0, float(t)))
    return QColor(round(a.red() * (1 - t) + b.red() * t),
                  round(a.green() * (1 - t) + b.green() * t),
                  round(a.blue() * (1 - t) + b.blue() * t))


class AccentButton(QPushButton):
    """主操作按钮：用系统强调色填充，比旁边的普通按钮显眼。

    颜色一律从调色板取（``Accent`` 不存在时退回 ``Highlight``），文字色按底色亮度
    选黑或白 —— 浅色主题、深色主题、用户自定义强调色（黄/粉这类浅色）都读得清。
    只做悬停/按下/禁用三种状态，圆角 4px 与系统原生按钮一致，不加渐变和阴影。
    """

    RADIUS = 4

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        font = self.font()
        font.setBold(True)
        self.setFont(font)
        self.setMinimumHeight(_BTN_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def sizeHint(self):
        # 自绘不走样式的 padding，左右各留 10px，文字不会贴到圆角上
        hint = super().sizeHint()
        return QSize(hint.width() + 20, max(hint.height() + 8, _BTN_HEIGHT))

    def _accent(self):
        pal = self.palette()
        role = getattr(QPalette.ColorRole, 'Accent', None)
        colour = pal.color(role) if role is not None else QColor()
        if not colour.isValid() or colour.alpha() == 0:
            colour = pal.color(QPalette.ColorRole.Highlight)
        return colour

    @staticmethod
    def _ink(fill):
        """强调色可能是浅色，按亮度挑黑/白，保证字读得清。"""
        return QColor(0, 0, 0) if fill.lightness() > 150 else QColor(255, 255, 255)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 先让样式把控件底（窗口背景）画掉，否则圆角外会残留上一帧
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)

        fill = self._accent()
        if not self.isEnabled():
            fill = _blend(fill, self.palette().color(QPalette.ColorRole.Window), 0.55)
        elif self.isDown():
            fill = _blend(fill, QColor(0, 0, 0), 0.16)
        elif self.underMouse():
            fill = _blend(fill, QColor(255, 255, 255), 0.10)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        ink = self._ink(fill)
        if not self.isEnabled():
            ink = _blend(ink, fill, 0.45)
        painter.setPen(ink)
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())

        if self.hasFocus():
            pen_colour = QColor(ink)
            pen_colour.setAlpha(190)
            pen = QPen(pen_colour)
            pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 3, 3)


def _prefs_path():
    """偏好设置放在缓存目录的上一级（和缓存同门，不污染下载目录）。"""
    return os.path.join(os.path.dirname(config.cache_dir()), PREFS_NAME)


def read_prefs():
    try:
        with open(_prefs_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_prefs(data):
    path = _prefs_path()
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass                      # 存偏好失败不值得打扰用户


# ---------------------------------------------------------------- 后台线程

class _ListThread(bg_thread.BgThread):
    """取版本列表（联网或读缓存）。"""

    done = Signal(list)
    failed = Signal(str)

    def __init__(self, token='', refresh=False, parent=None):
        super().__init__(parent)
        self._token = token
        self._refresh = bool(refresh)

    def run(self):
        try:
            raw = github.list_releases(token=self._token, refresh=self._refresh)
            rels = releases.collect(raw)
        except Exception as e:
            self.failed.emit(str(e))
            return
        if not rels:
            self.failed.emit('没有取到任何版本（仓库地址或网络有问题）')
            return
        self.done.emit(rels)


class _DownloadThread(bg_thread.BgThread):
    """按计划逐个下载；每个文件下完就落 manifest，中途退出也不丢记账。"""

    message = Signal(str)
    progressed = Signal(int, int)
    failed = Signal(str)
    finished = Signal(int, int, int)     # (下载数, 跳过数, 失败数)

    def __init__(self, jobs, out, prefer='auto', force=False, parent=None):
        super().__init__(parent)
        self._jobs = list(jobs)
        self._out = out
        self._prefer = prefer
        self._force = bool(force)
        self._cancel = threading.Event()

    def stop(self):
        self._cancel.set()

    def run(self):
        out = self._out
        manifest = download.load_manifest(out)
        saved = skipped = failed = 0
        total = len(self._jobs)
        for index, job in enumerate(self._jobs, 1):
            if self._cancel.is_set():
                break
            rel, asset = job['release'], job['asset']
            self.message.emit('[%d/%d] %s  %s' % (index, total, rel['tag'], asset['name']))
            try:
                rec = download.download_asset(
                    asset, job['dest'], version=rel['tag'], prefer=self._prefer,
                    force=self._force, progress=self._emit_progress, cancel=self._cancel)
            except cu.Cancelled:
                break
            except Exception as e:
                failed += 1
                self.failed.emit('%s：%s' % (rel['tag'], e))
                continue
            manifest[download.record_key(rel['tag'], rec['name'])] = rec
            download.save_manifest(out, manifest)
            if rec['skipped']:
                skipped += 1
            else:
                saved += 1
        self.finished.emit(saved, skipped, failed)

    def _emit_progress(self, done, total):
        """进度回调在工作线程里，经信号转回界面线程（不在工作线程碰控件）。"""
        self.progressed.emit(int(done), int(total))


class _InstallThread(bg_thread.BgThread):
    """等安装程序退出并回报退出码。

    安装要弹 UAC、要写 Program Files、要跑几十秒到几分钟，**必须**放在后台：
    直接在界面线程里 ``wait()``，UAC 一出来窗口就假死，用户点不动也看不到进度。
    ``result`` 是退出码（``int``）或异常对象，界面按类型分开处理。
    """

    done = Signal(str, object)           # (安装包路径, 退出码 / 异常)

    def __init__(self, path, silent=True, parent=None):
        super().__init__(parent)
        self._path = str(path)
        self._silent = bool(silent)

    def run(self):
        try:
            code = install.run(self._path, silent=self._silent, wait=True)
        except Exception as e:
            self.done.emit(self._path, e)
            return
        self.done.emit(self._path, code)


# ---------------------------------------------------------------- 主窗口

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._rels = []
        self._thread = None
        self._install_thread = None
        self._busy = False
        self._label = ''
        self._install_after = None      # 下载完后要装的本地路径
        self._auto_latest = False       # 点了「安装最新版」但列表还没来
        self._speed = cu.Speedometer()
        self._eta = cu.EtaEstimator()

        self.setWindowTitle('F HamLog 安装器')
        self.resize(1000, 780)
        self._build()
        self._load_prefs()
        # 启动那次先看缓存（10 分钟内直接用），点「刷新列表」才强制联网
        self._refresh(force=False)

    # ------------------------------------------------------------ 搭建
    def _build(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(8)

        title = QLabel('F HamLog 安装器')
        font = title.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setBold(True)
        title.setFont(font)
        sub = QLabel('下载最新版并安装，或按需挑版本下载')
        sub.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        lay.addWidget(title)
        lay.addWidget(sub)

        # 第一行：加速方式 + 存放目录
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel('GitHub 加速'))
        self.cmb_mirror = QComboBox()
        self.cmb_mirror.addItem('自动择优（默认）', 'auto')
        self.cmb_mirror.addItem('强制走镜像', 'on')
        self.cmb_mirror.addItem('只用直连', 'off')
        row.addWidget(self.cmb_mirror)
        row.addSpacing(10)
        row.addWidget(QLabel('存放目录'))
        self.ed_out = QLineEdit()
        self.ed_out.setMinimumWidth(240)
        row.addWidget(self.ed_out, 1)
        btn_browse = QPushButton('浏览…')
        btn_browse.clicked.connect(self._choose_out)
        btn_open = QPushButton('打开目录')
        btn_open.clicked.connect(self._open_out)
        row.addWidget(btn_browse)
        row.addWidget(btn_open)
        lay.addLayout(row)

        # 第二行：强制重下 + token
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.ck_force = QCheckBox('已有也重新下载')
        self.ed_token = QLineEdit()
        self.ed_token.setPlaceholderText('GitHub token（可留空）')
        self.ed_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_token.setMinimumWidth(240)
        self.ed_token.setMaximumWidth(280)
        btn_token_help = QPushButton('这是什么')
        btn_token_help.setFlat(True)
        btn_token_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_token_help.clicked.connect(self._explain_token)
        row2.addWidget(self.ck_force)
        row2.addStretch(1)
        row2.addWidget(self.ed_token)
        row2.addWidget(btn_token_help)
        lay.addLayout(row2)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_versions_tab(), '版本列表')
        self.tabs.addTab(self._build_about_tab(), '关于')
        lay.addWidget(self.tabs, 1)

        bar = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setFixedWidth(240)
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.btn_cancel = QPushButton('取消')
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.hide()
        bar.addPermanentWidget(self.progress)
        bar.addPermanentWidget(self.btn_cancel)
        bar.showMessage('就绪')

    def _build_versions_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        # 主操作放最左、用强调色自绘，别的按钮都退成普通样式
        self.btn_latest = AccentButton('下载并安装最新版')
        self.btn_refresh = QPushButton('刷新列表')
        self.btn_download = QPushButton('下载所选')
        self.btn_install_sel = QPushButton('安装所选')
        self.btn_delete = QPushButton('删除本地包')
        for btn in (self.btn_refresh, self.btn_download,
                    self.btn_install_sel, self.btn_delete):
            btn.setMinimumHeight(_BTN_HEIGHT)
        self.btn_latest.setMinimumHeight(_BTN_HEIGHT)
        self.btn_refresh.clicked.connect(lambda: self._refresh(force=True))
        self.btn_latest.clicked.connect(self._install_latest)
        self.btn_download.clicked.connect(self._download_selected)
        self.btn_install_sel.clicked.connect(self._install_selected)
        self.btn_delete.clicked.connect(self._delete_local)
        bar.addWidget(self.btn_latest)
        bar.addWidget(self.btn_refresh)
        bar.addStretch(1)
        bar.addWidget(self.btn_download)
        bar.addWidget(self.btn_install_sel)
        bar.addWidget(self.btn_delete)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([name for name, _ in _COLUMNS])
        # 只选「一个格子」：点哪儿亮哪儿，不整行刷蓝。多选仍可用 Ctrl/Shift 框多个格子，
        # 需要版本时按格子所在行归并（见 _selected_rels）。
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for col, (_name, width) in enumerate(_COLUMNS):
            self.table.setColumnWidth(col, width)

        # 表格下面挂「发布说明」：选中哪一行就看哪一版的正文，Markdown 原样渲染，
        # 长文不截断（QTextBrowser 自己滚动）。默认选中最新版，一眼就能看到更新内容。
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        split.addWidget(self._build_notes_panel())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        split.setSizes([230, 330])      # 发布说明留够高度，长正文少滚动
        split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        return page

    def _build_notes_panel(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)
        self.notes_title = QLabel('发布说明')
        font = self.notes_title.font()
        font.setBold(True)
        self.notes_title.setFont(font)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(240)        # 说明区不能缩成一条缝
        self.notes.setPlaceholderText('在上面的列表里选一个版本，这里显示它完整的发布说明')
        lay.addWidget(self.notes_title)
        lay.addWidget(self.notes, 1)
        return page

    def _on_selection_changed(self):
        rels = self._selected_rels()
        self._show_notes(rels[0] if rels else None)

    def _show_notes(self, rel):
        """把选中版本的发布说明整段渲染出来（不摘要、不截断）。"""
        if rel is None:
            self.notes_title.setText('发布说明')
            self.notes.clear()
            return
        title = str(rel.get('title') or '').strip()
        head = title or rel['tag']
        if title and rel['tag'] not in title:
            head = '%s  %s' % (rel['tag'], title)
        extra = [rel.get('date') or '', '预览版' if rel.get('prerelease') else '']
        extra = [item for item in extra if item]
        if extra:
            head += '（%s）' % ' · '.join(extra)
        self.notes_title.setText(head)

        body = str(rel.get('notes') or '').strip()
        if not body:
            self.notes.setPlainText('这个版本没有写发布说明。')
            return
        self.notes.setMarkdown(body)

    def _build_about_tab(self):
        """「关于」页：与主程序设置页底部同一套信息（反馈邮箱 / 更新页 / 仓库 / 版本 /
        Coded by），不渲染任何 markdown —— 那些是给开发者的文件，不该塞进窗口。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)

        self.about_links = QLabel()
        self.about_links.setTextFormat(Qt.TextFormat.RichText)
        self.about_links.setOpenExternalLinks(True)
        self.about_links.setText(self._about_html())
        lay.addWidget(self.about_links)

        lay.addWidget(self._hline())
        lay.addWidget(QLabel('F HamLog 安装器 版本：%s' % __version__))
        lay.addWidget(self._hline())
        lay.addWidget(QLabel('Coded by BI8SQL'))
        lay.addStretch(1)
        return page

    def _about_html(self):
        """链接色取当前调色板的 Link 角色：深浅色都跟着系统走，不写死 #0066cc。"""
        link = self.palette().color(QPalette.ColorRole.Link).name()
        return ('<html><head/><style>'
                'a {text-decoration: none; color: %s;}'
                '.t {margin-top: 5px;}'
                '</style></head><body>'
                '<div class="t">问题反馈到：BI8SQL@outlook.com</div>'
                '<div class="t">项目网址：'
                '<a href="https://mubi-baihua.pages.dev/f_hamlog.html">'
                'https://mubi-baihua.pages.dev/f_hamlog.html</a></div>'
                '<div class="t">Github项目：'
                '<a href="https://github.com/Mubi-Baihua/F_HamLog/">'
                'https://github.com/Mubi-Baihua/F_HamLog/</a></div>'
                '</body></html>') % link

    def _hline(self):
        """分隔线：与主程序一样用 Sunken 的 HLine，不画 QSS 边框。"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setLineWidth(1)
        return line

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'table'):
            self._fit_columns()

    def changeEvent(self, event):
        # 系统深浅色切换时链颜色要跟着变（HTML 里的颜色是写死的字符串，不会自动跟）
        if event.type() == QEvent.Type.PaletteChange:
            label = getattr(self, 'about_links', None)
            if label is not None:
                label.setText(self._about_html())
        super().changeEvent(event)

    # ------------------------------------------------------------ 偏好
    def _load_prefs(self):
        prefs = read_prefs()
        self.ed_out.setText(str(prefs.get('out') or config.out_dir()))
        index = self.cmb_mirror.findData(str(prefs.get('mirror') or 'auto'))
        self.cmb_mirror.setCurrentIndex(index if index >= 0 else 0)
        self.ck_force.setChecked(bool(prefs.get('force')))

    def _save_prefs(self):
        write_prefs({
            'out': self.ed_out.text().strip(),
            'mirror': self.cmb_mirror.currentData() or 'auto',
            'force': self.ck_force.isChecked(),
        })

    def _out_dir(self):
        return os.path.abspath(self.ed_out.text().strip() or config.out_dir())

    def _prefer(self):
        return {'auto': 'auto', 'on': 'mirror', 'off': 'direct'}.get(
            self.cmb_mirror.currentData() or 'auto', 'auto')

    def _choose_out(self):
        folder = QFileDialog.getExistingDirectory(self, '选择存放目录', self._out_dir())
        if folder:
            self.ed_out.setText(os.path.abspath(folder))
            self._save_prefs()
            self._fill_table()

    def _open_out(self):
        folder = self._out_dir()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, '打不开目录', str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _explain_token(self):
        """「这是什么」——长解释放独立对话框，主界面只留一个输入框。"""
        dlg = QDialog(self)
        dlg.setWindowTitle('GitHub token 是什么')
        dlg.resize(560, 440)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser(dlg)
        view.setOpenExternalLinks(True)
        view.setMarkdown(_TOKEN_HELP)
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton('知道了')
        ok.setDefault(True)
        ok.clicked.connect(dlg.accept)
        row.addWidget(ok)
        lay.addLayout(row)
        dlg.exec()

    # ------------------------------------------------------------ 列表
    def _refresh(self, force=False):
        if self._busy:
            return
        self._begin('正在获取版本列表…', progress=False)
        self._thread = _ListThread(token=self.ed_token.text().strip(), refresh=force)
        self._thread.done.connect(self._on_list_done)
        self._thread.failed.connect(self._on_list_failed)
        self._thread.start()

    def _on_list_done(self, rels):
        self._rels = list(rels)
        self._fill_table()
        self._end('共 %d 个版本' % len(self._rels))
        if self._auto_latest:
            self._auto_latest = False
            self._install_latest()

    def _on_list_failed(self, message):
        self._auto_latest = False
        self._end('获取版本列表失败')
        QMessageBox.warning(self, '获取版本列表失败', message)

    def _fill_table(self):
        keep = {rel['tag'] for rel in self._selected_rels()}
        manifest = download.load_manifest(self._out_dir())
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._rels))
        for row, rel in enumerate(self._rels):
            picked = releases.choose_assets(rel)
            asset = picked[0] if picked else None
            tag = rel['tag'] + (' *' if rel['prerelease'] else '')
            state = ''
            if asset is None:
                state = '没发安装包'
            else:
                dest = download.dest_path(self._out_dir(), rel['tag'], asset['name'])
                if download.complete(dest, asset.get('size') or 0):
                    state = '已下载'
                elif os.path.exists(dest):
                    state = '不完整'
                elif download.record_key(rel['tag'], asset['name']) in manifest:
                    state = '记录在册但文件没了'
            values = (tag, asset['kind'] if asset else '—',
                      cu.format_size(asset.get('size') or 0) if asset else '—',
                      rel['date'] or '—', state)
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, rel)
                self.table.setItem(row, col, item)
        self.table.setUpdatesEnabled(True)
        self._fit_columns()
        # 行填满后竖滚动条才出现，viewport 宽度会变窄；下一帧再量一次，避免横向滚动条
        QTimer.singleShot(0, self._fit_columns)
        self._restore_selection(keep)

    def _restore_selection(self, keep):
        """填表会清空选中；恢复原来那行，没有就选最新版（顺手亮出发布说明）。"""
        target = None
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            rel = item.data(Qt.ItemDataRole.UserRole) if item else None
            if rel is not None and rel['tag'] in keep:
                target = row
                break
        if target is None and self.table.rowCount():
            target = 0
        if target is None:
            self._on_selection_changed()      # 空表：把说明一并清掉
            return
        # 选格子而不是整行：setCurrentCell 只点亮 (行, 0) 这一格
        self.table.setCurrentCell(target, 0)
        self.table.scrollToItem(self.table.item(target, 0))

    def _fit_columns(self):
        """前几列固定宽度，把剩下的横向空间都给「本地」列（不留右侧大片空白）。

        不用 ``stretchLastSection``：那会让 Qt 每次布局都重算所有列宽，
        和「列宽显式设定」的约定冲突；这里只在尺寸变化时算一次。
        """
        widths = [width for _name, width in _COLUMNS]
        room = self.table.viewport().width() - sum(widths[:-1]) - 4
        self.table.setColumnWidth(len(widths) - 1, max(widths[-1], room))

    def _selected_rels(self):
        # 选的是格子不是整行，selectedRows() 会永远是空；按格子所在行归并
        rows = sorted({index.row() for index in self.table.selectionModel().selectedIndexes()})
        out = []
        for row in rows:
            item = self.table.item(row, 0)
            rel = item.data(Qt.ItemDataRole.UserRole) if item else None
            if rel is not None:
                out.append(rel)
        return out

    # ------------------------------------------------------------ 下载
    def _install_latest(self):
        if self._busy:
            self.statusBar().showMessage('正在忙（下载或安装进行中），请稍候')
            return
        if not self._rels:
            # 列表还没到：先取，回来再接着装
            self._auto_latest = True
            self._refresh()
            return
        rel = releases.latest(self._rels)
        if rel is None:
            QMessageBox.information(self, '没有可安装的版本', '版本列表是空的，先刷新一下')
            return
        self._install_rel(rel)

    def _download_selected(self):
        rels = self._selected_rels()
        if not rels:
            QMessageBox.information(self, '先选版本',
                                    '在列表里点一下要下载的版本（按住 Ctrl 可多选），再点下载')
            return
        self._start_jobs(download.plan(rels, self._out_dir()))

    def _install_selected(self):
        rels = self._selected_rels()
        if not rels:
            QMessageBox.information(self, '先选版本', '在列表里点一下要装的版本，再点安装')
            return
        self._install_rel(rels[0])

    def _delete_local(self):
        """删掉选中版本在本地已下载的安装包（连同 manifest 记录）。

        不弹二次确认：删的是能重下的缓存，问了反而碍事；删完在状态栏报一句
        删了几个、释放多少。**只动 ``<输出目录>/<版本>/<文件名>``**，不会碰到
        用户目录里别的东西。
        """
        if self._busy:
            self.statusBar().showMessage('正在忙（下载或安装进行中），请稍候')
            return
        rels = self._selected_rels()
        if not rels:
            QMessageBox.information(self, '先选版本',
                                    '在列表里点一下要删的版本，再点「删除本地包」')
            return
        out = self._out_dir()
        manifest = download.load_manifest(out)
        removed = freed = 0
        failed = []
        for rel in rels:
            picked = releases.choose_assets(rel)
            if not picked:
                continue
            asset = picked[0]
            key = download.record_key(rel['tag'], asset['name'])
            manifest.pop(key, None)
            dest = download.dest_path(out, rel['tag'], asset['name'])
            if not os.path.exists(dest):
                continue
            try:
                size = os.path.getsize(dest)
                os.remove(dest)
            except OSError as e:
                failed.append('%s：%s' % (rel['tag'], e))
                continue
            removed += 1
            freed += size
            try:
                os.rmdir(os.path.dirname(dest))     # 版本目录空了就一起收走
            except OSError:
                pass
        download.save_manifest(out, manifest)
        self._fill_table()
        if removed:
            self.statusBar().showMessage(
                '已删除 %d 个安装包，释放 %s（需要时重新下载即可）'
                % (removed, cu.format_size(freed)))
        else:
            self.statusBar().showMessage('没有可删的本地安装包（这些版本还没下载过）')
        if failed:
            QMessageBox.warning(self, '有些文件没删掉',
                                '\n'.join(failed[:8])
                                + ('\n…' if len(failed) > 8 else '')
                                + '\n\n多半是安装程序正在使用它，关掉再试。')

    def _install_rel(self, rel):
        picked = releases.choose_assets(rel)
        if not picked:
            QMessageBox.information(self, '没有安装包',
                                    '版本 %s 没有发布安装包' % rel['tag'])
            return
        asset = picked[0]
        dest = download.dest_path(self._out_dir(), rel['tag'], asset['name'])
        if download.complete(dest, asset.get('size') or 0):
            self._launch_installer(dest)
            return
        self._start_jobs([{'release': rel, 'asset': asset, 'dest': dest}],
                         install_after=dest)

    def _start_jobs(self, jobs, install_after=None):
        if self._busy:
            return
        jobs = [j for j in jobs if j.get('asset')]
        if not jobs:
            QMessageBox.information(self, '没有可下载的安装包',
                                    '这些版本都没发布安装包')
            return
        self._install_after = install_after
        self._speed.reset()
        self._eta.reset()
        self._begin('准备下载…', progress=True)
        self._thread = _DownloadThread(jobs, self._out_dir(), self._prefer(),
                                       self.ck_force.isChecked())
        self._thread.message.connect(self._on_message)
        self._thread.progressed.connect(self._on_progress)
        self._thread.failed.connect(self._on_thread_failed)
        self._thread.finished.connect(self._on_download_finished)
        self._thread.start()

    def _on_message(self, text):
        self._label = text
        self.statusBar().showMessage(text)

    def _on_progress(self, done, total):
        self.progress.show()
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(done * 100 / total))
        else:
            self.progress.setRange(0, 0)       # 总长未知：走「忙碌」样式
        speed = self._speed.update(done)
        eta = self._eta.update(done, total)
        parts = [cu.format_size(done) + ('/' + cu.format_size(total) if total else ''),
                 cu.format_speed(speed)]
        rest = cu.format_eta(eta)
        if rest:
            parts.append('剩余 ' + rest)
        self.statusBar().showMessage('%s  %s' % (self._label, '  '.join(parts)))

    def _on_thread_failed(self, message):
        self.statusBar().showMessage(message)

    def _on_download_finished(self, saved, skipped, failed):
        self._end('下载结束：成功 %d，跳过 %d，失败 %d' % (saved, skipped, failed))
        self._fill_table()
        after, self._install_after = self._install_after, None
        if after and os.path.exists(after):
            self._launch_installer(after)
        elif failed:
            QMessageBox.warning(self, '部分下载失败',
                                '有 %d 个安装包没下成，详情见状态栏；再点一次会只补失败的。'
                                % failed)

    def _cancel(self):
        thread = self._thread
        stopper = getattr(thread, 'stop', None) if thread is not None else None
        if callable(stopper):
            stopper()
            self.statusBar().showMessage('正在取消…')

    # ------------------------------------------------------------ 安装
    def _launch_installer(self, path, wizard=False):
        """确认后启动安装程序，并在后台等它结束 —— 只看启动成功是不够的。"""
        if self._busy:
            self.statusBar().showMessage('正在忙（下载或安装进行中），请稍候')
            return
        name = os.path.basename(path)
        tag = os.path.basename(os.path.dirname(path))
        lines = ['开始安装：', name, '']
        same = [item for item in install.installed_versions()
                if item[1] and item[1] == tag]
        if same:
            where = same[0][2] or '（注册表没记安装位置）'
            lines.append('本机已安装 %s：%s' % (tag, where))
            lines.append('继续会覆盖安装，用户数据（日志、密钥）不会被删。')
            lines.append('')
        lines.append('安装程序会弹出 UAC 提权确认 —— 请看清屏幕上的'
                     '「用户账户控制」窗口并点「是」。')
        if wizard:
            lines.append('这次走完整安装向导，能看到每一步和真实错误。')
        else:
            lines.append('装完这里会显示结果。继续？')
        if QMessageBox.question(self, '安装 F HamLog', '\n'.join(lines)) \
                != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage('已取消安装，安装包留在：%s' % path)
            return

        self._begin('正在等待安装程序结束（请在 UAC 窗口点「是」）…', progress=False)
        self._install_thread = _InstallThread(path, silent=not wizard)
        self._install_thread.done.connect(self._on_install_done)
        self._install_thread.start()

    def _on_install_done(self, path, result):
        self._end()
        if isinstance(result, Exception):
            self.statusBar().showMessage('安装程序没能启动')
            QMessageBox.warning(self, '无法启动安装包',
                                '%s\n\n安装包位置：%s' % (result, path))
            return
        if result is None:
            self.statusBar().showMessage('已拉起安装程序（未等待结果）')
            return
        text = install.code_text(result)
        if result == 0:
            self.statusBar().showMessage('%s（%s）' % (text, os.path.basename(path)))
            QMessageBox.information(
                self, '安装完成',
                '%s\n\n如果 F HamLog 正在运行，请关掉再重新打开。' % text)
            return

        self.statusBar().showMessage('安装没有完成：%s' % text)
        answer = QMessageBox.warning(
            self, '安装没有完成',
            '%s\n\n安装包：%s\n\n'
            '常见原因：UAC 提权被取消（弹窗没点「是」）、被安全软件拦下、'
            '或安装包不完整。\n\n要改用完整安装向导再试一次吗（能看到真实错误）？'
            % (text, path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Yes:
            self._launch_installer(path, wizard=True)

    # ------------------------------------------------------------ 忙碌态
    def _begin(self, text, progress=False):
        """忙的时候**不禁用按钮**，只改文字/状态并靠 ``_busy`` 拦重入。

        禁用按钮会把焦点甩到相邻控件上，用户看到的是「点一下，焦点乱跳」。
        """
        self._busy = True
        self._label = ''
        self.statusBar().showMessage(text)
        self.btn_cancel.setVisible(bool(progress))
        if progress:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.show()

    def _end(self, text=''):
        self._busy = False
        self.btn_cancel.hide()
        self.progress.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        if text:
            self.statusBar().showMessage(text)

    def closeEvent(self, event):
        self._save_prefs()
        thread = self._thread
        if thread is not None and thread.isRunning():
            stopper = getattr(thread, 'stop', None)
            if callable(stopper):
                stopper()
            thread.wait(3000)
        # 等安装的线程不强行结束也没关系：安装程序是独立进程，线程没了它照样装完。
        # 这里只等一小会儿，免得用户以为关不掉窗口。
        waiting = self._install_thread
        if waiting is not None and waiting.isRunning():
            waiting.wait(800)
        super().closeEvent(event)


# ---------------------------------------------------------------- 入口

def main(argv=None):
    app = QApplication.instance() or QApplication(list(argv) if argv else sys.argv[:1])
    app.setApplicationName('F HamLog 安装器')
    app.setApplicationDisplayName('F HamLog 安装器')
    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(bg_thread.stop_all)
    code = app.exec()
    bg_thread.stop_all()      # 幂等：exec() 之后再来一次，兜住不走 aboutToQuit 的退出路径
    return code
