# -*- coding: utf-8 -*-
"""探针：打开项目时，首帧绘制那一刻主表格的纵向滚动位置是多少（判断有没有「先顶部后跳到底部」）。

用法：python tests/__open_jump_probe.py [N]
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

from PySide6 import QtWidgets
from PySide6.QtCore import QObject, QEvent
from f_hamlog.paths import app_path
from f_hamlog import backup

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.jp_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_jump_')
TMP_FHL = os.path.join(TMPDIR, 'perf.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

records = []
for i in range(N):
    records.append({
        'date': '2026-01-%02d' % (i % 28 + 1), 'time': '%02d:%02d' % (i % 24, i % 60),
        'm_call': 'BI8SQL', 'o_call': 'BG%05d' % (10000 + i),
        'freq': '144.0', 'freq_rx': '14.0', 'mode': 'LSB', 'prop_mode': 'E',
        'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '杭州', 'o_qth': '北京',
        'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
        'notes': '',
    })

from f_hamlog import project as pj

PAINTS = []


class Filter(QObject):
    def __init__(self, table):
        super().__init__()
        self.table = table

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Paint:
            PAINTS.append((round(time.perf_counter() - T0[0], 4),
                           self.table.verticalScrollBar().value(),
                           self.table.verticalScrollBar().maximum()))
        return False


T0 = [time.perf_counter()]
win = QtWidgets.QMainWindow()
win.resize(1000, 500)
pj.main(win, filee=records, save_path=TMP_FHL)   # 内部已 show()
api = win._perf_api
table = api['get_table']()
print('main() 返回：vscroll=%s/%s' % (table.verticalScrollBar().value(),
                                   table.verticalScrollBar().maximum()), flush=True)
_f = Filter(table)
table.viewport().installEventFilter(_f)
table.verticalScrollBar().installEventFilter(_f)

for _ in range(40):
    app.processEvents()
    time.sleep(0.005)

print('事件跑完后：vscroll=%s/%s' % (table.verticalScrollBar().value(),
                                  table.verticalScrollBar().maximum()), flush=True)
print('paint 次数 = %d' % len(PAINTS), flush=True)
for t, v, mx in PAINTS[:8]:
    print('  paint @%.4fs  vscroll=%s/%s' % (t, v, mx), flush=True)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
sys.stdout.flush()
sys.exit(0)
