"""抓图对比：批量记录冻结列在「中文 / 英文」两种语言下的渲染差异。

输出（均在 test/ 下，已被 .gitignore 覆盖）：
    __frozen_zh_out.png / __frozen_en_out.png        整窗
    __frozen_zh_crop_out.png / __frozen_en_crop_out.png   左侧冻结区放大 2 倍
    __frozen_diff_out.png                    两图差异高亮

用法：QT_QPA_PLATFORM=offscreen python test/__batch_frozen_i18n_grab.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.exit = lambda *a, **k: None

from PySide6.QtCore import QRect, Qt                        # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter          # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow     # noqa: E402

import i18n                                                 # noqa: E402
import batch_project                                        # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))


def grab(win, name):
    for _ in range(4):
        QApplication.processEvents()
    pm = win.grab()
    path = os.path.join(OUT, '__frozen_%s_out.png' % name)
    pm.save(path)
    return pm


def crop_scale(pm, w, h, scale=2):
    out = QImage(w * scale, h * scale, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawImage(QRect(0, 0, w * scale, h * scale), pm.toImage(), QRect(0, 0, w, h))
    p.end()
    return QImage(out)


def diff(a, b):
    ia, ib = a.toImage(), b.toImage()
    w = min(ia.width(), ib.width())
    h = min(ia.height(), ib.height())
    out = QImage(w, h, QImage.Format_ARGB32)
    out.fill(QColor(255, 255, 255))
    n = 0
    for y in range(h):
        for x in range(w):
            ca = ia.pixelColor(x, y)
            cb = ib.pixelColor(x, y)
            if ca != cb:
                out.setPixelColor(x, y, QColor(255, 0, 0))
                n += 1
            else:
                out.setPixelColor(x, y, ca)
    return out, n


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    i18n.install(app)

    win = QMainWindow()
    batch_project.main(win)
    tbl = win.findChild(batch_project.FrozenTableWidget)

    i18n.set_language('zh', app)
    pm_zh = grab(win, 'zh')

    i18n.set_language('en', app)
    pm_en = grab(win, 'en')

    print('中文窗口尺寸:', pm_zh.width(), pm_zh.height())
    print('英文窗口尺寸:', pm_en.width(), pm_en.height())
    print('中文 垂直表头宽/col0宽:', tbl.verticalHeader().width(), tbl.columnWidth(0))

    W, H = 360, 200
    crop_scale(pm_zh, W, H).save(os.path.join(OUT, '__frozen_zh_crop_out.png'))
    crop_scale(pm_en, W, H).save(os.path.join(OUT, '__frozen_en_crop_out.png'))
    d, n = diff(pm_zh, pm_en)
    d.save(os.path.join(OUT, '__frozen_diff_out.png'))
    print('差异像素数:', n)

    win.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
