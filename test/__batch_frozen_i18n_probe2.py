"""批量记录冻结列错位复现：窗口足够宽（切语言不触发 resize）时是否错位。

假设：竖向表头（行标签=字段中文名）翻译后变长，垂直表头宽度变化，
而冻结层 x 只在 `resizeEvent` / 列宽变化时重算 —— 窗口不 resize 时 x 保持旧值。

用法：QT_QPA_PLATFORM=offscreen python test/__batch_frozen_i18n_probe2.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.exit = lambda *a, **k: None

from PySide6.QtCore import Qt                            # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

import i18n                                              # noqa: E402
import batch_project                                     # noqa: E402


def measure(tbl, tag):
    f = tbl._frozen
    geo = f.geometry()
    vhw = tbl.verticalHeader().width()
    print('  [%-8s] frozen.x=%-4d  垂直表头宽=%-4d  col0宽=%-4d  dx=%+d %s'
          % (tag, geo.x(), vhw, tbl.columnWidth(0), geo.x() - vhw,
             '' if geo.x() == vhw else '★ 错位'))
    return geo.x() - vhw


def run(app, width, height, label):
    print('=== 窗口 %dx%d：%s ===' % (width, height, label))
    win = QMainWindow()
    batch_project.main(win)
    tbl = win.findChild(batch_project.FrozenTableWidget)
    win.resize(width, height)
    win.show()
    for _ in range(6):
        app.processEvents()

    i18n.set_language('zh', app)
    for _ in range(6):
        app.processEvents()
    d1 = measure(tbl, 'zh')

    i18n.set_language('en', app)
    for _ in range(6):
        app.processEvents()
    d2 = measure(tbl, 'en')

    print('  窗口最终尺寸:', win.width(), 'x', win.height())
    print('  → 英文下 dx = %+d %s' % (d2, '（错位！）' if d2 else '（对齐）'))
    win.close()
    for _ in range(3):
        app.processEvents()
    return d1, d2


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    i18n.install(app)
    # 情况 A：窄窗口（切语言会因最小尺寸变大而 resize）
    run(app, 1200, 790, '窄窗口，切语言会触发 resize')
    # 情况 B：宽窗口（切语言不会 resize）
    run(app, 1900, 900, '宽窗口，切语言不触发 resize')
    return 0


if __name__ == '__main__':
    sys.exit(main())
