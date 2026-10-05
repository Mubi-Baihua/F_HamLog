# -*- coding: utf-8 -*-
"""删除日志的两项修复回归（离屏，不触碰 file/ 用户数据）：

1. 删除后弹悬浮通知：批量删除 → 「已删除 N 条日志。」；单条删除 → 「已删除 1 条日志。」
2. 删除后勾选状态不得错位到别的日志上：
   - 勾选删除：删完必须清空勾选集合（旧的删前行号不能套用到剩余日志）；
   - 单条删除（「更多」窗）：被删行之后的勾选行号整体前移 1，勾选仍锁定同一条日志。

用法：python test/__delete_select_smoke.py
"""
import os
import sys
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# 槽函数里的 sys.exit() 从 PySide6 C++ 边界直接终止进程，测试前屏蔽
sys.exit = lambda *a, **k: None

from PySide6 import QtWidgets
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QMouseEvent

from f_hamlog import backup
from f_hamlog.paths import app_path
from f_hamlog import data_factory as fhlgen

N = 40
SETTINGS = app_path('file/m_xml.txt'))
BAK = SETTINGS + '.delsel_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_delsel_')
TMP_FHL = os.path.join(TMPDIR, 'delsel.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


def mk(i):
    """每条记录的「对方呼号」列写成唯一可辨识的 T000..Txxx，方便断言身份。"""
    rec = fhlgen.make_record(i)
    rec['o_call'] = f'C{i:03d}'
    rec['notes'] = f'生成日志 {i + 1}'
    return rec


records = [mk(i) for i in range(N)]

from f_hamlog import project as pj

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def _cleanup():
    try:
        if os.path.exists(BAK):
            shutil.copyfile(BAK, SETTINGS)
            os.remove(BAK)
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)


import atexit
atexit.register(_cleanup)

# ---- 拦截二次确认与悬浮通知 ----
# question 一律返回 No：若代码里还残留确认弹窗，删除就会被拦下 → 断言立刻失败。
# 同时记录调用次数，用来断言「不再弹确认、直接删」。
TOASTS = []
ASKED = []
pj.QMessageBox.question = staticmethod(
    lambda *a, **k: (ASKED.append(a[1] if len(a) > 1 else ''), pj.QMessageBox.No)[1])
pj.toast_tip.show_toast = lambda text, parent=None, timeout=1000, kind='info': TOASTS.append((text, kind))

win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api

O_CALL_COL = 4  # 「对方呼号」列


def send_click(tbl, row, col):
    idx = tbl.model().index(row, col)
    pos = tbl.visualRect(idx).center()
    for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        ev = QMouseEvent(et, pos, tbl.viewport().mapToGlobal(pos),
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(tbl.viewport(), ev)
    app.processEvents()


def calls(tbl):
    return [tbl.item(r, O_CALL_COL).text() for r in range(tbl.rowCount())]


def checked_calls(tbl):
    """当前显示为勾选的行（读 item 的 _CHECK_ROLE），返回其呼号列表。"""
    return [tbl.item(r, O_CALL_COL).text() for r in range(tbl.rowCount())
            if bool(tbl.item(r, 0).data(pj._CHECK_ROLE))]


table = api['get_table']()
ok('初始 40 行', table.rowCount() == N, str(table.rowCount()))
ok('初始无勾选', len(api['checked_rows']) == 0)

# ---------- 1. 勾选 1/3/5 行 → 删除 → 有通知、勾选不错位 ----------
for r in (1, 3, 5):
    send_click(table, r, 0)
ok('点选第 1/3/5 行', api['get_selected_row_indexes']() == [1, 3, 5],
   str(api['get_selected_row_indexes']()))

TOASTS.clear()
before = calls(table)   # 表格载入时会排序，展示顺序 ≠ 生成顺序，故按当前展示顺序取快照
api['delete_selected_logs']()
table = api['get_table']()
ok('勾选删除：未弹二次确认（直接删）', ASKED == [], str(ASKED))
ok('勾选删除：提示已弹出', len(TOASTS) == 1, str(TOASTS))
ok('勾选删除：提示文案为「已删除 3 条日志。」',
   TOASTS and TOASTS[0][0] == '已删除 3 条日志。', str(TOASTS))
ok('勾选删除：行数 40→37', table.rowCount() == N - 3, str(table.rowCount()))
ok('勾选删除：删掉的正是被勾选的 3 行且其余顺序不变',
   calls(table) == [c for i, c in enumerate(before) if i not in (1, 3, 5)],
   str(calls(table)[:8]))
ok('勾选删除：勾选集合已清空', len(api['checked_rows']) == 0, str(sorted(api['checked_rows'])))
ok('勾选删除：无任何行残留勾选', checked_calls(table) == [], str(checked_calls(table)))
ok('勾选删除：未回退选中其它日志', api['get_selected_row_indexes']() == [],
   str(api['get_selected_row_indexes']()))

# ---------- 1b. 已取消二次确认 → 删错也能撤销回来 ----------
api['undo']()
table = api['get_table']()
ok('删除后可撤销（Ctrl+Z 还原 40 行）', table.rowCount() == N, str(table.rowCount()))
ok('撤销后记录顺序完全复原', calls(table) == before, str(calls(table)[:6]))
# 再删一次，回到后续用例需要的前置状态
send_click(table, 1, 0)
send_click(table, 3, 0)
send_click(table, 5, 0)
api['delete_selected_logs']()
table = api['get_table']()

# ---------- 2. 纯高亮（不勾选）删除：同样有通知、无残留勾选 ----------
before = calls(table)
table.setRangeSelected(QtWidgets.QTableWidgetSelectionRange(10, 0, 12, table.columnCount() - 1), True)
app.processEvents()
ok('高亮删除：此时勾选集合为空', len(api['checked_rows']) == 0)

TOASTS.clear()
api['delete_selected_logs']()
table = api['get_table']()
removed = [before[i] for i in (10, 11, 12)]
ok('高亮删除：未弹二次确认（直接删）', ASKED == [], str(ASKED))
ok('高亮删除：提示已弹出', TOASTS and TOASTS[0][0] == '已删除 3 条日志。', str(TOASTS))
ok('高亮删除：3 条被移除', table.rowCount() == N - 6, str(table.rowCount()))
ok('高亮删除：移除的是高亮的 3 行',
   all(c not in calls(table) for c in removed), str(removed))
ok('高亮删除：无残留勾选', checked_calls(table) == [] and len(api['checked_rows']) == 0,
   str(checked_calls(table)))

# ---------- 3. 「更多」窗内单条删除：勾选行号整体前移，不错位 ----------
table = api['get_table']()
cur = calls(table)
target_row = cur.index('C010')     # 待删除行
keep_row = cur.index('C030')       # 紧跟其后的勾选行（行号 > target_row）
send_click(table, keep_row, 0)
ok('单条删除前：C030 已勾选', checked_calls(table) == ['C030'], str(checked_calls(table)))

TOASTS.clear()
api['project_others'](target_row)
for _ in range(3):
    app.processEvents()
dlg = None
for w in app.topLevelWidgets():
    if w.windowTitle() == '更多信息':
        dlg = w
ok('「更多」窗已打开', dlg is not None)
btn = None
for b in (dlg.findChildren(QtWidgets.QPushButton) if dlg is not None else []):
    if b.text() == '删除日志':
        btn = b
ok('找到「删除日志」按钮', btn is not None)
btn.click()
for _ in range(3):
    app.processEvents()
table = api['get_table']()
ok('单条删除：未弹二次确认（直接删）', ASKED == [], str(ASKED))
ok('单条删除：提示已弹出', TOASTS and TOASTS[0][0] == '已删除 1 条日志。', str(TOASTS))
ok('单条删除：C010 已删除', 'C010' not in calls(table), str(calls(table)[:14]))
ok('单条删除：勾选仍锁定同一条日志（C030）', checked_calls(table) == ['C030'],
   str(checked_calls(table)))
ok('单条删除：行数再 -1', table.rowCount() == N - 7, str(table.rowCount()))

print()
print(f'== {sum(PASS)}/{len(PASS)} 通过 ==')
sys.stdout.flush()
_cleanup()          # 显式清理：下面的 os._exit 会跳过 atexit
os._exit(0 if all(PASS) else 1)
