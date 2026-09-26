"""深色模式冒烟：验证系统深浅色**运行中切换**时，批量记录窗口的取色即时刷新。

覆盖两条刷新通路：
  1. theme.watch_theme(窗口, …) —— 时钟/快捷键提示等次要文字色；
  2. FrozenTableWidget.changeEvent —— 冻结列底色（注意不能读冻结层自身调色板，
     QSS 的 background-color 会反写进去，导致锁死在首次颜色）。

不触碰 file/batch_backup.fhl（backup.BATCH_BACKUP 指向临时文件）。
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import backup  # noqa: E402
backup.BATCH_BACKUP = os.path.join(tempfile.gettempdir(), '__wb_batch_backup.fhl')

from PySide6.QtWidgets import QApplication, QMainWindow, QLabel  # noqa: E402
from PySide6.QtGui import QPalette, QColor  # noqa: E402

import batch_project  # noqa: E402

app = QApplication(sys.argv)

DARK = {
    QPalette.Window: '#202020', QPalette.WindowText: '#ffffff',
    QPalette.Base: '#2b2b2b', QPalette.Text: '#ffffff',
    QPalette.Button: '#2b2b2b', QPalette.ButtonText: '#ffffff',
    QPalette.Highlight: '#2f6fed', QPalette.HighlightedText: '#ffffff',
}
LIGHT = {
    QPalette.Window: '#f0f0f0', QPalette.WindowText: '#000000',
    QPalette.Base: '#ffffff', QPalette.Text: '#000000',
    QPalette.Button: '#f0f0f0', QPalette.ButtonText: '#000000',
    QPalette.Highlight: '#2f6fed', QPalette.HighlightedText: '#ffffff',
}


def apply(spec):
    p = QPalette()
    for role, val in spec.items():
        p.setColor(role, QColor(val))
    app.setPalette(p)
    for _ in range(3):
        app.processEvents()


apply(DARK)
win = QMainWindow()
batch_project.main(win)
win.show()
for _ in range(5):
    app.processEvents()

out = []


def snap(tag):
    table = win.findChildren(batch_project.FrozenTableWidget)[0]
    clock = [lb for lb in win.findChildren(QLabel) if 'UTC' in lb.text()][0]
    hint = [lb for lb in win.findChildren(QLabel) if '快捷键' in lb.text()][0]
    frozen_qss = table._frozen.styleSheet()
    bg = frozen_qss.split('background-color:')[-1].rstrip('; }')
    out.append('%s | frozen bg=%s | clock=%s | hint=%s'
               % (tag, bg,
                  clock.styleSheet().split('color:')[-1].split(';')[0],
                  hint.styleSheet().split('color:')[-1].split(';')[0]))


snap('initial dark ')
apply(LIGHT)
snap('switch light ')
apply(DARK)
snap('switch dark  ')

with open(os.path.join(HERE, '__dark_theme_switch_out.txt'), 'w',
          encoding='utf-8') as f:
    f.write('\n'.join(out) + '\n')
print('\n'.join(out))
