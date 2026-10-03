"""批量记录窗口：冻结列在切换语言前后的几何探针。

背景
----
`FrozenTableWidget` 的冻结层是一个**共享主表 model** 的独立 `QTableView`，
几何由 `updateFrozenGeometry()` 计算：

    x = verticalHeader().width()
    w = columnWidth(0)
    h = horizontalHeader().height() + viewport().height()

切语言时竖向表头（行标签=字段中文名）会被翻译成英文 → 行标签变长 →
垂直表头宽度变化，而冻结层只在 resize/show/列宽变化时才重算几何。
本探针就是量这个差值。

用法：QT_QPA_PLATFORM=offscreen python test/__batch_frozen_i18n_probe.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# 槽里的 sys.exit() 会从 PySide6 的 C++ 边界直接终止进程，测试前先兜住
sys.exit = lambda *a, **k: None

from PySide6.QtCore import Qt                       # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

import i18n                                          # noqa: E402
import batch_project                                 # noqa: E402


def snap(tbl, tag, lang):
    f = tbl._frozen
    m = tbl.model()
    geo = f.geometry()
    vhw = tbl.verticalHeader().width()
    print('-- [%s] 语言=%s --' % (tag, lang))
    print('   冻结层 geometry      : %s' % (geo.getRect(),))
    print('   冻结层 min/max 宽    : %d / %d' % (f.minimumWidth(), f.maximumWidth()))
    print('   主表 col0 宽         : %d' % tbl.columnWidth(0))
    print('   垂直表头宽           : %d   <- 冻结层 x 应对齐到这里' % vhw)
    print('   水平表头高           : %d' % tbl.horizontalHeader().height())
    print('   主表 viewport 几何   : %s' % (tbl.viewport().geometry().getRect(),))
    print('   水平表头[0]          : %r' % (m.headerData(
        0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole),))
    print('   垂直表头[0]          : %r' % (m.headerData(
        0, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole),))
    print('   冻结层 header[0]     : %r' % (m.headerData(
        0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole),))
    # 关键判据：冻结层左边是否正好压住主表 col0 的起点
    dx = geo.x() - vhw
    print('   ✦ 错位 dx = %d px %s' % (dx, '(对齐)' if dx == 0 else '★ 不对齐 ★'))
    return dx


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    i18n.install(app)

    win = QMainWindow()
    batch_project.main(win)
    for _ in range(3):
        app.processEvents()

    tbl = win.findChild(batch_project.FrozenTableWidget)
    if tbl is None:
        print('!! 找不到 FrozenTableWidget')
        return 2

    i18n.set_language('zh', app)
    for _ in range(3):
        app.processEvents()
    dx_zh = snap(tbl, '中文', 'zh')

    i18n.set_language('en', app)
    for _ in range(3):
        app.processEvents()
    dx_en = snap(tbl, '切换后', 'en')

    print()
    print('== 结论 ==')
    print('  中文下错位 : %d px' % dx_zh)
    print('  英文下错位 : %d px' % dx_en)
    if dx_en != 0:
        print('  ★ 复现：切语言后冻结层未重新定位（差 %d px）' % dx_en)
    else:
        print('  未复现几何错位')

    win.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
