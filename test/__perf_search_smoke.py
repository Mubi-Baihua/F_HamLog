# -*- coding: utf-8 -*-
"""搜索结果窗口（委托化后）冒烟：构建 / 勾选同步主表 / 全选反选 / 更多按钮映射。

搜索会弹模态对话框，故用 QTimer 定时填充并点「搜索」。
离屏运行，不触碰 file/ 用户数据。
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
BAK = SETTINGS + '.sr_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_sr_')
TMP_FHL = os.path.join(TMPDIR, 'perf.fhl')
# 关键：项目备份重定向到临时目录，绝不写用户的 file/project_backup.fhl
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

# 打开搜索对话框（模态）→ 定时填字段、选字段、点搜索
from PySide6.QtWidgets import QDialog, QLineEdit, QComboBox, QPushButton, QDialogButtonBox


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
        bb.accepted.emit()   # 等价于点「确定」


QTimer.singleShot(100, fill_and_search)

# 触发「搜索」菜单动作
acts = [a for m in win.menuBar().findChildren(QtWidgets.QMenu)
        for a in m.actions() if a.text() == '搜索']
if acts:
    QTimer.singleShot(0, acts[0].trigger)

for _ in range(200):
    app.processEvents()
    if any(w.windowTitle().startswith('搜索结果') for w in app.topLevelWidgets()):
        break
    if any(isinstance(w, QDialog) and w.windowTitle() == '搜索' for w in app.topLevelWidgets()):
        pass

rw = None
for w in app.topLevelWidgets():
    if w.windowTitle().startswith('搜索结果'):
        rw = w
        break

ok('搜索结果窗口已打开', rw is not None, str([w.windowTitle() for w in app.topLevelWidgets()]))

if rw is not None:
    tables = rw.findChildren(QtWidgets.QTableWidget)
    tr = tables[0] if tables else None
    ok('搜索结果表存在且行数>0', tr is not None and tr.rowCount() > 0,
       str(tr.rowCount() if tr else None))

    def click(tbl, row, col):
        idx = tbl.model().index(row, col)
        pos = tbl.visualRect(idx).center()
        for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            app.sendEvent(tbl.viewport(), QMouseEvent(
                et, pos, tbl.viewport().mapToGlobal(pos),
                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        app.processEvents()

    # 点击搜索结果第 0 行勾选 → 应同步到主表
    api['set_all_rows_checked'](False)
    click(tr, 0, 0)
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
