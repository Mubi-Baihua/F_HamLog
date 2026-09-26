# -*- coding: utf-8 -*-
"""验证：修复后，窗口是否在 show() 后立即完成首次绘制（即在"后续弹框/初始化"
阻塞之前就已经画出来），从而不再全程白屏。

模拟：勾选较多卫星 + 未设观测站（会弹引导框）+ 「阻塞式」假模态框。
用 QApplication 级事件过滤器捕获整进程第一次 Paint 的时刻。
"""
import os
import shutil
import sys
import time

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
os.chdir(D)
os.environ.pop('QT_QPA_PLATFORM', None)

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QObject, QEvent  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

import satellite_window as sw  # noqa: E402

SETTINGS = os.path.join(D, 'file', 'm_xml.txt')
bak = SETTINGS + '.verify_bak'
shutil.copyfile(SETTINGS, bak)

N_SEL = 200
BLOCK = 1.5
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

lines = open(os.path.join(D, 'file', 'amateur.tle'), encoding='utf-8-sig', errors='replace').read().splitlines()
names = [ln.strip() for ln in lines if ln.strip() and not ln.startswith('1 ') and not ln.startswith('2 ')][:N_SEL]

s = eval(open(SETTINGS, encoding='utf-8').read())
s['sat_sats'] = names
s['m_lat'] = 0.0
s['m_lon'] = 0.0
s['m_alt'] = 0.0
open(SETTINGS, 'w', encoding='utf-8').write(str(s))

T0 = []
PAINT_AT = []
BLOCK_AT = []


class Filter(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Paint and not PAINT_AT:
            PAINT_AT.append(time.perf_counter() - T0[0])
        return False


_FILTER = Filter()


def fake_block(*a, **k):
    # 模拟 QDialog.exec()：阻塞期间跑事件循环
    BLOCK_AT.append(time.perf_counter() - T0[0])
    end = time.perf_counter() + BLOCK
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.004)


# 让窗口一 show 就带上事件过滤器，以便捕获 main() 期间的首次 Paint
_orig_show = sw.QMainWindow.show


def _patched_show(self, *a, **k):
    self.installEventFilter(_FILTER)
    return _orig_show(self, *a, **k)


sw.QMainWindow.show = _patched_show

QMessageBox.information = staticmethod(fake_block)
QMessageBox.warning = staticmethod(fake_block)
sw.ObserverDialog.exec = lambda self: (fake_block() or QDialog.Rejected)
sw.SatelliteSelectDialog.exec = lambda self: (fake_block() or QDialog.Rejected)

T0.append(time.perf_counter())
sw.main(None)
t_ret = time.perf_counter() - T0[0]

# 跑到 TLE/预测告一段落，确认后续都能正常执行
win = sw._open_windows[-1]
for _ in range(300):
    app.processEvents()
    time.sleep(0.01)
    if getattr(win, '_tle_worker', None) is None and len(BLOCK_AT) >= 2:
        break
app.processEvents()

print('main() 返回 @ %.3fs' % t_ret)
print('首次 paint @ %s' % ('%.3fs' % PAINT_AT[0] if PAINT_AT else '未知'))
print('弹框(阻塞)开始 @ %s（共 %d 次）' % (
    ['%.3f' % x for x in BLOCK_AT], len(BLOCK_AT)))
if PAINT_AT and BLOCK_AT:
    print('→ %s' % ('窗口已在弹框前完成首次绘制（不再白屏）'
                    if PAINT_AT[0] < min(BLOCK_AT) else '窗口在弹框后才绘制（仍会白屏）'))
win.close()
sw.QMainWindow.show = _orig_show
shutil.copyfile(bak, SETTINGS)
os.remove(bak)
print('设置已还原')
