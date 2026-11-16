from PySide6.QtWidgets import *
from PySide6.QtGui import QUndoStack, QUndoCommand
from PySide6.QtCore import Qt, QTimer, QObject, QEvent, qInstallMessageHandler
from f_hamlog import call_upper
from f_hamlog.dialog_defaults import desktop_dir
from f_hamlog import i18n
import time as time_
import sys
import re
import os
import datetime
import json
from f_hamlog import fhl_rw
from f_hamlog import backup
from f_hamlog import theme
from f_hamlog.paths import app_path


# --------------------------------------------------------------------------
# 过滤冻结列（主表与冻结层共享同一 model）在真实 GUI 下偶发的良性 Qt 警告：
#   "QAbstractItemView::commitData/closeEditor called with an editor
#    that does not belong to this view"
# 这是 Qt 冻结列模式的已知框架怪癖（两视图共享 model 时事件路由导致），
# 并非逻辑错误；只过滤这一条，其余 Qt 消息原样输出到 stderr（或链式交给
# 之前已安装的其它消息处理器）。
# --------------------------------------------------------------------------
_ORIG_MSG_HANDLER = None
_MSG_FILTER_INSTALLED = False


def _qt_msg_filter(msg_type, context, text):
    if 'does not belong to this view' in text:
        return
    if _ORIG_MSG_HANDLER is not None:
        _ORIG_MSG_HANDLER(msg_type, context, text)
    else:
        try:
            sys.stderr.write(text + '\n')
        except Exception:
            pass


def _install_qt_msg_filter():
    global _ORIG_MSG_HANDLER, _MSG_FILTER_INSTALLED
    if _MSG_FILTER_INSTALLED:
        return
    _ORIG_MSG_HANDLER = qInstallMessageHandler(_qt_msg_filter)
    _MSG_FILTER_INSTALLED = True


translation_dict = {
                'date': '日期',
                'time': '时间',
                'm_call': '己方呼号',
                'o_call': '对方呼号',
                'freq': '频率',
                'freq_rx': '接收频率',
                'prop_mode': '传播方式',
                'sat_name': '卫星名称',
                'mode': '调制模式',
                'm_rst': '己方接收信号','o_rst': '对方接收信号',
                'm_qth': '己方QTH','o_qth': '对方QTH',
                "m_dig": '己方设备','o_dig': '对方设备',
                'm_ant': '己方天线','o_ant': '对方天线',
                'm_pow': '己方功率','o_pow': '对方功率',

                'notes': '备注'
            }

# 行顺序（即字段键顺序）
KEYS = list(translation_dict.keys())
# 每条日志必须满足的必填字段
REQUIRED_KEYS = ('m_call', 'o_call', 'freq', 'mode', 'm_rst', 'o_rst')

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TIME_RE = re.compile(r'^\d{2}:\d{2}$')


class FrozenTableWidget(QTableWidget):
    """第一列（模板列）冻结在左侧，类似 Excel 的冻结窗格。"""

    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        self._syncing = False
        # 冻结层：用 QTableView 共享主表 model，仅显示第 0 列
        self._frozen = QTableView(self)
        self._frozen.setModel(self.model())
        self._frozen.verticalHeader().hide()
        self._frozen.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self._frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.setFocusPolicy(Qt.NoFocus)
        self._frozen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._apply_frozen_theme()
        self.viewport().stackUnder(self._frozen)
        self._frozen.raise_()
        self._frozen.show()
        # 第 0 列宽度双向同步：主表和冻结层都能拖拽/调整，且避免递归循环
        self.horizontalHeader().sectionResized.connect(self._sync_frozen_from_main)
        self._frozen.horizontalHeader().sectionResized.connect(self._sync_main_from_frozen)
        # 冻结层 x = 竖向表头宽度，而竖向表头宽度会随**行标签文字**变化
        # （切语言时字段名由中文变英文 → 表头变宽 48px）。只在 resizeEvent 里
        # 重算的话，窗口不缩放时 x 会停在旧值 → 冻结列整体偏移一个表头宽度。
        # 这里监听表头几何 / 表头文字变化，延后一轮再同步（等 Qt 重算完表头宽度）。
        self._frozen_geom_pending = False
        self.verticalHeader().geometriesChanged.connect(self._schedule_frozen_geometry)
        self.horizontalHeader().geometriesChanged.connect(self._schedule_frozen_geometry)
        self.model().headerDataChanged.connect(self._schedule_frozen_geometry)
        self.sync_frozen_columns()
        # 垂直滚动同步（双向，带防抖）
        self.verticalScrollBar().valueChanged.connect(self._sync_from_main)
        self._frozen.verticalScrollBar().valueChanged.connect(self._sync_from_frozen)

    def _schedule_frozen_geometry(self, *args):
        """延后到事件循环下一轮再同步冻结层几何。

        表头文字变化 → 竖向表头宽度在本轮布局**结束之后**才更新，立刻量会拿到旧值
        （这正是「切语言后冻结列错位」的成因）。合并多次请求，只跑一次。
        """
        if self._frozen_geom_pending:
            return
        self._frozen_geom_pending = True

        def _run():
            try:
                self._frozen_geom_pending = False
                self.updateFrozenGeometry()
            except Exception:
                # 窗口可能已销毁；几何同步是纯视觉修正，失败不影响功能
                pass

        QTimer.singleShot(0, _run)

    def _apply_frozen_theme(self):
        """冻结层底色跟随主题取色。

        曾写死 background-color:#f3f3f3，在 Windows 深色模式下文字仍取主题的
        白色 → 白字压浅灰底，整列内容不可见。这里改为从调色板推导：浅色主题
        取浅灰、深色主题取深灰，两种主题下都与文字形成对比。

        注意：取色必须用主表（self）的调色板 —— 下面这条 stylesheet 的
        background-color 会被 Qt 反写进冻结层自身的调色板，用冻结层取色会
        在首次设置后就锁死在那个颜色，系统切换深浅色时不会跟着变。
        """
        css = ('QTableView{ border:none; background-color:%s; }'
               % theme.subtle_bg(self).name())
        if css != self._frozen.styleSheet():
            self._frozen.setStyleSheet(css)

    def changeEvent(self, event):
        # 系统深浅色切换时重新取色（Qt 会把调色板/主题变化事件发给控件）
        if event.type() in theme.THEME_EVENTS:
            self._apply_frozen_theme()
        super().changeEvent(event)

    def _sync_frozen_from_main(self, logical_index, old_size, new_size):
        if logical_index != 0 or self._syncing:
            return
        self._syncing = True
        try:
            self._frozen.setColumnWidth(0, new_size)
            self.updateFrozenGeometry()
        finally:
            self._syncing = False

    def _sync_main_from_frozen(self, logical_index, old_size, new_size):
        if logical_index != 0 or self._syncing:
            return
        self._syncing = True
        try:
            self.setColumnWidth(0, new_size)
            self.updateFrozenGeometry()
        finally:
            self._syncing = False

    def sync_frozen_columns(self):
        """冻结层只显示第 0 列，并同步其宽度（横向表头标签由共享 model 提供）。"""
        for c in range(self.columnCount()):
            self._frozen.setColumnHidden(c, c != 0)
        width = self.columnWidth(0)
        self._frozen.setColumnWidth(0, width)
        self._frozen.setMinimumWidth(width)
        self._frozen.setMaximumWidth(width)

    def updateFrozenGeometry(self):
        hh = self.horizontalHeader().height()
        vhw = self.verticalHeader().width()
        # 冻结层只覆盖第 0 列的实际区域，不得扩展到第 1 个日志列
        self._frozen.setGeometry(vhw, 0, self.columnWidth(0), hh + self.viewport().height())
        self.sync_frozen_columns()

    def set_frozen(self, on):
        self._frozen.setVisible(on)
        if on:
            self.updateFrozenGeometry()
            # 重新显示后需置顶，否则会落到主表视口后面导致"失效"
            self._frozen.raise_()

    def _sync_from_main(self, val):
        if self._syncing:
            return
        self._syncing = True
        self._frozen.verticalScrollBar().setValue(val)
        self._syncing = False

    def _sync_from_frozen(self, val):
        if self._syncing:
            return
        self._syncing = True
        self.verticalScrollBar().setValue(val)
        self._syncing = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateFrozenGeometry()

    def showEvent(self, event):
        super().showEvent(event)
        self.updateFrozenGeometry()


class _EditorHookDelegate(QStyledItemDelegate):
    """默认（非呼号）单元格委托：在编辑器上挂载导航/撤销事件过滤器。"""

    def __init__(self, nav_filter):
        super().__init__()
        self._nav = nav_filter

    def createEditor(self, parent, option, index):
        ed = super().createEditor(parent, option, index)
        ed._row = index.row()
        ed._col = index.column()
        ed.installEventFilter(self._nav)
        return ed


class _CallDelegate(call_upper.UpperCallDelegate):
    """呼号行（己方/对方）委托：实时转大写 + 挂载导航/撤销事件过滤器。"""

    def __init__(self, nav_filter):
        super().__init__()
        self._nav = nav_filter

    def createEditor(self, parent, option, index):
        ed = super().createEditor(parent, option, index)
        ed._row = index.row()
        ed._col = index.column()
        ed.installEventFilter(self._nav)
        return ed


class _NavFilter(QObject):
    """统一处理单元格编辑器与主窗口的快捷键与撤销/重做捕获。

    挂在主窗口（按钮聚焦时）、主表与冻结层（未编辑时）以及每个编辑器
    （编辑时，由委托在 createEditor 内挂载）——覆盖所有焦点状态，避免
    QLineEdit / QTableWidget 吞掉 Ctrl+方向 / N / D / Z / Y 等组合键。
    """

    def __init__(self):
        super().__init__()
        self.table = None
        self.undo = None
        self.suspend = [False]
        self._pending = None
        self.goto_prev = None
        self.goto_next = None
        self.add_col = None
        self.del_col = None
        self.do_undo = None
        self.do_redo = None
        self.do_save = None

    def _capture_old(self, editor):
        r, c = editor._row, editor._col
        item = self.table.item(r, c)
        self._pending = (r, c, item.text() if item else '')

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and (event.modifiers() & Qt.ControlModifier):
            # 模态对话框（如保存完成、提示框）打开时不拦截，避免误触发
            if QApplication.activeModalWidget() is not None:
                return False
            key = event.key()
            if key == Qt.Key_Left:
                if self.goto_prev:
                    self.goto_prev()
                return True
            if key == Qt.Key_Right:
                if self.goto_next:
                    self.goto_next()
                return True
            if key == Qt.Key_N:
                if self.add_col:
                    self.add_col()
                return True
            if key == Qt.Key_D:
                if self.del_col:
                    self.del_col()
                return True
            if key == Qt.Key_Z and not (event.modifiers() & Qt.ShiftModifier):
                if self.do_undo:
                    self.do_undo()
                return True
            if key == Qt.Key_Y or (key == Qt.Key_Z and (event.modifiers() & Qt.ShiftModifier)):
                if self.do_redo:
                    self.do_redo()
                return True
            if key == Qt.Key_S:
                if self.do_save:
                    self.do_save()
                return True
            return False
        if event.type() == QEvent.FocusIn and hasattr(obj, '_row'):
            if not self.suspend[0]:
                self._capture_old(obj)
            return False
        if event.type() == QEvent.FocusOut and self._pending is not None:
            r, c, old = self._pending
            item = self.table.item(r, c)
            new = item.text() if item else ''
            if new == old:
                self._pending = None
            return False
        return False


# ---------------------------------------------------------------------------
#  「记录保存到哪儿」——完成页与「自动保存到日志文件」共用同一套选择界面
# ---------------------------------------------------------------------------
# 目标一律用元组描述，第一个元素是类型：
#   ('append', path)                  追加到已有日志文件（.fhla / .fhl / .adi）
#   ('new', path)                     另存为新的日志文件（只放本次记录）
#   ('default', path)                 默认通联日志（主页「通联日志」那个文件）
#   ('remote', host, port, password)  多人日志
def default_log_path():
    """主页「通联日志」打开的那个文件：**优先 main.fhla**，只有旧的 main.fhl 才退回它。

    旧写法写死 main.fhl——迁移成 .fhla 后主页读的是 main.fhla，记录加进去了却看不见。
    """
    path = app_path(os.path.join('file', 'main.fhla'))
    legacy = app_path(os.path.join('file', 'main.fhl'))
    if not os.path.exists(path) and os.path.exists(legacy):
        return legacy
    return path


def target_name(target):
    """目标显示名：文件类用文件名，多人日志用 ``host:port``。"""
    if target[0] in ('append', 'new', 'default'):
        return os.path.basename(target[1]) or target[1]
    return '{}:{}'.format(target[1], target[2])


def _load_records_file(path):
    """读日志文件 → ``(records, key, meta)``；文件不存在按空日志处理。"""
    if not os.path.exists(path):
        return [], None, None
    from f_hamlog import project
    return project.read_project_file(path)


def _write_records_file(records, path, key=None, meta=None):
    """写日志文件：按扩展名分派（.fhla 带属性块 / .adi 写 ADIF / .fhl 只写记录）。"""
    from f_hamlog import project   # 延迟导入：project 亦以延迟方式引用本模块
    project.save_project_file(path, records, key, meta=meta)


def _append_to_remote(host, port, password, records):
    """把 records 追加到指定多人日志服务端（连上先拉现有日志，再整体发回去）。"""
    from f_hamlog.project import RemoteConnection
    conn = RemoteConnection(host, port, password, role='guest')
    try:
        conn.connect()                                  # 连接并拉取服务端现有日志
        conn.send_save(list(conn.initial_file) + list(records))
        # 等服务端回 OK 再关闭，避免立即关闭触发 RST
        try:
            conn.sock.settimeout(5.0)
            from f_hamlog.remote_server import recv_frame
            while True:
                frame = recv_frame(conn.sock)
                if frame is None or frame[0] == 'OK':
                    break
        except Exception:
            pass
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


def apply_save_target(target, records):
    """把 records 写到 target 指定的地方；失败直接抛异常，由调用方提示。"""
    kind = target[0]
    if kind == 'new':
        _write_records_file(records, target[1])
    elif kind in ('append', 'default'):
        old, key, meta = _load_records_file(target[1])
        _write_records_file(list(old or []) + list(records), target[1], key, meta)
    elif kind == 'remote':
        _append_to_remote(target[1], target[2], target[3], records)
    else:
        raise ValueError('unknown save target: %r' % (target,))
    if kind != 'remote':
        # 这个日志可能正被某个项目窗口打开着：让它把磁盘内容重新读回来。
        # 否则那个窗口的内存还停在写入前的样子，它下一次自动保存就会把刚写进去的
        # 记录整份覆盖掉（用户看到的就是「自动保存没生效」）。
        from f_hamlog import project
        project.notify_file_changed(target[1])


def _stamp_of(path):
    """文件指纹（修改时间 + 大小）；不存在返回 None。用来判断「要不要重新解析」。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def path_sync_io(path, fresh=False):
    """按路径实时读写的同步接口（主页启动的批量记录用）。

    read() → ``(records, token)``：``records`` 为 None 表示读不出来（例如加密日志
             又没有密钥）——调用方据此放弃实时同步，**绝不**把明文写回去。
    write(records, token)：按扩展名分派写盘，并通知打开同一文件的项目窗口重载，
             这样那个窗口的表格能立刻显示出批量记录写进去的内容。

    fresh=True（「另存为日志文件」）时文件只放本次记录，不读旧内容。
    连续同步同一个文件时用文件指纹做缓存：自己刚写完就不用再解析一遍。
    """
    cache = {'stamp': None, 'records': None, 'token': None}

    def read():
        if fresh:
            return [], (None, None)
        stamp = _stamp_of(path)
        if cache['records'] is not None and stamp == cache['stamp']:
            return list(cache['records']), cache['token']
        if not os.path.exists(path):
            return [], (None, None)
        from f_hamlog import project
        recs, k, m = project.read_project_file(path, key=None, ask_key=False)
        if recs is None:
            return None, None
        cache['records'] = list(recs)
        cache['token'] = (k, m)
        cache['stamp'] = stamp
        return list(recs), cache['token']

    def write(records, token):
        key_, meta_ = token or (None, None)
        _write_records_file(records, path, key_, meta_)
        cache['records'] = list(records)
        cache['token'] = token
        cache['stamp'] = _stamp_of(path)
        from f_hamlog import project
        project.notify_file_changed(path)

    return {'read': read, 'write': write}


def done_message(target, count):
    """保存成功后的提示文案（按去处分别措辞，便于确认写到了哪个日志）。"""
    kind = target[0]
    if kind == 'new':
        return '已另存为项目文件：{}'.format(target[1])
    if kind == 'default':
        return '已添加 {} 条记录到默认通联日志'.format(count)
    if kind == 'remote':
        return '已添加 {} 条记录到多人日志（{}:{}）。'.format(count, target[1], target[2])
    return '已添加 {} 条记录到项目。'.format(count)


def ask_remote_target(parent):
    """问多人日志的地址 / 端口 / 密码；取消返回 None。"""
    dlg = QDialog(parent)
    dlg.setWindowTitle('添加到多人日志')
    dlg.setMinimumWidth(380)
    dlg.setModal(True)
    v = QVBoxLayout(dlg)
    v.setSpacing(8)
    v.setContentsMargins(18, 16, 18, 14)
    host_e = QLineEdit()
    host_e.setPlaceholderText('服务端地址（IP 或域名）')
    port_e = QLineEdit('8000')
    pw_e = QLineEdit()
    pw_e.setEchoMode(QLineEdit.Password)
    pw_e.setPlaceholderText('密码（可留空）')
    btn_tgl = QPushButton('显示/隐藏')
    btn_tgl.setFixedWidth(84)

    def _toggle_password():
        pw_e.setEchoMode(QLineEdit.Normal if pw_e.echoMode() == QLineEdit.Password
                         else QLineEdit.Password)

    btn_tgl.clicked.connect(_toggle_password)
    r1 = QHBoxLayout(); r1.addWidget(QLabel('服务端：')); r1.addWidget(host_e, 1)
    r2 = QHBoxLayout(); r2.addWidget(QLabel('端口：')); r2.addWidget(port_e, 1)
    r3 = QHBoxLayout(); r3.addWidget(QLabel('密码：')); r3.addWidget(pw_e, 1); r3.addWidget(btn_tgl)
    v.addLayout(r1); v.addLayout(r2); v.addLayout(r3)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    v.addWidget(bb)
    if dlg.exec() != QDialog.Accepted:
        return None
    host = host_e.text().strip()
    if not host:
        QMessageBox.warning(parent, '添加到多人日志', '请输入服务端地址。')
        return None
    try:
        port = int(port_e.text().strip() or '8000')
    except ValueError:
        port = 8000
    return (host, port, pw_e.text())


def choose_save_target(parent, heading):
    """「记录保存到哪儿」选择页（完成页 / 勾选自动保存时提示位置，同一个界面）。

    只有一个标题 + 四条单选项，**不摆灰色说明文字**：去处本身就是「日志文件 /
    默认通联日志 / 多人日志」，一眼能分辨，多一行灰字只会显得啰嗦。
    返回目标元组；取消返回 None。文案写中文原文，由 i18n 在显示时统一翻译。
    """
    from f_hamlog import project
    # 定稿：一律说「日志文件」，不再按格式叫「F HamLog 项目」——现在 .fhla / .fhl / .adi
    # 三种都能进（追加时按扩展名分派，另存为时在文件对话框里选格式）。
    options = (
        ('append', '添加到日志文件'),
        ('new', '另存为日志文件'),
        ('default', '添加到默认通联日志'),
        ('remote', '添加到多人日志'),
    )

    dlg = QDialog(parent)
    dlg.setWindowTitle('保存记录')
    dlg.setMinimumWidth(340)
    dlg.setModal(True)
    v = QVBoxLayout(dlg)
    v.setSpacing(0)
    v.setContentsMargins(24, 20, 24, 16)

    title = QLabel(heading)
    title.setStyleSheet('font-size:11pt;')
    v.addWidget(title)
    v.addSpacing(14)

    group = QButtonGroup(dlg)
    radios = []
    for i, (_kind, label) in enumerate(options):
        rb = QRadioButton(label)
        rb.setStyleSheet('font-size:10pt;')
        group.addButton(rb, i)
        radios.append(rb)
        v.addSpacing(10 if i else 0)
        v.addWidget(rb)

    radios[0].setChecked(True)

    v.addSpacing(16)
    btns = QHBoxLayout()
    btns.addStretch(1)
    btn_cancel = QPushButton('取消')
    btn_cancel.setFixedWidth(88)
    btn_ok = QPushButton('确定')
    btn_ok.setFixedWidth(88)
    btn_ok.setDefault(True)
    btns.addWidget(btn_cancel)
    btns.addWidget(btn_ok)
    v.addLayout(btns)

    picked = {'target': None}

    def _confirm():
        idx = group.checkedId()
        kind = options[idx][0]
        if kind == 'append':
            path, _ = QFileDialog.getOpenFileName(
                dlg, i18n.tr('添加到 F HamLog项目'), desktop_dir(),
                project.project_open_filters())
            if not path:
                return                      # 没选文件就停在选择页，别悄悄按取消处理
            target = ('append', path)
        elif kind == 'new':
            path, sel = QFileDialog.getSaveFileName(
                dlg, i18n.tr('另存为 F HamLog项目'), desktop_dir(),
                project.project_save_filters())   # 默认 .fhla；想存纯记录切到 .fhl 那条
            if not path:
                return
            target = ('new', project.complete_project_suffix(path, sel))
        elif kind == 'default':
            target = ('default', default_log_path())
        else:
            remote = ask_remote_target(dlg)
            if remote is None:
                return
            target = ('remote',) + remote
        picked['target'] = target
        dlg.accept()

    btn_cancel.clicked.connect(dlg.reject)
    btn_ok.clicked.connect(_confirm)
    dlg.exec()
    return picked['target']


def main(window, preset=None, on_saved=None, preset_records=None, recovered=False,
         auto_target=None, sync_io=None, auto_target_path=None):
    """打开批量记录窗口。

    on_saved：由某个项目窗口启动时传入的「追加到该日志」回调（卫星「记录」按钮 /
              项目窗口菜单「批量记录」）；从主页启动时为 None。
    auto_target：启动窗口的那个日志名（显示在「自动保存到日志文件」复选框上）。
    auto_target_path：启动窗口的日志文件路径（没有落盘时给 None）；只用于判断
              「点完成时选的去处是不是还是这个日志」，避免同一批记录被重复追加。
    sync_io：实时同步用的读写接口（``{'read':…, 'write':…}``，见 path_sync_io）。
              由项目窗口启动时传入，让「边改边写」直接落到那个窗口自己的记录列表
              与落盘实现上（加密密钥 / .fhla 属性块 / 多人日志都不会分叉）；
              从主页启动时由本模块按所选文件目标临时构造。
    """
    _install_qt_msg_filter()  # 过滤冻结列良性 Qt 警告
    window.resize(1200, 790)
    window.setWindowTitle('批量记录')

    with open(app_path('file/m_xml.txt'), 'r', encoding='utf-8') as f:
        xml_dict = eval(f.read())

    local_date = time_.strftime("%Y-%m-%d", time_.localtime())
    local_time = time_.strftime("%H:%M", time_.localtime())

    app_list = {
                'date': local_date,
                'time': local_time,
                'm_call': xml_dict['m_call'].upper(),
                'o_call': '',
                'freq': '',
                'freq_rx': '',
                'mode': '',
                'prop_mode': '',
                'sat_name': '',
                'm_rst': '59',
                'o_rst': '59',
                'm_qth': xml_dict['m_qth'],
                'o_qth': '',
                "m_dig": xml_dict['m_dig'],
                'o_dig': '',
                'm_ant': '',
                'o_ant': '',
                'm_pow': '',
                'o_pow': '',
                'notes': ''
            }

    # 若由卫星窗口等外部调用并传入预填数据，则用其覆盖对应字段
    # （其余字段如 m_call/o_call/m_qth 仍取自设置，保持默认）
    if preset:
        for k in ('date', 'time', 'freq', 'freq_rx', 'mode', 'prop_mode', 'sat_name',
                  'm_qth', 'o_qth', 'o_call', 'notes'):
            v = preset.get(k)
            if v not in (None, ''):
                app_list[k] = v

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    # 实时时钟：显示当前 UTC 与本地时间（每秒刷新一次），置于窗口上方
    clock_label = QLabel()
    # 颜色在下方 apply_theme_colors() 里按当前主题设置（写死颜色会在深色模式下看不清）
    clock_label.setStyleSheet('font-size:9pt; padding:2px 0;')
    clock_label.setAlignment(Qt.AlignLeft)

    def update_clock():
        """刷新时钟标签：UTC 与本地时间（含本地 UTC 偏移）。"""
        fmt = '%Y-%m-%d %H:%M:%S'
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = datetime.datetime.now()
        tz = now_local.astimezone().strftime('%z')  # 形如 '+0800'
        tz_disp = ('UTC%s:%s' % (tz[:3], tz[3:])) if tz else 'UTC'
        clock_label.setText(i18n.tr('UTC %s   |   本地 %s (%s)'
                                    % (now_utc.strftime(fmt),
                                       now_local.strftime(fmt), tz_disp)))

    update_clock()  # 立即填充一次，避免首秒空白
    # 定时器挂到 window 下，防止 main() 返回后被回收
    clock_timer = QTimer(window)
    clock_timer.setInterval(1000)
    clock_timer.timeout.connect(update_clock)
    clock_timer.start()
    layout.addWidget(clock_label)

    label = QLabel('第一列为模板（默认值，可留空）；新增日志列时，日期/时间为空则自动填充当前时间。')
    label.setAlignment(Qt.AlignCenter)
    layout.addWidget(label)

    # 选项区：冻结模板列开关（默认开启，类似 Excel 冻结首列）
    opt_row = QHBoxLayout()
    opt_row.setSpacing(10)
    cb_freeze = QCheckBox('固定模板列')
    cb_freeze.setChecked(True)
    opt_row.addWidget(cb_freeze)
    # 「自动保存到日志文件」：勾上后**边改边写**——表格里每改动 / 新建一列，都会把
    # 已经填完整的记录同步进目标日志（项目窗口的表格随之刷新），点「完成」只是补一次
    # 同步然后关窗。
    #   · 由项目窗口启动（on_saved 非空）→ 默认勾选，目标就是那个项目的日志文件；
    #   · 从主页启动 → 没有「当前日志」，默认不勾选；**一勾上就先问「存到哪个日志」**
    #     （复用完成页那套选择界面），选好之后就开始实时同步。
    cb_auto = QCheckBox('自动保存到日志文件')
    cb_auto.setChecked(on_saved is not None)
    if auto_target:
        # 写中文原文，由 i18n 在窗口显示时统一翻译（别在这里先 tr，否则切回中文还原不回来）
        cb_auto.setText('自动保存到日志文件（{}）'.format(auto_target))
    # 主页启动时勾选后选定的去处（元组，见本模块顶部的「记录保存到哪儿」）
    auto_pick = {'target': None}

    # 实时同步的运行时状态（函数体在后面 table 建好之后定义）：
    #   io      读写接口；active 是否真的在同步（读不出来就是 False）
    #   last    目标日志当前内容（我们最后一次读到 / 写下的版本）
    #   pos/wrote  各列写进日志后的下标与内容——下次同步就地改这一条，而不是再追加一条
    #   times   各列「日期/时间留空」时补的当前时间（同一列只用第一次补的那份）
    #   pending 有改动还没写；hold 暂停（回填恢复内容时不要自动写盘）
    live = {'io': None, 'active': False, 'target': None, 'last': None,
            'pos': {}, 'wrote': {}, 'times': {}, 'pending': False, 'hold': False,
            'warned': False, 'gone': [], 'detached': []}
    # 逐格提交 + 连续几格编辑会被合并成一次写盘（日志是整份重写，别敲一下就写一次）
    live['timer'] = QTimer(window)
    live['timer'].setSingleShot(True)
    live['timer'].setInterval(400)
    live['timer'].timeout.connect(lambda: _live_sync())

    def _on_auto_toggled(checked):
        """勾选 / 取消「自动保存到日志文件」。"""
        if not checked:
            # 取消勾选：停止实时同步。已经写进日志的记录不撤回，但记下它们是哪几条——
            # 之后点「完成」若还是写回同一个日志，就别再追加一遍（否则就是重复记录）。
            if live['active']:
                live['detached'] = [dict(r) for r in live['wrote'].values()]
            live['active'] = False
            live['io'] = None
            live['timer'].stop()
            live['pending'] = False
            return
        if on_saved is not None:
            # 项目窗口启动：目标就是这个项目，直接开始实时同步
            if not live['active'] and _live_enable(sync_io, keep=True):
                _live_touch()           # 取消过再勾回来：把这段时间的改动补写一次
            return
        if auto_pick['target'] is not None:
            # 目标已经选过（取消勾选后又勾回来）：接着同步，别重复问一遍
            if not live['active'] and auto_pick['target'][0] != 'remote':
                io = path_sync_io(auto_pick['target'][1],
                                  fresh=(auto_pick['target'][0] == 'new'))
                if _live_enable(io, keep=True):
                    _live_touch()
            return
        target = choose_save_target(window, '已录入的记录要保存到哪里？')
        if target is None:
            cb_auto.setChecked(False)   # 没选成 → 保持未勾选，完成时仍按原流程选保存方式
            return
        auto_pick['target'] = target
        live['target'] = target
        # 默认通联日志是固定的去处，复选框上不挂文件名（「（main.fhla）」看着像
        # 「只能存这个文件」，且那个文件名对用户没有信息量）；只有选了具体文件
        # 才把日志名带上，方便确认写到哪里。
        cb_auto.setText('自动保存到日志文件' if target[0] == 'default'
                        else '自动保存到日志文件（{}）'.format(target_name(target)))
        if target[0] == 'remote':
            # 多人日志不做逐格同步：每改一格就连一次网、把整份日志发回去，代价太大。
            # 它仍按原来的方式工作——点「完成」时一次性追加。
            return
        if _live_enable(path_sync_io(target[1], fresh=(target[0] == 'new'))):
            _live_touch()               # 勾选前已经填好的记录，立刻补一次同步

    cb_auto.toggled.connect(_on_auto_toggled)
    opt_row.addWidget(cb_auto)
    opt_row.addStretch(1)
    layout.addLayout(opt_row)

    # 表格：行=字段，列0=模板，初始无日志列（默认不要日志）
    table = FrozenTableWidget(len(KEYS), 1)
    table.setVerticalHeaderLabels(list(translation_dict.values()))
    # 行高与 project.py 主表一致：使用 Qt 默认行高，不设自定义值

    # 冻结模板列开关（默认开启）；在 table 创建后再连接
    cb_freeze.toggled.connect(table.set_frozen)

    def refresh_headers():
        headers = [i18n.tr('模板')] + [i18n.tr(f'第{i}条')
                                      for i in range(1, table.columnCount())]
        table.setHorizontalHeaderLabels(headers)

    # 初始填充：仅模板列（默认值）；若日期/时间为空字符串则自动回填本地时间/日期
    for r in range(len(KEYS)):
        value = app_list[KEYS[r]]
        if KEYS[r] == 'date' and value == '':
            value = local_date
        if KEYS[r] == 'time' and value == '':
            value = local_time
        table.setItem(r, 0, QTableWidgetItem(value))
    refresh_headers()
    # 默认选中最后一列（初始即模板列）
    table.setCurrentCell(0, table.columnCount() - 1)

    # 列宽
    table.setColumnWidth(0, 150)

    # 「对方呼号」所在行；记录时自动聚焦到此，并支持 Ctrl+←/→ 在多条日志间切换
    o_call_row = KEYS.index('o_call')
    # 构造播放窗口标题/信息所需的行索引
    date_row = KEYS.index('date')
    time_row = KEYS.index('time')
    # ---- 撤销 / 重做栈（挂到 window 下，避免局部变量被提前析构）----
    undo_stack = QUndoStack(window)

    def _set_suspend(on):
        nav_filter.suspend[0] = on

    def _col_data(c):
        return [table.item(r, c).text() if table.item(r, c) is not None else ''
                for r in range(table.rowCount())]

    def _insert_col(c, data):
        _set_suspend(True)
        table.insertColumn(c)
        for r, t in enumerate(data):
            table.setItem(r, c, QTableWidgetItem(t))
        table.setColumnWidth(c, 120)
        refresh_headers()
        table.updateFrozenGeometry()
        _set_suspend(False)
        _live_shift_cols(c, +1)      # 后面各列的列号往后挪一格（写进日志的位置不变）
        _live_touch()

    def _remove_col(c):
        _set_suspend(True)
        table.removeColumn(c)
        refresh_headers()
        table.updateFrozenGeometry()
        _set_suspend(False)
        # 这一列写进日志的那条记录也要跟着删（交给下次同步）；后面各列列号往前挪一格
        _live_shift_cols(c, -1, removed=(live['pos'].get(c), live['wrote'].get(c)))
        _live_touch()

    def focus_o_call(col):
        """把焦点定位到指定列的「对方呼号」单元格并进入编辑。

        始终先让主表当前单元格跟踪到目标列（保证 currentColumn 一致，
        使 Ctrl+←/→ 导航不卡死）；模板列(col 0)由冻结层呈现，编辑器需落到
        冻结层上（否则主表弹出的编辑器会被冻结层遮住），其余日志列直接在主表编辑。"""
        if col < 0 or col >= table.columnCount():
            return
        idx = table.model().index(o_call_row, col)
        table.setCurrentCell(o_call_row, col)
        if col == 0 and table._frozen.isVisible():
            table._frozen.setCurrentIndex(idx)
            table._frozen.edit(idx)
        else:
            table.edit(idx)
        table.scrollTo(idx)

    def goto_prev():
        """Ctrl+←：上一条（前一列日志）。"""
        c = table.currentColumn()
        if c > 0:
            focus_o_call(c - 1)

    def goto_next():
        """Ctrl+→：下一条（后一列日志）。"""
        c = table.currentColumn()
        if c < table.columnCount() - 1:
            focus_o_call(c + 1)

    def _template_data_for_new_log():
        """复制模板列内容到新日志列，日期/时间为空时用当前本地时间补齐。"""
        current_date = time_.strftime("%Y-%m-%d", time_.localtime())
        current_time = time_.strftime("%H:%M", time_.localtime())
        data = [table.item(r, 0).text() if table.item(r, 0) is not None else ''
                for r in range(table.rowCount())]
        for r, key in enumerate(KEYS):
            if key == 'date' and data[r] == '':
                data[r] = current_date
            elif key == 'time' and data[r] == '':
                data[r] = current_time
        return data

    def add_log_column():
        """Ctrl+N：在末尾新增一条日志列，内容复制当前模板列的值，并跳转聚焦。"""
        c = table.columnCount()
        data = _template_data_for_new_log()
        undo_stack.push(_AddColCmd(c, data))

    def delete_current_column():
        """Ctrl+D：删除当前选中的日志列（模板列不可删），可撤销。"""
        c = table.currentColumn()
        if c < 1:
            QMessageBox.information(window, '提示', '请先选中要删除的日志列（模板列不可删除）。')
            return
        undo_stack.push(_DelColCmd(c, _col_data(c)))

    def do_undo():
        undo_stack.undo()

    def do_redo():
        undo_stack.redo()

    # ---- 撤销命令 ----
    class _CellCmd(QUndoCommand):
        def __init__(self, tbl, r, c, old, new, nf):
            super().__init__('编辑单元格')
            self._tbl = tbl
            self._r = r
            self._c = c
            self._old = old
            self._new = new
            self._nf = nf

        def _apply(self, text):
            self._nf.suspend[0] = True
            item = self._tbl.item(self._r, self._c)
            if item is None:
                item = QTableWidgetItem()
                self._tbl.setItem(self._r, self._c, item)
            item.setText(text)
            self._nf.suspend[0] = False
            if self._c >= 1:
                _live_touch()     # 撤销 / 重做也要同步（否则日志里留下的是撤销前的内容）

        def redo(self):
            self._apply(self._new)

        def undo(self):
            self._apply(self._old)

    class _AddColCmd(QUndoCommand):
        def __init__(self, c, data):
            super().__init__('添加日志列')
            self._c = c
            self._data = data

        def redo(self):
            _insert_col(self._c, self._data)
            focus_o_call(self._c)

        def undo(self):
            _remove_col(self._c)
            focus_o_call(max(0, self._c - 1))

    class _DelColCmd(QUndoCommand):
        def __init__(self, c, data):
            super().__init__('删除日志列')
            self._c = c
            self._data = data

        def redo(self):
            _remove_col(self._c)
            focus_o_call(max(0, self._c - 1))

        def undo(self):
            _insert_col(self._c, self._data)
            focus_o_call(self._c)

    def on_cell_changed(r, c):
        if nav_filter.suspend[0]:
            return
        if c >= 1:
            _live_touch()     # 勾了自动保存 → 合并一次，把这一格同步进日志

        if nav_filter._pending is None:
            return
        pr, pc, old = nav_filter._pending
        if pr != r or pc != c:
            return
        item = table.item(r, c)
        new = item.text() if item else ''
        if new != old:
            undo_stack.push(_CellCmd(table, r, c, old, new, nav_filter))
        nav_filter._pending = None

    # ---- 委托（主表与冻结层各用独立实例，避免跨视图 commitData 警告）----
    nav_filter = _NavFilter()
    nav_filter.table = table
    nav_filter.undo = undo_stack
    nav_filter.goto_prev = goto_prev
    nav_filter.goto_next = goto_next
    nav_filter.add_col = add_log_column
    nav_filter.del_col = delete_current_column
    nav_filter.do_undo = do_undo
    nav_filter.do_redo = do_redo

    _del_main = _EditorHookDelegate(nav_filter)
    _del_call_main = _CallDelegate(nav_filter)
    _del_frozen = _EditorHookDelegate(nav_filter)
    _del_call_frozen = _CallDelegate(nav_filter)
    # 保持引用，防止被回收
    table._hook_del = _del_main
    table._call_del = _del_call_main
    table._frozen._hook_del = _del_frozen
    table._frozen._call_del = _del_call_frozen

    table.setItemDelegate(_del_main)
    table.setItemDelegateForRow(2, _del_call_main)
    table.setItemDelegateForRow(3, _del_call_main)
    table._frozen.setItemDelegate(_del_frozen)
    table._frozen.setItemDelegateForRow(2, _del_call_frozen)
    table._frozen.setItemDelegateForRow(3, _del_call_frozen)

    # 导航/撤销过滤器：挂在主窗口（按钮聚焦时）、主表与冻结层（未编辑时）
    # 以及每个编辑器（编辑时，委托在 createEditor 内挂载）——覆盖所有焦点状态，
    # 避免 QLineEdit / QTableWidget 吞掉 Ctrl+方向 / N / D / Z / Y。
    for _w in (window, table, table.viewport(), table._frozen, table._frozen.viewport()):
        _w.installEventFilter(nav_filter)
    table.cellChanged.connect(on_cell_changed)

    # ---------- 实时同步：勾选「自动保存到日志文件」后边改边写 ----------
    def _col_record(c):
        """把第 c 列收成一条记录 → ``(记录, 是否可写, 是否全空)``。

        「可写」= 这一列不是全空、日期/时间格式对、必填项都填了。批量记录本来就是
        边打边填：没填完的列先不写进日志，等填完那一下再同步，用户不会看到半条记录。
        """
        rec = {}
        empty = True
        for r in range(table.rowCount()):
            k = KEYS[r]
            it = table.item(r, c)
            v = it.text() if it is not None else ''
            rec[k] = v
            if v != '':
                empty = False
        if empty:
            live['times'].pop(c, None)
            return None, False, True
        # 日期 / 时间留空 → 补当前时间；同一列只用第一次补的那份（否则每同步一次时间就变）
        fb = live['times'].get(c)
        if fb is None:
            fb = (time_.strftime("%Y-%m-%d", time_.localtime()),
                  time_.strftime("%H:%M", time_.localtime()))
            live['times'][c] = fb
        if rec['date'] == '':
            rec['date'] = fb[0]
        if rec['time'] == '':
            rec['time'] = fb[1]
        if not DATE_RE.match(rec['date']) or not TIME_RE.match(rec['time']):
            return rec, False, False
        for k in REQUIRED_KEYS:
            if rec.get(k, '') == '':
                return rec, False, False
        return rec, True, False

    def _live_enable(io, keep=False):
        """为当前目标建立实时同步；读不出来就不启用（退回「完成时再写」）。

        keep=True 用于「取消勾选后又勾回来」：保留各列写进日志的位置，这样再改那一列
        时会就地更新，而不是再追加一条重复记录。
        """
        live['io'] = None
        live['active'] = False
        if not keep:
            live['pos'], live['wrote'], live['gone'] = {}, {}, []
        live['pending'] = False
        live['detached'] = []
        live['last'] = None
        if io is None:
            return False
        try:
            base, _token = io['read']()
        except Exception:
            return False
        if base is None:
            return False
        live['io'] = io
        live['last'] = list(base)
        live['active'] = True
        return True

    def _live_failed(err):
        """记录一次同步失败：只提示一次（别每敲一格弹一次），下次改动照常重试。"""
        if not live['warned']:
            live['warned'] = True
            try:
                from f_hamlog import toast_tip
                toast_tip.show_toast(i18n.tr('实时同步失败：{}').format(err),
                                     window, kind='warning')
            except Exception:
                pass
        return False

    def _live_shift_cols(at, delta, removed=None):
        """增删列之后重排下标键：写进日志的位置不变，只是列号挪了一格。

        removed：被删掉那一列写进日志的那条记录（位置已按删除前算好），交给下一次
        同步把它从日志里删掉——不能直接丢掉，否则日志里会留一条对不上的记录。
        """
        if removed is not None:
            live['gone'].append(removed)
        for name in ('wrote', 'pos', 'times'):
            old = live[name]
            new = {}
            for c, v in old.items():
                if c == at and removed is not None:
                    continue                 # 删掉的那一列：键跟着丢掉
                new[c + delta if c >= at else c] = v
            live[name] = new

    def _live_sync(force=False):
        """把表格里已经填完整的记录同步进目标日志；成功返回 True。

        做法：读目标日志的当前内容 → 对每一列，把「上次写进去的那一条」就地改成现在
        的内容（找不到就补一条）→ 列被删掉 / 被清空时，把之前写进去的那条拿掉。
        这样反复同步不会产生重复记录，也不会动到别人写进去的记录；没填完的列先跳过
        （日志里保留它上一次的完整内容，等填完再更新）。
        """
        if not live['active'] or live['hold']:
            return True
        if not cb_auto.isChecked():
            live['active'] = False
            return True
        io = live['io']
        if io is None:
            return True
        if not force and not live['pending']:
            return True

        cols, in_table = [], set()
        for c in range(1, table.columnCount()):
            rec, ok, empty = _col_record(c)
            if ok:
                cols.append((c, rec))
                in_table.add(c)
            elif not empty:
                in_table.add(c)      # 还在填：日志里那条先留着

        try:
            base, token = io['read']()
        except Exception as e:
            return _live_failed(e)
        if base is None:
            return _live_failed(i18n.tr('无法读取目标日志'))

        records = list(base)

        # ① 先删：列被删掉（_live_shift_cols 记的 gone）+ 列已被清空 / 不存在了
        doomed = list(live['gone'])
        for c, old in list(live['wrote'].items()):
            if c not in in_table:
                doomed.append((live['pos'].get(c), old))
        cut = []
        for i, rec in doomed:
            if i is None or not (0 <= i < len(records)) or i in cut:
                continue
            if rec is not None and records[i] == rec:
                cut.append(i)
        for i in sorted(cut, reverse=True):
            del records[i]
        live['gone'] = []

        def _adj(i):
            """删除之后的下标（左边删了几条就往前挪几格）。"""
            if i is None:
                return None
            return i - sum(1 for d in cut if d < i)

        pos, wrote = {}, {}
        writable = {c for c, _ in cols}

        # ② 没填完的列：日志里保留它上次写进去的那条，位置原地不动
        for c in in_table:
            if c in writable:
                continue
            old = live['wrote'].get(c)
            i = _adj(live['pos'].get(c))
            if old is not None and i is not None and 0 <= i < len(records) \
                    and records[i] == old:
                wrote[c] = old
                pos[c] = i

        # ③ 可写的列：就地更新上次写进去的那条，找不到就补一条
        for c, rec in cols:
            old = live['wrote'].get(c)
            i = _adj(live['pos'].get(c))
            if old is not None and i is not None and 0 <= i < len(records) \
                    and records[i] == old:
                records[i] = rec
                pos[c] = i
            elif old is not None and old in records and records.index(old) not in pos.values():
                # 位置对不上（文件被别的写入方动过）：按内容找回原记录，就地更新
                j = records.index(old)
                records[j] = rec
                pos[c] = j
            else:
                # 宁可多一条，也不要覆盖别人的记录
                records.append(rec)
                pos[c] = len(records) - 1
            wrote[c] = rec

        if not force and records == live['last']:
            # 内容没变（例如只改了模板列）→ 不写盘
            live['pos'], live['wrote'] = pos, wrote
            live['pending'] = False
            return True
        try:
            io['write'](records, token)
        except Exception as e:
            return _live_failed(e)
        live['last'] = records
        live['pos'], live['wrote'] = pos, wrote
        live['pending'] = False
        _bk_clear()          # 已写进日志 → 清掉「未保存批量记录」备份
        _bk_snapshot()       # 基线跟到当前表格：已同步的记录不再算未保存
        if _pending_input():
            _bk_write()      # 但没填完的列还在内存里，照样留一份备份（别在崩溃时丢掉）
        return True

    def _live_flush():
        """立刻把待同步的改动写进目标（点「完成」/ 关窗前）。"""
        try:
            live['timer'].stop()
        except Exception:
            pass
        return _live_sync()

    def _pending_input():
        """表格里还有「填了一半、还没写进日志」的列吗？

        实时同步时「已保存」= 记录已经写进日志文件；只有这种填了但没填完的列还在内存里，
        关窗会丢，所以要算作「未保存的更改」（关窗时问一句、并留备份）。
        """
        try:
            for c in range(1, table.columnCount()):
                _rec, ok, empty = _col_record(c)
                if not empty and not ok:
                    return True
        except Exception:
            return False
        return False

    def _live_touch():
        """表格有改动（编辑单元格 / 增删列）→ 稍后合并写一次。"""
        if live['hold'] or not live['active']:
            return
        live['pending'] = True
        live['timer'].start()

    live['flush'] = _live_flush

    # 由项目窗口启动（默认勾选）→ 立刻开始实时同步，目标就是那个项目的日志文件
    if cb_auto.isChecked() and on_saved is not None:
        if auto_target_path:
            live['target'] = ('append', auto_target_path)
        _live_enable(sync_io)


    # ---------- 未保存内容自动备份（batch_backup.fhl） ----------
    def _bk_cur_records():
        """从表格收集当前所有日志列（列>=1）为记录列表。"""
        recs = []
        for c in range(1, table.columnCount()):
            rec = {}
            for r in range(table.rowCount()):
                k = KEYS[r]
                it = table.item(r, c)
                rec[k] = it.text() if it is not None else ''
            recs.append(rec)
        return recs

    _bk_state = {'last': json.dumps(_bk_cur_records(), ensure_ascii=False, sort_keys=True)}

    def _bk_snapshot():
        _bk_state['last'] = json.dumps(_bk_cur_records(), ensure_ascii=False, sort_keys=True)

    def _bk_is_dirty():
        # 勾了「自动保存到日志文件」时先把待同步的改动写掉，再判断是否还有未保存内容：
        # 刚敲完就往 X 关窗（防抖还没到点）也应该是「已保存」，不该再问一次。
        _live_flush()
        if live['active']:
            # 实时同步下「已保存」= 已写进日志文件；只有没填完的列还在内存里
            return _pending_input()
        try:
            return json.dumps(_bk_cur_records(), ensure_ascii=False, sort_keys=True) != _bk_state['last']
        except Exception:
            return False

    def _bk_write():
        recs = _bk_cur_records()
        if not recs:
            backup.clear_backup(backup.BATCH_BACKUP)
            return
        backup.write_backup(backup.BATCH_BACKUP, recs, None)

    def _bk_clear():
        backup.clear_backup(backup.BATCH_BACKUP)

    def _bk_after_save():
        _bk_clear()
        _bk_snapshot()

    # 恢复场景：把上次未保存的批量记录回填到表格
    if preset_records:
        # 回填期间暂停实时同步：恢复出来的内容还没确认过，不能悄悄写进日志
        live['hold'] = True
        for _rec in preset_records:
            _data = [_rec.get(k, '') for k in KEYS]
            _insert_col(table.columnCount(), _data)
        live['hold'] = False
        live['pending'] = False

    # 打开批量记录时：把当前内容写入备份作为基线；若为空则清空
    _bk_snapshot()
    if _bk_cur_records():
        _bk_write()
    else:
        _bk_clear()
    # 恢复场景：回填内容尚未保存，强制标记为「未保存更改」（关闭时会再次提示保存/不保存/取消）
    if recovered:
        _bk_state['last'] = ''

    # 周期定时器：存在未保存更改时即时备份，覆盖意外关闭/崩溃场景
    _bk_timer = QTimer(window)
    _bk_timer.setInterval(1500)
    _bk_timer.timeout.connect(lambda: _bk_write() if _bk_is_dirty() else None)
    _bk_timer.start()

    backup.install_close_guard(window, {
        'is_dirty': _bk_is_dirty,
        'write_backup': _bk_write,
        'clear_backup': _bk_clear,
        'do_save': lambda: save_all(),
    })

    layout.addWidget(table)

    def collect_and_validate():
        """从日志列（列>=1）收集记录，返回 (records, error_msg)。"""
        records = []
        for c in range(1, table.columnCount()):
            col_label = (table.horizontalHeaderItem(c).text()
                         if table.horizontalHeaderItem(c) is not None else f'第{c}条')
            rec = {}
            empty = True
            for r in range(table.rowCount()):
                key = KEYS[r]
                v = table.item(r, c).text() if table.item(r, c) is not None else ''
                rec[key] = v
                if v != '':
                    empty = False
            if empty:
                continue  # 整列空白视为未填写，跳过
            # 日期/时间为空则自动填充当前时间
            if rec['date'] == '':
                rec['date'] = time_.strftime("%Y-%m-%d", time_.localtime())
            if rec['time'] == '':
                rec['time'] = time_.strftime("%H:%M", time_.localtime())
            # 校验
            if rec['date'] != '' and not DATE_RE.search(rec['date']):
                return None, f'{col_label} 日期格式错误，应为YYYY-MM-DD'
            if rec['time'] != '' and not TIME_RE.search(rec['time']):
                return None, f'{col_label} 时间格式错误，应为HH:MM'
            for k in REQUIRED_KEYS:
                if rec[k] == '':
                    return None, f'{col_label} 缺少 {translation_dict[k]} (必填)'
            records.append(rec)
        return records, ''

    def _live_message(count):
        """「完成」时的提示：说清这次写到了哪个日志。"""
        target = live.get('target')
        if target is None:
            return f'已添加 {count} 条记录到当前项目。'
        return done_message(target, count)

    def _strip_synced(records):
        """取消勾选「自动保存」后又点「完成」：把已经实时同步过的那几条剔掉。

        不这么做的话，中途取消勾选再点完成，同一批记录会被**再追加一遍**——日志里
        就多出一份重复记录。只在目标还是同一个日志时才剔（换了去处当然要全写）。
        """
        if not live['detached']:
            return list(records)
        out = list(records)
        for old in live['detached']:
            try:
                out.remove(old)
            except ValueError:
                pass
        return out

    def save_all():
        records, err = collect_and_validate()
        if err:
            QMessageBox.warning(window, '格式错误', err)
            return False

        fhl_list = records  # 供下方保存逻辑使用（与旧逻辑保持一致）

        # 「自动保存到日志文件」+ 实时同步
        #   每次改格子 / 增删列都已经把记录写进目标日志了（见 _live_sync），这里只要
        #   把最后一点待同步的改动补上就能关窗——**不再**整份追加一遍，否则就是重复记录。
        # 补同步失败（例如原项目窗口已被关掉）不吞掉记录：提示一句后落到下面的选择页。
        if cb_auto.isChecked() and live['active']:
            if _live_flush():
                if fhl_list:
                    QMessageBox.information(window, '完成', _live_message(len(fhl_list)))
                return True
            QMessageBox.warning(window, '保存失败',
                                '实时同步没有成功，请在下一步选择保存位置。')

        if not fhl_list:
            QMessageBox.warning(window, '提示', '没有可保存的记录（日志列均为空）。')
            return False

        # 勾了自动保存、但这个目标做不了实时同步（多人日志 / 加密日志没密钥 /
        # 项目还没有保存路径）→ 仍按原来的方式：点「完成」一次性写过去。
        if cb_auto.isChecked() and not live['active']:
            done = False
            write_list = _strip_synced(fhl_list)   # 中途取消过勾选的话，已同步的别再写一遍
            if on_saved is not None:
                if not write_list:
                    QMessageBox.information(window, '完成', _live_message(len(fhl_list)))
                    return True
                try:
                    on_saved(write_list)
                except Exception as e:
                    QMessageBox.warning(window, '保存失败',
                                        f'添加到项目失败：\n{e}\n\n请在下一步选择保存位置。')
                else:
                    QMessageBox.information(window, '完成',
                                            f'已添加 {len(write_list)} 条记录到当前项目。')
                    done = True
            elif auto_pick['target'] is not None:
                if not write_list:
                    QMessageBox.information(
                        window, '完成', done_message(auto_pick['target'], len(fhl_list)))
                    return True
                try:
                    apply_save_target(auto_pick['target'], write_list)
                except Exception as e:
                    QMessageBox.warning(window, '保存失败',
                                        f'保存失败：\n{e}\n\n请在下一步选择保存位置。')
                else:
                    QMessageBox.information(window, '完成',
                                            done_message(auto_pick['target'], len(write_list)))
                    done = True
            if done:
                _bk_after_save()
                return True

        # 没勾自动保存（或实时同步不可用）→ 打开「保存到哪里」选择页：
        # 与勾选时的提示是同一个界面，用户只会看到一种选择方式。
        target = choose_save_target(
            window, '已成功录入 {} 条记录'.format(len(fhl_list)))
        if target is None:
            return False                # 取消：窗口保持打开，记录还在
        # 中途取消过勾选、又选回同一个日志 → 已经同步过的那几条别再追加一遍
        write_list = fhl_list
        if live['detached'] and live['target'] is not None \
                and target[:2] == live['target'][:2]:
            write_list = _strip_synced(fhl_list)
        if not write_list:
            QMessageBox.information(window, '完成', done_message(target, len(fhl_list)))
            _bk_after_save()
            return True
        try:
            apply_save_target(target, write_list)
        except Exception as e:
            QMessageBox.warning(window, '保存失败', f'保存失败：\n{e}')
            return False
        QMessageBox.information(window, '完成', done_message(target, len(write_list)))
        _bk_after_save()
        return True

    # 按钮区（按钮文字与提示中显示对应快捷键，方便查看）
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    button_add = QPushButton('添加日志列 (Ctrl+N)')
    button_add.setMinimumHeight(34)
#     button_add.setToolTip('新建一条日志列（Ctrl+N）')
    button_add.clicked.connect(add_log_column)

    button_del = QPushButton('删除当前列 (Ctrl+D)')
    button_del.setMinimumHeight(34)
#     button_del.setToolTip('删除当前选中的日志列（Ctrl+D，模板列不可删除）')
    button_del.clicked.connect(delete_current_column)

    button_undo = QPushButton('撤销 (Ctrl+Z)')
    button_undo.setMinimumHeight(34)
#     button_undo.setToolTip('撤销上一步操作（Ctrl+Z）')
    button_undo.clicked.connect(do_undo)
    button_undo.setEnabled(undo_stack.canUndo())
    undo_stack.canUndoChanged.connect(button_undo.setEnabled)

    button_redo = QPushButton('重做 (Ctrl+Y)')
    button_redo.setMinimumHeight(34)
#     button_redo.setToolTip('重做（Ctrl+Y 或 Ctrl+Shift+Z）')
    button_redo.clicked.connect(do_redo)
    button_redo.setEnabled(undo_stack.canRedo())
    undo_stack.canRedoChanged.connect(button_redo.setEnabled)

    def _finish_save():
        # 保存成功则关闭窗口；取消/失败则保持打开
        if save_all():
            window.close()

    button_save = QPushButton('完成 (Ctrl+S)')
    button_save.setMinimumHeight(34)
#     button_save.setToolTip('保存全部记录（Ctrl+S）')
    button_save.clicked.connect(_finish_save)

    btn_row.addWidget(button_add)
    btn_row.addWidget(button_del)
    btn_row.addWidget(button_undo)
    btn_row.addWidget(button_redo)
    btn_row.addStretch(1)
    btn_row.addWidget(button_save)

    layout.addLayout(btn_row)

    # 快捷键说明（始终可见）：列出全部按钮与导航快捷键
    hint = QLabel('快捷键：Ctrl+←/→ 上一条/下一条 · Ctrl+N 新建 · Ctrl+D 删除 · '
                  'Ctrl+Z 撤销 · Ctrl+Y 重做 · Ctrl+S 完成')
    hint.setStyleSheet('font-size:9pt;')
    layout.addWidget(hint)

    # 次要文字色（时钟、快捷键提示）统一跟随系统主题：深浅色下都保持可读
    def apply_theme_colors():
        _hint = theme.hint_color().name()
        clock_label.setStyleSheet('color:%s; font-size:9pt; padding:2px 0;' % _hint)
        hint.setStyleSheet('color:%s; font-size:9pt;' % _hint)

    apply_theme_colors()
    theme.watch_theme(window, apply_theme_colors)

    # 让 Ctrl+S 在未编辑（按钮/窗口聚焦）与编辑中（编辑器聚焦）时都能触发保存
    nav_filter.do_save = _finish_save

    window.show()
    # 打开即聚焦「对方呼号」，方便直接输入（等窗口显示/冻结层几何就绪后再聚焦）
    QTimer.singleShot(0, lambda: focus_o_call(0))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    i18n.install(app)
    win = QMainWindow()
    main(win)
    app.exec()
