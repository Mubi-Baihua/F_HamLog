# -*- coding: utf-8 -*-
"""打开项目不再「先显示第 1 行、再闪到底部」。

背景：`table_update(scroll_to_bottom=True)` 原来只写 `QTimer.singleShot(0, scrollToBottom)`，
定位被推到**首帧绘制之后** → 打开项目能看见一次可见的跳动。现在改成「滚动范围一变
（rangeChanged，发生在 show() 里、绘制之前）就把滚动条贴到底部」，首帧即最终位置。

同时覆盖另一个坑：范围会分几次定稿（滚动条是否占位也影响最大值），第一次贴底后
就摘监听会停在 max-2 → 必须等稳定后再摘。

用法：QT_QPA_PLATFORM=offscreen python tests/__open_no_jump_smoke.py [N]
"""
import os
import sys
import shutil
import tempfile
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QObject, QEvent
from PySide6 import QtWidgets

from f_hamlog.paths import app_path
from f_hamlog import backup

N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.nj_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_nojump_')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print("[%s] %s%s" % ('PASS' if cond else 'FAIL', name,
                        ('  -> %s' % detail) if detail else ''), flush=True)


def make_records(n):
    return [{
        'date': '2026-01-%02d' % (i % 28 + 1), 'time': '%02d:%02d' % (i % 24, i % 60),
        'm_call': 'BI8SQL', 'o_call': 'BG%05d' % (10000 + i),
        'freq': '144.0', 'freq_rx': '14.0', 'mode': 'LSB', 'prop_mode': 'E',
        'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '杭州', 'o_qth': '北京',
        'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
        'notes': '',
    } for i in range(n)]


from f_hamlog import project as pj   # noqa: E402

PAINTS = []


class PaintSpy(QObject):
    """记录每一次绘制时纵向滚动条的位置：首帧就应在底部。"""

    def __init__(self, table):
        super().__init__()
        self.table = table

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Paint:
            bar = self.table.verticalScrollBar()
            PAINTS.append((bar.value(), bar.maximum()))
        return False


win = QtWidgets.QMainWindow()
win.resize(1000, 500)
pj.main(win, filee=make_records(N), save_path=os.path.join(TMPDIR, 'a.fhl'))

table = win._perf_api['get_table']()
bar = table.verticalScrollBar()
# main() 末尾就 show() 了，但一次事件循环都还没跑 → 这一行读到的就是**首帧绘制前**的状态
ok('open: 滚动范围已确定', bar.maximum() > 0, '%s/%s' % (bar.value(), bar.maximum()))
ok('open: 首帧之前就已在最后一条', bar.value() == bar.maximum(),
   '%s/%s' % (bar.value(), bar.maximum()))

spy = PaintSpy(table)
table.viewport().installEventFilter(spy)
for _ in range(30):
    app.processEvents()
    time.sleep(0.003)
ok('open: 确有绘制发生（探针有效）', bool(PAINTS), str(len(PAINTS)))
ok('open: 每一帧都停在最后一条',
   all(v == mx for v, mx in PAINTS), str(PAINTS[:5]))

# 已显示窗口里的重建（新建日志 / 批量记录走同一条路）：也必须在底部，且不能差几像素
api = win._perf_api
bar.setValue(0)
for _ in range(3):
    app.processEvents()
api['table_update'](scroll_to_bottom=True)
for _ in range(12):
    app.processEvents()
bar2 = api['get_table']().verticalScrollBar()
ok('rebuild: 重建后停在最后一条', bar2.value() == bar2.maximum(),
   '%s/%s' % (bar2.value(), bar2.maximum()))

# 稳定之后不该再被「范围变化」牵着走（用户把窗口拖小不应突然跳到底部）
table3 = api['get_table']()
table3.verticalScrollBar().setValue(0)
for _ in range(3):
    app.processEvents()
win.resize(760, 500)
for _ in range(6):
    app.processEvents()
ok('settle: 缩小窗口后没有被拽回底部',
   table3.verticalScrollBar().value() == 0,
   '%s/%s' % (table3.verticalScrollBar().value(),
              table3.verticalScrollBar().maximum()))

# 短项目：不足一屏时不能崩、位置只能是 0
win2 = QtWidgets.QMainWindow()
win2.resize(1000, 500)
pj.main(win2, filee=make_records(3), save_path=os.path.join(TMPDIR, 'b.fhl'))
for _ in range(6):
    app.processEvents()
bar4 = win2._perf_api['get_table']().verticalScrollBar()
ok('short: 不足一屏时停在顶部且无异常', bar4.value() == 0 and bar4.maximum() == 0,
   '%s/%s' % (bar4.value(), bar4.maximum()))

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
sys.exit(0 if all(PASS) else 1)
