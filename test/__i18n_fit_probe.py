# -*- coding: utf-8 -*-
"""探针：中文下 set.py / 启动器 的窗口尺寸与最宽控件（确认布局未被改宽）。"""
import io
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import i18n          # noqa: E402
import theme         # noqa: E402
import satellite_pred as sp   # noqa: E402

TMP = tempfile.mkdtemp(prefix='fhl_fitprobe_')
for name, attr in (('m_xml.txt', 'SETTINGS_PATH'),
                   ('tle_sources.txt', 'TLE_SOURCES_PATH')):
    src = os.path.join(ROOT, 'file', name)
    dst = os.path.join(TMP, name)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
    else:
        io.open(dst, 'w', encoding='utf-8').write('{}')
    setattr(sp, attr, dst)

try:
    s = eval(io.open(os.path.join(TMP, 'm_xml.txt'), encoding='utf-8').read())
    if not isinstance(s, dict):
        s = {}
except Exception:
    s = {}
s['language'] = sys.argv[1] if len(sys.argv) > 1 else 'zh'
io.open(os.path.join(TMP, 'm_xml.txt'), 'w', encoding='utf-8').write(str(s))

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget   # noqa: E402
from PySide6.QtGui import QAction                                  # noqa: E402

QApplication.exec = lambda self=None, *a, **k: 0

OUT = []
app = QApplication([])
theme.init_app(app)
i18n.install(app)
print('语言 =', i18n.current_language())

import set as setmod   # noqa: E402
win = QMainWindow()
setmod.main(win)
app.processEvents()

print('窗口尺寸 = %dx%d' % (win.width(), win.height()))
cw = win.centralWidget()
items = [cw] + cw.findChildren(QWidget)
items.sort(key=lambda w: -w.sizeHint().width())
print('中央控件 sizeHint = %dx%d' % (cw.sizeHint().width(), cw.sizeHint().height()))
print('中央控件 minimumSizeHint 宽 = %d' % cw.minimumSizeHint().width())
lay = cw.layout()
if lay is not None:
    print('--- 顶层各行/控件的 minimumSizeHint 宽 ---')
    rows = []
    for i in range(lay.count()):
        it = lay.itemAt(i)
        w = it.widget()
        sub = it.layout()
        if w is not None:
            rows.append((w.minimumSizeHint().width(), type(w).__name__,
                         (w.text() if hasattr(w, 'text') else '')[:40]))
        elif sub is not None:
            rows.append((sub.minimumSize().width(), type(sub).__name__,
                         '<row %d 个控件>' % sub.count()))
    for width, name, txt in sorted(rows, reverse=True)[:6]:
        print('  min=%4d  %-14s %r' % (width, name, txt))
for w in items[:8]:
    print('  %-16s hint=%4d min=%4d 实宽=%4d  %r'
          % (type(w).__name__, w.sizeHint().width(),
             w.minimumSizeHint().width(), w.width(),
             (w.text() if hasattr(w, 'text') else w.windowTitle())[:48]))

for a in win.findChildren(QAction):
    pass

shutil.rmtree(TMP, ignore_errors=True)
os._exit(0)
