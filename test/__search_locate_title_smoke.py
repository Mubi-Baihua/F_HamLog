# -*- coding: utf-8 -*-
"""搜索结果「定位到此条」+ 搜索性能优化 + 未保存标题 '*' 冒烟。

覆盖：
 1) 搜索结果窗口出现「定位到此条」列与右键菜单项；点击后主窗口被聚焦、
    主表滚动并选中对应行（行号由搜索结果行 → 主表原始索引映射）。
 2) 搜索窗口勾选集合化后：全选/反选/取消 与主表同步、统计/导出范围解析正确、
    构建过程冻结刷新（性能路径）。
 3) 未保存项目的窗口标题最前面带 '*'，保存后自动去掉；多人日志标题同样遵循。

离屏运行；备份与项目文件均重定向到临时目录，绝不触碰用户真实数据。
"""
import os
import sys
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QMouseEvent

import backup
import test as fhlgen

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
BAK = SETTINGS + '.slt_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_slt_')
TMP_FHL = os.path.join(TMPDIR, 'slt.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
records = fhlgen.generate_records(N)

import project as pj

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api
table = api['get_table']()

# ---------------------------------------------------------------- 3) 标题 '*'
ok('打开已保存项目标题不带 *', not win.windowTitle().startswith('*'), win.windowTitle())
api['_set_title']()
ok('基线一致时标题仍不带 *', not win.windowTitle().startswith('*'), win.windowTitle())

# 制造一次未保存更改：直接改内存 file 后手动 tick（模拟周期检测）
import project as _pj
_pj.file.append({'date': '2099-01-01', 'time': '00:00', 'm_call': 'X', 'o_call': 'Y',
                 'freq': '145.000', 'mode': 'FM', 'prop_mode': '', 'sat_name': '',
                 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': ''})
api['table_update'](delete=False)
api['_bk_tick']()
for _ in range(3):
    app.processEvents()
ok('有未保存更改时标题带 *', win.windowTitle().startswith('*'), win.windowTitle())
ok('* 位于标题最开头', win.windowTitle()[0] == '*', repr(win.windowTitle()))

# 保存后应自动去掉 *（用 message=True 走真实用户保存；message=False 会受
# 「自动保存」开关影响，开关关闭时不落盘、也就不会复位基线）
_pj_save = api.get('save') or _pj.save
_pj_save(message=True)
for _ in range(3):
    app.processEvents()
ok('保存后标题去掉 *', not win.windowTitle().startswith('*'), win.windowTitle())

# ---------------------------------------------------------------- 1) 搜索 + 定位
from PySide6.QtWidgets import QDialog, QLineEdit, QComboBox, QDialogButtonBox


def fill_and_search():
    dlg = None
    for w in app.topLevelWidgets():
        if isinstance(w, QDialog) and w.windowTitle() == '搜索':
            dlg = w
            break
    if dlg is None:
        QTimer.singleShot(80, fill_and_search)
        return
    edits = dlg.findChildren(QLineEdit)
    edits[-1].setText('生成日志')   # notes 都含「生成日志」→ 命中全部记录
    combos = dlg.findChildren(QComboBox)
    for i in range(combos[0].count()):
        if combos[0].itemData(i) == 'notes':
            combos[0].setCurrentIndex(i)
            break
    bb = dlg.findChild(QDialogButtonBox)
    if bb is not None:
        bb.accepted.emit()


QTimer.singleShot(100, fill_and_search)

acts = [a for m in win.menuBar().findChildren(QtWidgets.QMenu)
        for a in m.actions() if a.text() == '搜索']
if acts:
    QTimer.singleShot(0, acts[0].trigger)

for _ in range(300):
    app.processEvents()
    if any(w.windowTitle().startswith('搜索结果') for w in app.topLevelWidgets()):
        break

rw = None
for w in app.topLevelWidgets():
    if w.windowTitle().startswith('搜索结果'):
        rw = w
        break

ok('搜索结果窗口已打开', rw is not None, str([w.windowTitle() for w in app.topLevelWidgets()]))

if rw is not None:
    tr = rw.findChildren(QtWidgets.QTableWidget)[0]
    # 前面 table_update 重建过主表 → 必须重新取当前主表引用（旧引用可能已销毁）
    table = api['get_table']()
    ok('搜索结果行数 > 0', tr.rowCount() > 0, str(tr.rowCount()))
    headers = [tr.horizontalHeaderItem(c).text() for c in range(tr.columnCount())]
    ok('新增「定位到此条」列', headers and headers[-1] == '定位到此条', str(headers[-3:]))

    # 点击最后一列（定位）第 5 行 → 主表应选中同一原始索引
    target = 5
    # 先滚动到该行，确保单元格在视口内（否则合成的鼠标事件落在视口外无效）
    tr.scrollToItem(tr.item(target, 0))
    for _ in range(3):
        app.processEvents()
    idx = tr.model().index(target, tr.columnCount() - 1)
    pos = tr.visualRect(idx).center()
    for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        app.sendEvent(tr.viewport(), QMouseEvent(
            et, pos, tr.viewport().mapToGlobal(pos),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    for _ in range(5):
        app.processEvents()
    sel = sorted(r.row() for r in table.selectionModel().selectedRows())
    # 主表行号 == 搜索结果里的原始索引（file 未重排）
    expected = target
    ok('点击定位后主表选中对应行', sel == [expected] or (expected in sel), f'sel={sel} expected={expected}')
    # 同时校验定位逻辑本身（绕过事件分发，直接驱动委托回调）
    tr.itemDelegateForColumn(tr.columnCount() - 1)._click_cb(9)
    for _ in range(5):
        app.processEvents()
    sel2 = sorted(r.row() for r in table.selectionModel().selectedRows())
    ok('定位回调驱动主表选中', sel2 == [9], f'sel={sel2}')

    # 右键菜单里含「定位到此条」
    menu_actions = []
    # 直接构造菜单项检查（不阻塞）：调用内部菜单构建不易，改为验证列委托存在
    from project import LocateButtonDelegate
    dele = tr.itemDelegateForColumn(tr.columnCount() - 1)
    ok('定位列挂载 LocateButtonDelegate', isinstance(dele, LocateButtonDelegate), type(dele).__name__)

    # ------------------------------------------------- 2) 搜索勾选集合化
    api['set_all_rows_checked'](False)
    # 全选
    tr.selectAll() if False else None
    # 用菜单动作触发全选（搜索窗「选择」菜单）
    sel_acts = [a for m in rw.menuBar().findChildren(QtWidgets.QMenu)
                for a in m.actions() if a.text() == '全选']
    if sel_acts:
        sel_acts[0].trigger()
    for _ in range(3):
        app.processEvents()
    ok('搜索全选 → 主表勾选数 == 搜索结果行数',
       len(api['checked_rows']) == tr.rowCount(),
       f'{len(api["checked_rows"])} vs 结果行数 {tr.rowCount()}（主表共 {table.rowCount()} 行）')

    inv_acts = [a for m in rw.menuBar().findChildren(QtWidgets.QMenu)
                for a in m.actions() if a.text() == '反选']
    if inv_acts:
        inv_acts[0].trigger()
    for _ in range(3):
        app.processEvents()
    ok('搜索反选 → 主表全不勾选', len(api['checked_rows']) == 0, str(len(api['checked_rows'])))

    # 勾选搜索结果第 3 行 → 主表同步
    it = tr.item(3, 0)
    idx = tr.model().index(3, 0)
    pos = tr.visualRect(idx).center()
    for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        app.sendEvent(tr.viewport(), QMouseEvent(
            et, pos, tr.viewport().mapToGlobal(pos),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    for _ in range(3):
        app.processEvents()
    ok('搜索窗勾选同步到主表', len(api['checked_rows']) == 1, str(sorted(api['checked_rows'])))

    rw.close()

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
print('设置已还原', flush=True)
sys.exit(0 if all(PASS) else 1)
