# -*- coding: utf-8 -*-
"""探针：量出当前 toast 在各种文案下的宽度/高度，以及"文字实际需要的单行宽度"。

用来判断现在的宽度是"够用"还是"被截断/换行压扁"。
用法：python test/__toast_width_probe.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtGui import QFontMetrics

from f_hamlog import toast_tip
from f_hamlog import theme

app = QApplication(sys.argv)
theme.init_app(app)
win = QMainWindow()
win.setGeometry(100, 100, 800, 600)
win.show()
for _ in range(5):
    app.processEvents()

TEXTS = [
    '已保存成功！',
    '已删除 1 条日志。',
    '已粘贴 5 条日志。',
    '已复制 3 条日志到剪贴板。',
    '已删除 12 条日志。',
    '剪贴板内容无法识别为日志数据。',
    '没有可删除的日志：请先在“选择”列勾选要删除的行，或直接选中（高亮）这些行。',
    '当前未加载日志表。',
    '已保存到服务端，多人日志已关闭。',
]

fm = QFontMetrics(win.font())
print('%-4s %-8s %-8s %-7s %-7s %-7s %-9s %s' % (
    'no', '所需单行', 'label.w', 'toast.w', 'toast.h', 'label.h', '换行?', '文案'))
for i, txt in enumerate(TEXTS, 1):
    t = toast_tip.show_toast(txt, win)
    for _ in range(3):
        app.processEvents()
    need = fm.horizontalAdvance(txt)          # 单行完整显示所需宽度
    lw, lh = t._label.width(), t._label.height()
    wrapped = lh > fm.height() + 4
    print('%-4d %-8d %-8d %-7d %-7d %-7d %-9s %s' % (
        i, need, lw, t.width(), t.height(), lh,
        '是' if wrapped else '否', txt[:28]))
    t.close()
    for _ in range(2):
        app.processEvents()

print()
print('（所需单行 = 不含内边距的纯文字宽度；toast.w 含左右各 12px 内边距 + 22 余量）')

# ---- 额外产物：把几种文案的 toast 拼成一张图，肉眼确认文字没被截断 ----
from PySide6.QtGui import QImage, QPainter, QColor
imgs = []
for txt in TEXTS:
    t = toast_tip.show_toast(txt, win)
    for _ in range(3):
        app.processEvents()
    imgs.append((txt, t.grab().toImage()))
    t.close()
    for _ in range(2):
        app.processEvents()

pad = 10
cw = max(im.width() for _, im in imgs) + pad * 2
ch = sum(im.height() + pad for _, im in imgs) + pad
canvas = QImage(cw, ch, QImage.Format_ARGB32)
canvas.fill(QColor(245, 245, 245))
pnt = QPainter(canvas)
y = pad
for _, im in imgs:
    pnt.drawImage(pad, y, im)
    y += im.height() + pad
pnt.end()
out = os.path.join(HERE, '__toast_width_out.png')
canvas.save(out)
print('拼图已保存:', out, canvas.width(), 'x', canvas.height())

sys.stdout.flush()
os._exit(0)
