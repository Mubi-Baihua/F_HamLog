# -*- coding: utf-8 -*-
"""主表「选中一格」冒烟：确认表格是单元格选择模式，点哪格只亮哪格，
且复制/删除用的「选中行」仍能由选中格正确推导。

离屏运行；设置与项目文件均重定向到临时目录，绝不触碰用户真实数据。
"""
import os
import sys
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QAbstractItemView

from f_hamlog import backup
from f_hamlog.paths import app_path
from f_hamlog import data_factory as fhlgen

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.cs_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_cs_')
TMP_FHL = os.path.join(TMPDIR, 'cs.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
records = fhlgen.generate_records(N)

from f_hamlog import project as pj

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
for _ in range(5):
    app.processEvents()

table = win._perf_api['get_table']()
print('行为 =', table.selectionBehavior(), '模式 =', table.selectionMode(), flush=True)
ok('表格为单元格选择（SelectItems）',
   table.selectionBehavior() == QAbstractItemView.SelectItems,
   str(table.selectionBehavior()))

# 点击第 3 行、第 4 列：只应选中这一格
row, col = 3, 4
table.scrollToItem(table.item(row, 0))
for _ in range(3):
    app.processEvents()
idx = table.model().index(row, col)
pos = table.visualRect(idx).center()
for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
    app.sendEvent(table.viewport(), QMouseEvent(
        et, pos, table.viewport().mapToGlobal(pos),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
for _ in range(3):
    app.processEvents()

cells = list(table.selectionModel().selectedIndexes())
print('选中格 =', [(i.row(), i.column()) for i in cells], flush=True)
ok('只选中被点的那一格', cells == [idx], str([(i.row(), i.column()) for i in cells]))
ok('selectedRows() 在此模式下为空（已改用 selectedIndexes 取行）',
   list(table.selectionModel().selectedRows()) == [])

# 复制逻辑：未勾选时应按选中格回退到行号
api = win._perf_api
rows = api['get_selected_row_indexes']()
ok('选中格能推导出该行', rows == [row], str(rows))

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
print(f"\n通过 {sum(PASS)} / {len(PASS)}")
print('RESULT=' + ('ALL PASS' if all(PASS) else 'HAS FAIL'))
