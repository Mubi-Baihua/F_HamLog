"""深色模式端到端冒烟：预填打开批量记录 → Ctrl+N 新增日志列 → 配色/几何自检。

用法：python __dark_batch_final_smoke.py [dark|light]
不触碰 file/batch_backup.fhl（backup.BATCH_BACKUP 指向临时文件）。
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

MODE = sys.argv[1] if len(sys.argv) > 1 else 'dark'

import backup  # noqa: E402
backup.BATCH_BACKUP = os.path.join(tempfile.gettempdir(), '__wb_batch_backup.fhl')

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette, QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel  # noqa: E402

import batch_project  # noqa: E402

app = QApplication(sys.argv)

p = QPalette()
if MODE == 'dark':
    spec = {QPalette.Window: '#202020', QPalette.WindowText: '#ffffff',
            QPalette.Base: '#2b2b2b', QPalette.Text: '#ffffff',
            QPalette.Button: '#2b2b2b', QPalette.ButtonText: '#ffffff',
            QPalette.Highlight: '#2f6fed', QPalette.HighlightedText: '#ffffff'}
else:
    spec = {QPalette.Window: '#f0f0f0', QPalette.WindowText: '#000000',
            QPalette.Base: '#ffffff', QPalette.Text: '#000000',
            QPalette.Button: '#f0f0f0', QPalette.ButtonText: '#000000',
            QPalette.Highlight: '#2f6fed', QPalette.HighlightedText: '#ffffff'}
for role, val in spec.items():
    p.setColor(role, QColor(val))
app.setPalette(p)

preset = {'freq': '145.900', 'freq_rx': '437.800', 'mode': 'FM',
          'prop_mode': 'SAT', 'sat_name': 'AO-91'}

win = QMainWindow()
batch_project.main(win, preset=preset)
win.show()
for _ in range(5):
    app.processEvents()

table = win.findChildren(batch_project.FrozenTableWidget)[0]
result = ['mode=%s' % MODE, 'columns before Ctrl+N = %d' % table.columnCount()]

# Ctrl+N：新增一条日志列（走 _NavFilter 的快捷键通路）
QTest.keyClick(table, Qt.Key_N, Qt.ControlModifier)
for _ in range(5):
    app.processEvents()

result.append('columns after  Ctrl+N = %d' % table.columnCount())
result.append('headers=%s'
              % [table.horizontalHeaderItem(c).text()
                 for c in range(table.columnCount())])


def contrast(fg, bg):
    def lum(c):
        def ch(v):
            v = v / 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())
    l1, l2 = sorted([lum(fg), lum(bg)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


fr = table._frozen
frozen_bg = QColor(fr.styleSheet().split('background-color:')[-1].rstrip('; }'))
item_fg = table.item(0, 0).foreground().color() if table.item(0, 0).foreground().style().name != 'NoBrush' else None
frozen_text = item_fg or fr.palette().color(QPalette.Text)
result.append('frozen bg=%s text=%s contrast=%.2f:1'
              % (frozen_bg.name(), frozen_text.name(),
                 contrast(frozen_text, frozen_bg)))
main_bg = table.viewport().palette().color(QPalette.Base)
main_text = table.palette().color(QPalette.Text)
result.append('main column bg=%s text=%s contrast=%.2f:1'
              % (main_bg.name(), main_text.name(), contrast(main_text, main_bg)))

clock = [lb for lb in win.findChildren(QLabel) if 'UTC' in lb.text()][0]
c_fg = QColor(clock.styleSheet().split('color:')[-1].split(';')[0])
result.append('clock fg=%s bg=%s contrast=%.2f:1'
              % (c_fg.name(), app.palette().color(QPalette.Window).name(),
                 contrast(c_fg, app.palette().color(QPalette.Window))))

png = os.path.join(HERE, '__dark_final_%s_out.png' % MODE)
win.grab().save(png)
result.append('saved %s' % png)
if not fr.isVisible():
    result.append('WARNING: frozen layer not visible')
result.append('frozen width=%d (col0=%d)'
              % (fr.width(), table.columnWidth(0)))

with open(os.path.join(HERE, '__dark_final_%s_out.txt' % MODE), 'w',
          encoding='utf-8') as f:
    f.write('\n'.join(result) + '\n')
print('\n'.join(result))
