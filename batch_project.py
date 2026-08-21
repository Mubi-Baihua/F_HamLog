from PySide6.QtWidgets import *
from PySide6.QtGui import QUndoStack, QUndoCommand
from PySide6.QtCore import Qt, QTimer, QObject, QEvent, qInstallMessageHandler
import call_upper
from dialog_defaults import desktop_dir
import time as time_
import sys
import re
import os
import datetime
import fhl_rw


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
        self._frozen.setStyleSheet("QTableView{ border:none; background-color:#f3f3f3; }")
        self.viewport().stackUnder(self._frozen)
        self._frozen.raise_()
        self._frozen.show()
        # 第 0 列宽度双向同步：主表和冻结层都能拖拽/调整，且避免递归循环
        self.horizontalHeader().sectionResized.connect(self._sync_frozen_from_main)
        self._frozen.horizontalHeader().sectionResized.connect(self._sync_main_from_frozen)
        self.sync_frozen_columns()
        # 垂直滚动同步（双向，带防抖）
        self.verticalScrollBar().valueChanged.connect(self._sync_from_main)
        self._frozen.verticalScrollBar().valueChanged.connect(self._sync_from_frozen)

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


def main(window, preset=None, on_saved=None):
    _install_qt_msg_filter()  # 过滤冻结列良性 Qt 警告
    window.resize(1200, 790)
    window.setWindowTitle('批量记录')

    with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
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
    clock_label.setStyleSheet('color:#444; font-size:9pt; padding:2px 0;')
    clock_label.setAlignment(Qt.AlignLeft)

    def update_clock():
        """刷新时钟标签：UTC 与本地时间（含本地 UTC 偏移）。"""
        fmt = '%Y-%m-%d %H:%M:%S'
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = datetime.datetime.now()
        tz = now_local.astimezone().strftime('%z')  # 形如 '+0800'
        tz_disp = ('UTC%s:%s' % (tz[:3], tz[3:])) if tz else 'UTC'
        clock_label.setText('UTC %s   |   本地 %s (%s)'
                            % (now_utc.strftime(fmt), now_local.strftime(fmt), tz_disp))

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
    opt_row.addStretch(1)
    layout.addLayout(opt_row)

    # 表格：行=字段，列0=模板，初始无日志列（默认不要日志）
    table = FrozenTableWidget(len(KEYS), 1)
    table.setVerticalHeaderLabels(list(translation_dict.values()))
    # 行高与 project.py 主表一致：使用 Qt 默认行高，不设自定义值

    # 冻结模板列开关（默认开启）；在 table 创建后再连接
    cb_freeze.toggled.connect(table.set_frozen)

    def refresh_headers():
        headers = ['模板'] + [f'第{i}条' for i in range(1, table.columnCount())]
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

    def _remove_col(c):
        _set_suspend(True)
        table.removeColumn(c)
        refresh_headers()
        table.updateFrozenGeometry()
        _set_suspend(False)

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

    def save_all():
        records, err = collect_and_validate()
        if err:
            QMessageBox.warning(window, '格式错误', err)
            return
        if not records:
            QMessageBox.warning(window, '提示', '没有可保存的记录（日志列均为空）。')
            return

        fhl_list = records  # 供下方保存逻辑使用（与旧逻辑保持一致）

        # 若由卫星窗口（项目界面）传入 on_saved，则直接追加到项目文件，不弹保存方式选择
        if on_saved is not None:
            try:
                on_saved(fhl_list)
                QMessageBox.information(window, '完成',
                                        f'已添加 {len(fhl_list)} 条记录到当前项目。')
            except Exception as e:
                QMessageBox.warning(window, '保存失败',
                                    f'添加到项目失败：\n{e}')
            window.close()
            return

        if not fhl_list:
            QMessageBox.warning(window, "提示", "没有可保存的记录。")
            return

        def save_records_to_path(records, save_path, key=None):
            fhl_rw.write_fhl_file(save_path, records, key)

        def load_records_from_path(load_path):
            if not os.path.exists(load_path):
                return [], None
            data, key = fhl_rw.read_fhl_file(load_path)
            return data, key

        finish_dialog = QDialog(window)
        finish_dialog.setWindowTitle('批量记录完成')
        finish_dialog.resize(520, 120)
        finish_dialog.setFixedSize(520, 120)
        finish_dialog.setModal(True)

        finish_layout = QVBoxLayout(finish_dialog)
        finish_layout.setSpacing(12)

        title_label = QLabel('请选择保存方式：')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        finish_layout.addWidget(title_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.setContentsMargins(0, 0, 0, 0)

        def add_to_project():
            project_path, _ = QFileDialog.getOpenFileName(
                finish_dialog,
                '添加到 F HamLog项目',
                desktop_dir(),
                'F HamLog项目 (*.fhl)'
            )
            if project_path == '':
                return
            records, key = load_records_from_path(project_path)
            records.extend(fhl_list)
            save_records_to_path(records, project_path, key)
            QMessageBox.information(finish_dialog, '完成', f'已添加 {len(fhl_list)} 条记录到项目。')
            finish_dialog.accept()

        def save_as_project():
            save_path, _ = QFileDialog.getSaveFileName(
                finish_dialog,
                '另存为 F HamLog项目',
                desktop_dir(),
                'F HamLog项目 (*.fhl)'
            )
            if save_path == '':
                return
            save_records_to_path(fhl_list, save_path)
            QMessageBox.information(finish_dialog, '完成', f'已另存为项目文件：{save_path}')
            finish_dialog.accept()

        def add_to_default_log():
            default_path = os.path.join('file', 'main.fhl')
            records, key = load_records_from_path(default_path)
            records.extend(fhl_list)
            save_records_to_path(records, default_path, key)
            QMessageBox.information(finish_dialog, '完成', f'已添加 {len(fhl_list)} 条记录到默认通联日志')
            finish_dialog.accept()

        btn_project = QPushButton('添加到 F HamLog 项目')
        btn_project.setMinimumHeight(36)
        btn_project.clicked.connect(add_to_project)
        action_row.addWidget(btn_project)

        btn_save_as = QPushButton('另存为 F HamLog 项目')
        btn_save_as.setMinimumHeight(36)
        btn_save_as.clicked.connect(save_as_project)
        action_row.addWidget(btn_save_as)

        btn_default = QPushButton('添加到默认通联日志')
        btn_default.setMinimumHeight(36)
        btn_default.clicked.connect(add_to_default_log)
        action_row.addWidget(btn_default)

        finish_layout.addLayout(action_row)

        cancel_button = QPushButton('取消')
        cancel_button.clicked.connect(finish_dialog.reject)
        finish_layout.addWidget(cancel_button, alignment=Qt.AlignRight)

        finish_dialog.exec()

    # 按钮区（按钮文字与提示中显示对应快捷键，方便查看）
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    button_add = QPushButton('添加日志列 (Ctrl+N)')
    button_add.setMinimumHeight(34)
    button_add.setToolTip('新建一条日志列（Ctrl+N）')
    button_add.clicked.connect(add_log_column)

    button_del = QPushButton('删除当前列 (Ctrl+D)')
    button_del.setMinimumHeight(34)
    button_del.setToolTip('删除当前选中的日志列（Ctrl+D，模板列不可删除）')
    button_del.clicked.connect(delete_current_column)

    button_undo = QPushButton('撤销 (Ctrl+Z)')
    button_undo.setMinimumHeight(34)
    button_undo.setToolTip('撤销上一步操作（Ctrl+Z）')
    button_undo.clicked.connect(do_undo)
    button_undo.setEnabled(undo_stack.canUndo())
    undo_stack.canUndoChanged.connect(button_undo.setEnabled)

    button_redo = QPushButton('重做 (Ctrl+Y)')
    button_redo.setMinimumHeight(34)
    button_redo.setToolTip('重做（Ctrl+Y 或 Ctrl+Shift+Z）')
    button_redo.clicked.connect(do_redo)
    button_redo.setEnabled(undo_stack.canRedo())
    undo_stack.canRedoChanged.connect(button_redo.setEnabled)

    button_save = QPushButton('完成 (Ctrl+S)')
    button_save.setMinimumHeight(34)
    button_save.setToolTip('保存全部记录（Ctrl+S）')
    button_save.clicked.connect(save_all)

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
    hint.setStyleSheet('color:#666; font-size:9pt;')
    layout.addWidget(hint)

    # 让 Ctrl+S 在未编辑（按钮/窗口聚焦）与编辑中（编辑器聚焦）时都能触发保存
    nav_filter.do_save = save_all

    window.show()
    # 打开即聚焦「对方呼号」，方便直接输入（等窗口显示/冻结层几何就绪后再聚焦）
    QTimer.singleShot(0, lambda: focus_o_call(0))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()
