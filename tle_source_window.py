"""星历(TLE) 数据源设置——**独立窗口** + **独立配置文件**。

打开方式：主页「设置」→「星历数据源…」按钮，或直接调用 main(window)。

功能：
  - 列表即下载顺序：先列出的数据源优先，同一颗卫星（按 NORAD 编号）以列表中先出现的为准；
  - **双击某一行即可就地编辑**该地址（回车确认 / 取消放弃）；
  - 添加 / 删除 / 上移 / 下移 / 恢复默认；
  - 改动先在窗口内暂存（**不自动保存**），点「保存」写入独立文件
    file/tle_sources.txt（每行一个地址，可用记事本直接改），**保存成功后自动关闭窗口**；
  - 直接关闭窗口不做任何提示：未保存的更改直接丢弃，文件内容不受影响。

数据源不再保存在设置文件 m_xml.txt 里；早期版本遗留的旧键会在保存时清理
（见 satellite_pred.save_tle_sources / drop_legacy_tle_sources）。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

import satellite_pred as sp

WINDOW_W, WINDOW_H = 660, 430

# 列表里长地址的省略方式：中间省略，保证「协议+主机」和「文件名」都看得见
_ELIDE = Qt.TextElideMode.ElideMiddle

_HINT_COLOR = 'color: gray;'
_WARN_COLOR = 'color: #c0392b;'


def _display_path(path):
    """把绝对路径显示为相对程序目录的短路径，便于在界面上提示保存位置。"""
    try:
        rel = os.path.relpath(path, sp.app_path('.'))
    except Exception:
        return path
    if rel.startswith('..'):
        return path
    return rel.replace('\\', '/')


def main(window=None, on_save=None):
    """构建「星历数据源」窗口。window 缺省时自建一个 QMainWindow。

    on_save：可选回调，每次成功保存后调用一次（供调用方刷新摘要等）。
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
        '下载卫星星历时按列表顺序依次读取；同一颗卫星（按 NORAD 编号）'
        '以列表中先出现的数据源为准。\n'
        '双击某一行即可直接编辑地址（回车确认、Esc 取消）；点「保存」后写入：%s'
        % path_text, central)
    tip.setStyleSheet(_HINT_COLOR)
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
    src_list.setToolTip(
        '双击某一项即可编辑；地址需以 http:// 或 https:// 开头。')
    # 选中行不整行填充蓝色：用蓝色文字 + 透明背景表示选中（保留斑马纹底色）
    src_list.setStyleSheet(
        "QListWidget::item:selected { background: transparent; color: #1f5bb5; }")
    layout.addWidget(src_list, 1)

    status = QLabel('', central)
    status.setStyleSheet(_HINT_COLOR)
    layout.addWidget(status)

    # ---------- 按钮 ----------
    btn_row = QHBoxLayout()
    add_btn = QPushButton('添加', central)
    del_btn = QPushButton('删除', central)
    up_btn = QPushButton('上移', central)
    down_btn = QPushButton('下移', central)
    reset_btn = QPushButton('恢复默认', central)
    save_btn = QPushButton('保存', central)
    close_btn = QPushButton('关闭', central)
    add_btn.setToolTip('添加一个 TLE 下载地址（可为 Celestrak 之外的镜像）')
    del_btn.setToolTip('删除选中项（至少保留一个数据源）')
    up_btn.setToolTip('上移：提高优先级')
    down_btn.setToolTip('下移：降低优先级')
    reset_btn.setToolTip('恢复为内置默认数据源（Celestrak 全部活动卫星）')
    save_btn.setToolTip('把当前列表写入配置文件，并关闭本窗口')
    close_btn.setToolTip('关闭本窗口（未保存的更改将被丢弃）')
    btn_row.addWidget(add_btn)
    btn_row.addWidget(del_btn)
    btn_row.addWidget(up_btn)
    btn_row.addWidget(down_btn)
    btn_row.addWidget(reset_btn)
    btn_row.addStretch(1)
    btn_row.addWidget(save_btn)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    # _busy：重建列表 / 规范化回写时屏蔽 itemChanged，避免递归与误判
    _busy = {'flag': False}
    # _dirty：有未保存的更改（点「保存」才落盘）
    _dirty = {'flag': False}

    def _set_item_text(item, text):
        _busy['flag'] = True
        try:
            item.setText(text)
        finally:
            _busy['flag'] = False

    def _make_item(url):
        item = QListWidgetItem(url)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(Qt.UserRole, url)   # 已提交的地址，用于编辑校验失败时回滚
        item.setToolTip('%s\n（双击可编辑）' % url)
        return item

    def _urls():
        return [src_list.item(i).text().strip()
                for i in range(src_list.count())
                if src_list.item(i).text().strip()]

    def _row():
        return src_list.currentRow()

    def _reload(urls=None):
        """按给定列表（缺省读数据源文件）重建列表控件。"""
        if urls is None:
            urls = sp.load_tle_sources()
        _busy['flag'] = True
        try:
            src_list.clear()
            for url in urls:
                src_list.addItem(_make_item(url))
        finally:
            _busy['flag'] = False
        if src_list.count():
            src_list.setCurrentRow(0)
        _refresh_buttons()

    def _save():
        """把当前列表写入独立文件；返回是否成功。"""
        try:
            saved = sp.save_tle_sources(_urls())
        except Exception as e:
            status.setStyleSheet(_WARN_COLOR)
            status.setText('保存失败：%s' % e)
            return False
        _dirty['flag'] = False
        _refresh_buttons()
        status.setStyleSheet(_HINT_COLOR)
        status.setText('已保存：%d 个数据源' % len(saved))
        # 规整后与界面不一致（例如全被删空而回落到默认）时，以文件内容为准刷新界面
        if saved != _urls():
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
        status.setStyleSheet(_HINT_COLOR)
        status.setText('%s（未保存，点「保存」写入文件）' % note)

    def on_item_changed(item):
        """就地编辑提交后的校验：规范化文本、拒绝非法/重复地址并回滚。"""
        if _busy['flag'] or item is None:
            return
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
        item.setToolTip('%s\n（双击可编辑）' % new)
        _mark_unsaved('已修改')

    def _revert(item, old, why):
        _set_item_text(item, old)
        status.setStyleSheet(_WARN_COLOR)
        status.setText('未修改：%s' % why)
        try:
            QApplication.beep()
        except Exception:
            pass

    def add_source():
        url, ok = QInputDialog.getText(
            win, '添加星历数据源',
            'TLE 数据下载地址：')
        if not ok:
            return
        url = (url or '').strip()
        if not url:
            return
        if not sp.is_valid_tle_source(url):
            QMessageBox.warning(win, '添加星历数据源',
                                '地址需以 http:// 或 https:// 开头。')
            return
        if url in _urls():
            QMessageBox.information(win, '添加星历数据源', '该地址已在列表中。')
            return
        src_list.addItem(_make_item(url))
        src_list.setCurrentRow(src_list.count() - 1)
        _mark_unsaved('已添加')

    def del_source():
        row = _row()
        if row < 0:
            status.setStyleSheet(_WARN_COLOR)
            status.setText('请先选中要删除的数据源。')
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
        _reload(list(sp.DEFAULT_TLE_SOURCES))
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
    # 关闭不做任何提示：未保存的更改直接丢弃
    close_btn.clicked.connect(lambda: win.close())

    _reload()
    status.setText('双击某行即可编辑；更改后点「保存」写入文件。')
    win.show()
    return win


if __name__ == '__main__':
    app = QApplication()
    main(QMainWindow())
    app.exec()
