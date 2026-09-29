"""星历(TLE) 数据源设置——**独立窗口** + **独立配置文件**。

打开方式：主页「设置」→「星历数据源…」按钮，或直接调用 main(window)。

功能：
  - 列表即下载顺序：先列出的数据源优先，同一颗卫星（按 NORAD 编号）以列表中先出现的为准；
  - 每行左侧的方框是**启用开关**：只有启用的数据源才参与下载（至少保留一个启用）；
  - **双击某一行即可就地编辑**该地址（回车确认 / 取消放弃）；
  - **自动测延迟**：打开本窗口、以及改完地址 / 新添加地址后，都会在后台自动测一遍
    响应延迟并显示在行尾，不需要点任何「测试」按钮；
  - 添加 / 删除 / 上移 / 下移 / 恢复默认；
  - 改动先在窗口内暂存（**不自动保存**），点「保存」写入独立文件
    file/tle_sources.txt（每行一个地址，地址前加 # 表示禁用），**保存成功后自动关闭窗口**；
  - 直接关闭窗口不做任何提示：未保存的更改直接丢弃，文件内容不受影响。

数据源不再保存在设置文件 m_xml.txt 里；早期版本遗留的旧键会在保存时清理
（见 satellite_pred.save_tle_source_entries / drop_legacy_tle_sources）。
"""

import os

from PySide6.QtCore import QEvent, QObject, QRect, Qt, QThread, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import *

import satellite_pred as sp
import theme

WINDOW_W, WINDOW_H = 660, 430

# 列表里长地址的省略方式：中间省略，保证「协议+主机」和「文件名」都看得见
_ELIDE = Qt.TextElideMode.ElideMiddle

# 行数据角色：延迟文本 / 探测令牌 / 基准启用状态（基准地址沿用 Qt.UserRole）
_ROLE_DELAY = Qt.ItemDataRole.UserRole + 1
_ROLE_TOKEN = Qt.ItemDataRole.UserRole + 2
_ROLE_ENABLED = Qt.ItemDataRole.UserRole + 3
_ROLE_OK = Qt.ItemDataRole.UserRole + 4      # True/False/None（未测）
_ROLE_MS = Qt.ItemDataRole.UserRole + 5

# 正在跑的延迟探测线程：模块级持有引用，避免窗口被关闭、回收后线程对象被 GC 掉
# 而报「QThread: Destroyed while thread is still running」。
_ACTIVE_PROBES = []


def _hint_css():
    """次要提示色：跟随主题（写死 gray 在深色底上偏暗）。"""
    return theme.hint_css()


def _warn_css():
    """警告提示色：深色主题下自动提亮，写死 #c0392b 会看不清。"""
    return theme.warn_css()


def _list_qss():
    """选中项用主题链接色 + 透明背景（保留斑马纹底色）。"""
    return ("QListWidget::item:selected { background: transparent; color: %s; }"
            % theme.link_color().name())


def _display_path(path):
    """把绝对路径显示为相对程序目录的短路径，便于在界面上提示保存位置。"""
    try:
        rel = os.path.relpath(path, sp.app_path('.'))
    except Exception:
        return path
    if rel.startswith('..'):
        return path
    return rel.replace('\\', '/')


class SourceItemDelegate(QStyledItemDelegate):
    """列表项自绘：左侧地址（过长中间省略），右端灰色显示延迟摘要。

    延迟刻意**不写进 item.text()**——`text()` 始终只是地址本身（解析与保存都用它），
    否则「显示」和「数据」会互相污染。禁用的源整行文字用次要提示色画淡。
    """

    def sizeHint(self, option, index):
        """把行宽收窄到视口宽度。

        默认实现按「整条地址」算宽度，视图据此算出比视口宽的contents → 出现横向
        滚动条，而且右端延迟会被推到可视区之外（这正是自绘延迟必须处理的一点）。
        """
        size = super().sizeHint(option, index)
        view = option.widget
        if isinstance(view, QAbstractItemView):
            size.setWidth(view.viewport().width())
        return size

    def paint(self, painter, option, index):
        delay = index.data(_ROLE_DELAY) or ''
        if not delay:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        fm = opt.fontMetrics
        right = fm.horizontalAdvance(delay) + fm.horizontalAdvance('00')
        full = QRect(opt.rect)
        # ① 整行先铺一次底色/选中态，这样右端延迟文字背后也有高亮背景
        base = QStyleOptionViewItem(opt)
        base.text = ''
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, widget)
        # ② 未启用的源：文字用次要提示色，看起来「灰掉」
        if index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked:
            pal = QPalette(opt.palette)
            hint = theme.hint_color(widget)
            pal.setColor(QPalette.ColorRole.Text, hint)
            pal.setColor(QPalette.ColorRole.HighlightedText, hint)
            opt.palette = pal
        # ③ 地址只占左侧，过长中间省略
        opt.rect = full.adjusted(0, 0, -right, 0)
        opt.text = fm.elidedText(opt.text, _ELIDE, max(0, opt.rect.width() - 8))
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        # ④ 右端延迟
        painter.save()
        painter.setPen(theme.hint_color(widget))
        painter.drawText(full.adjusted(0, 0, -6, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         delay)
        painter.restore()


class DelayProbeWorker(QThread):
    """后台逐个测数据源延迟，每测完一个就发一次结果。

    只测、不碰界面：结果带回「探测令牌」，由界面按令牌找回对应行
    （行被删掉、或地址被改过 → 令牌已换 → 旧结果直接丢弃）。
    """

    result = Signal(int, str, bool, int, str)   # token, url, ok, ms, err

    def __init__(self, jobs, timeout=sp.TLE_PROBE_TIMEOUT, parent=None):
        super().__init__(parent)
        self._jobs = list(jobs)          # [(token, url)]
        self._timeout = timeout
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        for token, url in self._jobs:
            if self._cancel:
                return
            ok, ms, err = sp.probe_tle_source(url, self._timeout)
            if self._cancel:
                return
            self.result.emit(token, url, ok, ms, err)


def _close_watcher(callback, parent=None):
    """在窗口收到 Close/Destroy 事件时回调一次（用于收尾后台线程）。"""

    class _Watcher(QObject):
        def eventFilter(self, obj, event):
            if event.type() in (QEvent.Type.Close, QEvent.Type.Destroy):
                callback()
            return False

    watcher = _Watcher(parent)
    return watcher


def main(window=None, on_save=None):
    """构建「星历数据源」窗口。window 缺省时自建一个 QMainWindow。

    on_save：可选回调，每次成功保存后调用一次（供调用方刷新摘要等）。

    窗口显示后会自动在后台测一遍各数据源的响应延迟（见 satellite_pred.
    probe_tle_source）；无需任何「测试」按钮。
    """
    if window is None:
        window = QMainWindow()
    win = window
    win.setWindowTitle('星历数据源')
    win.resize(WINDOW_W, WINDOW_H)
    win.setFixedSize(WINDOW_W, WINDOW_H)

    central = QWidget()
    win.setCentralWidget(central)
    layout = QVBoxLayout(central)

    path_text = _display_path(sp.TLE_SOURCES_PATH)

    tip = QLabel(
        '按列表顺序读取已启用的数据源；同一颗卫星（按 NORAD 编号）以先出现的为准。\n'
        '左侧方框为启用开关；双击地址即可编辑（回车确认、Esc 取消）。\n'
        '打开本窗口或改完地址会自动测试各源延迟，无需手动操作；点「保存」后写入：%s'
        % path_text, central)
    tip.setStyleSheet(_hint_css())
    tip.setWordWrap(True)
    layout.addWidget(tip)

    # ---------- 数据源列表 ----------
    src_list = QListWidget(central)
    # 默认编辑触发器即「双击 / F2」，这里显式写出，保证「双击即可编辑」不被主题改掉
    src_list.setEditTriggers(
        QAbstractItemView.EditTrigger.DoubleClicked |
        QAbstractItemView.EditTrigger.EditKeyPressed)
    src_list.setTextElideMode(_ELIDE)
    src_list.setAlternatingRowColors(True)
    src_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    # 行宽固定为视口宽（见 SourceItemDelegate.sizeHint），地址靠省略显示，
    # 因此不需要横向滚动条
    src_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    # 自绘：左边地址、右边延迟（延迟不进 item.text()）
    src_list.setItemDelegate(SourceItemDelegate(src_list))
#     src_list.setToolTip(
#         '双击某一项即可编辑地址（需以 http:// 或 https:// 开头）。\n'
#         '行尾显示的是自动测得的响应延迟。')
    # 选中行不整行填充蓝色：用主题链接色文字 + 透明背景表示选中（保留斑马纹底色）
    src_list.setStyleSheet(_list_qss())
    layout.addWidget(src_list, 1)

    status = QLabel('', central)
    status.setStyleSheet(_hint_css())
    layout.addWidget(status)

    # 记住最后一次状态文字与是否为警告，主题切换时据此重刷颜色
    _status = {'text': '双击某行即可编辑；更改后点「保存」写入文件。', 'warn': False}

    def _set_status(text, warn=False):
        """统一设置状态文字与颜色（记住状态，便于主题切换时重刷）。"""
        _status['text'], _status['warn'] = text, warn
        status.setText(text)
        status.setStyleSheet(_warn_css() if warn else _hint_css())

    # ---------- 按钮 ----------
    btn_row = QHBoxLayout()
    add_btn = QPushButton('添加', central)
    del_btn = QPushButton('删除', central)
    up_btn = QPushButton('上移', central)
    down_btn = QPushButton('下移', central)
    reset_btn = QPushButton('恢复默认', central)
    save_btn = QPushButton('保存', central)
    close_btn = QPushButton('关闭', central)
#     add_btn.setToolTip('插入一个空行并进入编辑：可直接输入 TLE 下载地址（可为 Celestrak 之外的镜像）')
#     del_btn.setToolTip('删除选中项（至少保留一个数据源）')
#     up_btn.setToolTip('上移：提高优先级')
#     down_btn.setToolTip('下移：降低优先级')
#     reset_btn.setToolTip('恢复为内置默认数据源（Celestrak 全部活动卫星）')
#     save_btn.setToolTip('把当前列表写入配置文件，并关闭本窗口')
#     close_btn.setToolTip('关闭本窗口（未保存的更改将被丢弃）')
    btn_row.addWidget(add_btn)
    btn_row.addWidget(del_btn)
    btn_row.addWidget(up_btn)
    btn_row.addWidget(down_btn)
    btn_row.addWidget(reset_btn)
    btn_row.addStretch(1)
    btn_row.addWidget(save_btn)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    # _busy：重建列表 / 规范化回写 / 写延迟数据时屏蔽 itemChanged，避免递归与误判
    _busy = {'flag': False}
    # _dirty：有未保存的更改（点「保存」才落盘）
    _dirty = {'flag': False}
    # 窗口是否还活着：关窗后到达的探测结果直接丢弃（那时控件已被销毁）
    _alive = {'flag': True}
    # 探测令牌发号器 + 待回结果的条数（用于状态栏汇总）
    _seq = {'n': 0, 'pending': 0}

    def _guarded(fn):
        """在屏蔽 itemChanged 的前提下改一个 item（改文本 / 勾选 / 写延迟都用它）。

        保存并恢复调用前的屏蔽状态，因此可以安全嵌套（_reload 里会再调 _make_item）。
        """
        prev = _busy['flag']
        _busy['flag'] = True
        try:
            fn()
        finally:
            _busy['flag'] = prev

    def _set_item_text(item, text):
        _guarded(lambda: item.setText(text))

    def _set_item_checked(item, checked):
        _guarded(lambda: item.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked))

    def _set_item_delay(item, text):
        _guarded(lambda: item.setData(_ROLE_DELAY, text))
        _refresh_item_tooltip(item)

    def _refresh_item_tooltip(item):
        """行提示：地址 + 启用状态 + 最近一次延迟。"""
        url = item.text().strip()
        checked = item.checkState() == Qt.CheckState.Checked
        delay = item.data(_ROLE_DELAY) or '尚未测试'
#         item.setToolTip('%s\n%s ｜ 延迟：%s\n（双击可编辑地址，方框切换启用）'
#                         % (url, '已启用' if checked else '已禁用', delay))

    def _entries():
        """当前列表内容（含启用状态），顺序即优先级。"""
        out = []
        for i in range(src_list.count()):
            item = src_list.item(i)
            url = item.text().strip()
            if not url:
                continue
            out.append((url, item.checkState() == Qt.CheckState.Checked))
        return out

    def _checked_count():
        return sum(1 for _, enabled in _entries() if enabled)

    def _make_item(url, enabled=True):
        item = QListWidgetItem(url)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable
                      | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.UserRole, url)          # 已提交的地址，编辑校验失败时回滚
        item.setData(_ROLE_ENABLED, bool(enabled))
        _guarded(lambda: item.setCheckState(
            Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked))
        item.setData(_ROLE_DELAY, '')
        item.setData(_ROLE_OK, None)
        item.setData(_ROLE_MS, -1)
        _refresh_item_tooltip(item)
        return item

    def _row():
        return src_list.currentRow()

    def _normalize_entries(items):
        """把「地址字符串」或「(地址, 启用)」两种写法统一成 (地址, 启用)。"""
        out = []
        for it in (items or []):
            if isinstance(it, (tuple, list)) and len(it) == 2:
                out.append((str(it[0]).strip(), bool(it[1])))
            else:
                out.append((str(it).strip(), True))
        return [e for e in out if e[0]]

    def _reload(entries=None):
        """按给定列表（缺省读数据源文件）重建列表控件。"""
        if entries is None:
            entries = sp.load_tle_source_entries()
            if not entries:
                # 无独立文件 / 文件里没有数据行 → 走完整读取链（旧设置键 → 内置默认）
                entries = [(u, True) for u in sp.load_tle_sources()]
        entries = _normalize_entries(entries)
        _busy['flag'] = True
        try:
            src_list.clear()
            for url, enabled in entries:
                src_list.addItem(_make_item(url, enabled))
        finally:
            _busy['flag'] = False
        if src_list.count():
            src_list.setCurrentRow(0)
        _refresh_buttons()

    # ---------- 延迟探测（打开即测；改完地址 / 添加后自动重测该行） ----------

    def _emit_summary():
        """一次探测批次跑完后在状态栏给个汇总（有失败才告警）。"""
        total = src_list.count()
        ok_n = failed = 0
        fastest = -1
        for i in range(total):
            item = src_list.item(i)
            state = item.data(_ROLE_OK)
            if state is True:
                ok_n += 1
                ms = item.data(_ROLE_MS)
                if isinstance(ms, int) and ms >= 0 and (fastest < 0 or ms < fastest):
                    fastest = ms
            elif state is False:
                failed += 1
        if failed:
            _set_status('延迟测试完成：%d 个数据源中 %d 个无法访问。'
                        % (total, failed), True)
        elif ok_n:
            tail = ('，最快 %d ms' % fastest) if fastest >= 0 else ''
            _set_status('延迟测试完成：%d 个数据源均可访问%s。' % (ok_n, tail))
        else:
            _set_status('双击某行即可编辑；更改后点「保存」写入文件。')

    def _stop_probes():
        """关窗收尾：取消在跑的探测线程（避免线程未结束就被销毁）。"""
        _alive['flag'] = False
        running = list(_ACTIVE_PROBES)
        for worker in running:
            worker.cancel()
        for worker in running:
            if worker.isRunning():
                worker.wait(2000)

    def _on_probe_result(token, url, ok, ms, err):
        if not _alive['flag']:
            return          # 窗口已关闭：控件可能已销毁，直接丢弃
        _seq['pending'] = max(0, _seq['pending'] - 1)
        item = None
        for i in range(src_list.count()):
            if src_list.item(i).data(_ROLE_TOKEN) == token:
                item = src_list.item(i)
                break
        if item is not None and item.text().strip() == url:
            _guarded(lambda it=item, o=ok, m=ms: (it.setData(_ROLE_OK, o),
                                                 it.setData(_ROLE_MS, m)))
            _set_item_delay(item, ('%d ms' % ms) if ok else (err or '不可用'))
        if _seq['pending'] == 0 and not _dirty['flag']:
            _emit_summary()

    def _probe(items):
        """给这些行各自发一个探测任务（换新令牌 → 旧的在途结果自动作废）。

        不写状态文字：行内已显示「测试中…」，状态栏留给「未保存」这类提示。
        """
        jobs = []
        for item in items:
            if not (item.text() or '').strip():
                continue
            _seq['n'] += 1
            token = _seq['n']
            _guarded(lambda it=item, tk=token: it.setData(_ROLE_TOKEN, tk))
            _set_item_delay(item, '测试中…')
            jobs.append((token, item.text().strip()))
        if not jobs:
            return
        _seq['pending'] += len(jobs)
        worker = DelayProbeWorker(jobs)
        worker.result.connect(_on_probe_result)
        worker.finished.connect(lambda w=worker: _drop_probe(w))
        _ACTIVE_PROBES.append(worker)
        worker.start()

    def _drop_probe(worker):
        try:
            _ACTIVE_PROBES.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _probe_all():
        """整表探测：打开窗口 / 恢复默认后调用。"""
        if not _dirty['flag']:
            _set_status('正在自动测试各数据源延迟…')
        _probe([src_list.item(i) for i in range(src_list.count())])

    def _save():
        """把当前列表写入独立文件；返回是否成功。"""
        try:
            saved = sp.save_tle_source_entries(_entries())
        except Exception as e:
            _set_status('保存失败：%s' % e, True)
            return False
        _dirty['flag'] = False
        _refresh_buttons()
        n_on = sum(1 for _, enabled in saved if enabled)
        _set_status('已保存：%d 个数据源（%d 个已启用）' % (len(saved), n_on))
        # 规整后与界面不一致（例如全被删空而回落到默认）时，以文件内容为准刷新界面
        if _normalize_entries(saved) != _entries():
            _reload(saved)
        if on_save is not None:
            try:
                on_save()
            except Exception as e:
                print('[星历数据源] 保存回调异常：%s' % e)
        return True

    def _mark_unsaved(note):
        """界面已改动但尚未写文件：置脏标记并提示。"""
        _dirty['flag'] = True
        _refresh_buttons()
        _set_status('%s（未保存，点「保存」写入文件）' % note)

    def on_item_changed(item):
        """itemChanged 同时覆盖「改地址」与「勾选/取消启用」，这里一并处理。"""
        if _busy['flag'] or item is None:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        # ---- ① 启用状态变化 ----
        if checked != bool(item.data(_ROLE_ENABLED)):
            if not checked and _checked_count() == 0:
                # 不允许把最后一个启用的源也关掉（文件里必须至少留一个可用源）
                _set_item_checked(item, True)
                _set_status('未修改：至少需要保留一个启用的数据源。', True)
                _beep()
                return
            _guarded(lambda: item.setData(_ROLE_ENABLED, checked))
            _refresh_item_tooltip(item)
            _mark_unsaved('已修改启用状态')
            _probe([item])          # 启用/禁用都重测一次，便于判断要不要启用
            return
        # ---- ② 地址文本变化 ----
        old = item.data(Qt.UserRole) or ''
        new = (item.text() or '').strip()
        if new == old:
            if item.text() != old:
                _set_item_text(item, old)   # 只有首尾空白不同，规范回写
            return
        if not new:
            _revert(item, old, '地址不能为空。')
            return
        if not sp.is_valid_tle_source(new):
            _revert(item, old, '地址需以 http:// 或 https:// 开头。')
            return
        others = [src_list.item(i).text().strip()
                  for i in range(src_list.count())
                  if src_list.item(i) is not item]
        if new in others:
            _revert(item, old, '该地址已在列表中。')
            return
        item.setData(Qt.UserRole, new)
        if item.text() != new:
            _set_item_text(item, new)
        _refresh_item_tooltip(item)
        _mark_unsaved('已修改')
        _probe([item])              # 改完地址马上自动重测这一行

    def _beep():
        try:
            QApplication.beep()
        except Exception:
            pass

    def _revert(item, old, why):
        _set_item_text(item, old)
        _set_status('未修改：%s' % why, True)
        _beep()

    def add_source():
        # 不弹输入对话框：直接插入一个空行，并进入内联编辑态，用户可立即输入地址；
        # 校验（http(s) 开头 / 去重 / 非空）沿用双击编辑的 on_item_changed 逻辑。
        # 若已有一行空行在等待填写，则聚焦并编辑它，避免重复创建。
        for i in range(src_list.count()):
            if not src_list.item(i).text().strip():
                src_list.setCurrentRow(i)
                src_list.editItem(src_list.item(i))
                return
        item = _make_item('', True)
        src_list.addItem(item)
        src_list.setCurrentRow(src_list.count() - 1)
        src_list.editItem(item)      # 打开内联编辑器，直接填写地址（无需对话框）

    def del_source():
        row = _row()
        if row < 0:
            _set_status('请先选中要删除的数据源。', True)
            return
        if src_list.count() <= 1:
            QMessageBox.information(win, '删除星历数据源',
                                    '至少需要保留一个数据源。')
            return
        src_list.takeItem(row)
        if src_list.count():
            src_list.setCurrentRow(min(row, src_list.count() - 1))
        _mark_unsaved('已删除')

    def move_source(delta):
        row = _row()
        new_row = row + delta
        if row < 0 or not (0 <= new_row < src_list.count()):
            return
        item = src_list.takeItem(row)
        src_list.insertItem(new_row, item)
        src_list.setCurrentRow(new_row)
        _mark_unsaved('已调整顺序')

    def reset_sources():
        again = QMessageBox.question(
            win, '恢复默认数据源',
            '将把数据源恢复为内置默认（Celestrak 全部活动卫星），'
            '当前列表中的自定义地址会被清除（保存后才会写入文件）。是否继续？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if again != QMessageBox.StandardButton.Yes:
            return
        _reload([(u, True) for u in sp.DEFAULT_TLE_SOURCES])
        _probe_all()                # 新列表的延迟重新测一遍
        _mark_unsaved('已恢复默认')

    def _refresh_buttons():
        """没有选中项时禁用「删除/上移/下移」；有未保存更改时才启用「保存」。"""
        has = src_list.currentItem() is not None
        for btn in (del_btn, up_btn, down_btn):
            btn.setEnabled(has)
        save_btn.setEnabled(_dirty['flag'])

    src_list.itemChanged.connect(on_item_changed)
    src_list.itemSelectionChanged.connect(lambda: _refresh_buttons())
    add_btn.clicked.connect(add_source)
    del_btn.clicked.connect(del_source)
    up_btn.clicked.connect(lambda: move_source(-1))
    down_btn.clicked.connect(lambda: move_source(1))
    reset_btn.clicked.connect(reset_sources)
    save_btn.clicked.connect(lambda: _save() and win.close())
    # 关闭不做任何提示：未保存的更改直接丢弃（但要先把探测线程停掉）
    close_btn.clicked.connect(lambda: win.close())

    _reload()
    _set_status('双击某行即可编辑；更改后点「保存」写入文件。')
    for i in range(src_list.count()):
        _refresh_item_tooltip(src_list.item(i))

    # 主题变化时重刷提示/选中/状态颜色（写死颜色在深色主题下会看不清）
    def _refresh_theme():
        tip.setStyleSheet(_hint_css())
        src_list.setStyleSheet(_list_qss())
        _set_status(_status['text'], _status['warn'])
        src_list.viewport().update()    # 自绘的延迟文字颜色也要重画

    theme.watch_theme(win, _refresh_theme)

    # 关窗/销毁时收尾后台探测线程
    win._delay_close_watcher = _close_watcher(_stop_probes, win)
    win.installEventFilter(win._delay_close_watcher)

    # 打开设置页即自动测延迟（不用手动开启）
    _probe_all()

    win.show()
    return win


if __name__ == '__main__':
    app = QApplication()
    main(QMainWindow())
    app.exec()
