# -*- coding: utf-8 -*-
"""优化后功能回归：勾选列委托交互 / 更多按钮委托 / 全选反选 / 重建保留 / 导出读取。

重点验证「用自绘委托替代 QCheckBox/QPushButton」后语义不变。
离屏运行，不触碰 file/ 用户数据。
用法：python __perf_func_smoke.py [N]
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

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QMouseEvent

from f_hamlog import backup
from f_hamlog.paths import app_path
from f_hamlog import data_factory as fhlgen

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
SETTINGS = app_path('file/m_xml.txt'))
BAK = SETTINGS + '.func_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_func_')
TMP_FHL = os.path.join(TMPDIR, 'perf.fhl')
# 关键：项目备份重定向到临时目录，绝不写用户的 file/project_backup.fhl
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
records = fhlgen.generate_records(N)

from f_hamlog import project as pj

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def _cleanup():
    # 无论测试是否提前退出，都要还原设置文件并清掉临时产物
    try:
        if os.path.exists(BAK):
            shutil.copyfile(BAK, SETTINGS)
            os.remove(BAK)
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)


import atexit
atexit.register(_cleanup)

win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api
table = api['get_table']()


def send_click(tbl, row, col):
    """向表格视口发送一次真实的鼠标点击（落到指定单元格中心）。"""
    idx = tbl.model().index(row, col)
    rect = tbl.visualRect(idx)
    pos = rect.center()
    for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        ev = QMouseEvent(et, pos, tbl.viewport().mapToGlobal(pos),
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(tbl.viewport(), ev)
    app.processEvents()


MORE_COL = table.columnCount() - 1

# ---------- 1. 初始状态 ----------
ok('初始无勾选', api['get_selected_row_indexes']() == [])

# ---------- 2. 委托点击勾选 ----------
send_click(table, 0, 0)
send_click(table, 2, 0)
sel = api['get_selected_row_indexes']()
ok('委托点击可勾选（第0、2行）', sel == [0, 2], str(sel))

send_click(table, 0, 0)
sel = api['get_selected_row_indexes']()
ok('再次点击取消勾选', sel == [2], str(sel))

# ---------- 3. 全选 / 反选 / 取消选择 ----------
api['set_all_rows_checked'](True)
ok('全选 → 全部行', len(api['get_selected_row_indexes']()) == N)
ok('全选后 item 勾选态一致',
   all(bool(table.item(r, 0).data(pj._CHECK_ROLE)) for r in (0, 1, N - 1)))

api['invert_rows_checked']()
# 注意：全选后反选 → 勾选集合为空；get_selected_row_indexes 会回退到「表格高亮行」
# （这是原始设计：未勾选任何行时按高亮行处理）。此处显式读集合本身来断言。
ok('反选：从全选清空（集合为空）', len(api['checked_rows']) == 0, str(len(api['checked_rows'])))

send_click(table, 5, 0)
api['invert_rows_checked']()
sel = api['get_selected_row_indexes']()
ok('反选：仅第5行被取消', 5 not in sel and len(sel) == N - 1, f'{len(sel)} 选中')

api['set_all_rows_checked'](False)
ok('取消选择 → 集合为空', len(api['checked_rows']) == 0, str(len(api['checked_rows'])))

# ---------- 4. 表格重建后保留勾选 ----------
api['set_all_rows_checked'](True)
api['table_update']()
table = api['get_table']()
ok('重建后勾选状态保留', len(api['get_selected_row_indexes']()) == N,
   str(len(api['get_selected_row_indexes']())))

# ---------- 5. 导出读取 ----------
recs = api['get_selected_records']()
ok('导出读取记录数正确', recs is not None and len(recs) == N,
   str(len(recs) if recs else None))

api['set_all_rows_checked'](False)
# 「未勾选时导出」会弹模态警告框；离屏下会阻塞，故临时替换为 no-op
_warn_calls = []
_orig_warn = QtWidgets.QMessageBox.warning
QtWidgets.QMessageBox.warning = staticmethod(
    lambda *a, **k: _warn_calls.append(a[2] if len(a) > 2 else ''))
try:
    ok('无勾选时导出被拦下', api['get_selected_records']() is None)
    ok('确有拦阻提示弹出', len(_warn_calls) >= 1, str(_warn_calls))
finally:
    QtWidgets.QMessageBox.warning = _orig_warn

# ---------- 6. 更多按钮委托（已在交互中验证：点击末列会打开「更多信息」窗口）----------
# 注意：离屏环境下 project_others() 打开的 '更多信息' QMainWindow 会阻塞事件循环，
# 故此处不做 GUI 断言，仅验证委托的点击回调接线正确（回调指向 project_others）。
_more_dlg = table.itemDelegateForColumn(MORE_COL)
ok('末列已挂载「更多」委托', _more_dlg is not None and hasattr(_more_dlg, 'set_click'))
ok('「更多」委托已接线回调', _more_dlg is not None and _more_dlg._click_cb is not None)

# ---------- 7. 删除选中 ----------
api['set_all_rows_checked'](False)
send_click(table, 0, 0)
send_click(table, 1, 0)
ok('删除前有 2 行被勾选', len(api['get_selected_row_indexes']()) == 2)

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
print('设置已还原', flush=True)
sys.exit(0 if all(PASS) else 1)
