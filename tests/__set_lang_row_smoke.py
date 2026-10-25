# -*- coding: utf-8 -*-
"""冒烟：设置窗口里「颜色模式」与「语言」是否落在同一行、顺序与尺寸是否仍然正常。

背景：语言下拉曾与「保存更改」并作一行；2026-10-03 起「颜色模式」也移入该行。
2026-10-25 起整页改成**自动保存**，「保存更改」按钮已删除，该行只剩：
「颜色模式:」+ 下拉 →「语言 Language:」+ 下拉 →（stretch）。

不污染用户数据：数据目录指向临时目录（F_HAMLOG_DATA_DIR）。

用法：QT_QPA_PLATFORM=offscreen python tests/__set_lang_row_smoke.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from f_hamlog import theme, i18n                     # noqa: E402

TMP = tempfile.mkdtemp(prefix='__set_lang_row_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
XML = os.path.join(TMP, 'file', 'm_xml.txt')
_SEED = {'m_call': 'BI8SQL', 'm_qth': '成都', 'm_lat': 30.0, 'm_lon': 104.0}
with open(XML, 'w', encoding='utf-8') as f:
    f.write(str(_SEED))
os.environ['F_HAMLOG_DATA_DIR'] = TMP
theme.settings_path = lambda: XML

from PySide6.QtWidgets import (QApplication, QComboBox, QLabel,       # noqa: E402
                               QMainWindow, QPushButton)

from f_hamlog import set as set_mod                              # noqa: E402

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


app = QApplication.instance() or QApplication(sys.argv)
theme.init_app(app)
i18n.install(app)


def pump(n=6):
    for _ in range(n):
        app.processEvents()


sw = QMainWindow()
set_mod.main(sw)
sw.show()
pump()

cw = sw.centralWidget()
combos = sw.findChildren(QComboBox)
lang_box = next((b for b in combos if b.findData('en') >= 0), None)
lang_lbl = next((lb for lb in sw.findChildren(QLabel)
                 if lb.text() in ('语言 Language:', 'Language:')), None)
theme_lbl = next((lb for lb in sw.findChildren(QLabel)
                  if lb.text() in ('颜色模式:', 'Theme:')), None)
theme_box = next((b for b in combos if b.findData('dark') >= 0), None)
sett = next((b for b in sw.findChildren(QPushButton)
             if b.text() in ('保存更改', 'Save changes')), None)

ok('找到语言下拉', lang_box is not None)
ok('找到「语言 Language:」标签', lang_lbl is not None)
ok('找到「颜色模式:」标签', theme_lbl is not None)
ok('找到颜色模式下拉', theme_box is not None)
ok('「保存更改」按钮已删除（整页自动保存）', sett is None, repr(sett))

if None not in (lang_box, lang_lbl, theme_lbl, theme_box):
    seq = (theme_lbl, theme_box, lang_lbl, lang_box)
    ys_c = [w.mapTo(cw, w.rect().center()).y() for w in seq]
    ok('颜色与语言在同一行', max(ys_c) - min(ys_c) <= 2, '行中心 y=%s' % sorted(set(ys_c)))
    xs_c = [w.mapTo(cw, w.rect().center()).x() for w in seq]
    ok('横向顺序为 颜色标签 < 下拉 < 语言标签 < 下拉', xs_c == sorted(xs_c), 'x=%s' % xs_c)

    over = [w.__class__.__name__ for w in seq
            if (w.mapTo(cw, w.rect().topLeft()).x() + w.width()) > cw.width()]
    ok('同行控件未超出窗口宽度', not over, ' | '.join(over))
    squeezed = ['%s %d<%d' % (w.__class__.__name__, w.width(), w.sizeHint().width())
                for w in (theme_box, lang_box) if w.width() < w.sizeHint().width()]
    ok('下拉未被压缩', not squeezed, ' | '.join(squeezed))

    ok('中文窗口尺寸=770x475', (sw.width(), sw.height()) == (770, 475),
       '%dx%d' % (sw.width(), sw.height()))

    # 切英文：窗口按需放宽，同行控件仍未越界
    lang_box.setCurrentIndex(lang_box.findData('en'))     # 走真实的 on_language_changed
    pump()
    ok('切英文后语言=English', i18n.current_language() == 'en', i18n.current_language())
    ys2 = [w.mapTo(cw, w.rect().center()).y() for w in seq]
    ok('英文下仍在同一行', max(ys2) - min(ys2) <= 2, '行中心 y=%s' % sorted(set(ys2)))
    over2 = [w.__class__.__name__ for w in seq
             if (w.mapTo(cw, w.rect().topLeft()).x() + w.width()) > cw.width()]
    ok('英文下未超出窗口宽度', not over2, ' | '.join(over2))
    ok('英文下高度仍有余量', cw.layout().sizeHint().height() <= cw.height(),
       '内容需要 %d，可视 %d' % (cw.layout().sizeHint().height(), cw.height()))
    print('[英文窗口] %dx%d 标签=%r' % (sw.width(), sw.height(), lang_lbl.text()))

    lang_box.setCurrentIndex(lang_box.findData('zh'))     # 还原中文
    pump()

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sw.close()
sys.exit(1 if bad else 0)
