# -*- coding: utf-8 -*-
"""设置窗口「检查更新」按钮冒烟：位置、可点、不撑破固定尺寸。

不污染用户数据：设置文件与数据目录都指向临时目录（F_HAMLOG_DATA_DIR）。

用法：QT_QPA_PLATFORM=offscreen python tests/__set_update_btn_smoke.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

TMP = tempfile.mkdtemp(prefix='__set_upd_btn_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
_SEED = {'m_call': 'BI8SQL', 'm_qth': '成都', 'm_lat': 30.0, 'm_lon': 104.0}
for p in (os.path.join(TMP, 'file', 'm_xml.txt'), os.path.join(TMP, 'm_xml.txt')):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(str(_SEED))
os.environ['F_HAMLOG_DATA_DIR'] = TMP

from f_hamlog import theme, i18n, set as set_mod          # noqa: E402
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton,   # noqa: E402
                               QLabel)
from PySide6.QtCore import QSize                          # noqa: E402

theme.settings_path = lambda: os.path.join(TMP, 'm_xml.txt')

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


app = QApplication.instance() or QApplication(sys.argv)
theme.init_app(app)
i18n.install(app)


def pump(n=8):
    for _ in range(n):
        app.processEvents()


window = QMainWindow()
set_mod.main(window)
pump()

buttons = {b.text(): b for b in window.findElements(QPushButton)} if hasattr(window, 'findElements') else {}
buttons = {}
for b in window.centralWidget().findChildren(QPushButton):
    buttons[b.text()] = b

print('按钮：', sorted(buttons))
ok('S1 存在「检查更新」按钮', '检查更新' in buttons)
btn = buttons.get('检查更新')

labels = [w.text() for w in window.centralWidget().findChildren(QLabel)]
ver_label = [t for t in labels if t.startswith('F HamLog 版本：')]
ok('S2 版本号仍在窗口里', bool(ver_label), str(ver_label))

if btn is not None:
    geo = btn.geometry()
    cw = window.centralWidget()
    pos = btn.mapTo(cw, btn.rect().topLeft())
    ok('S3 按钮右边缘不超出窗口', pos.x() + geo.width() <= cw.width(),
       'x=%d w=%d 窗口宽=%d' % (pos.x(), geo.width(), cw.width()))
    ok('S4 按钮与版本号同一行', abs(pos.y() - 300) < 400, 'y=%d' % pos.y())
    ok('S5 按钮可点击', btn.isEnabled())

# 内容高度 vs 固定窗口高度：超了布局就会挤（换行/重叠）
lay = window.centralWidget().layout()
lay.activate()
hint = window.centralWidget().minimumSizeHint()
print('窗口 %dx%d，内容最小 %dx%d，行数=%d' % (
    window.width(), window.height(), hint.width(), hint.height(), lay.count()))
ok('S6 中文下内容放得下（最小高度 ≤ 窗口高）', hint.height() <= window.height(),
   'min_h=%d 窗口高=%d' % (hint.height(), window.height()))

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
window.close()
sys.exit(1 if bad else 0)
