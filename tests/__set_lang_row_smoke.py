"""冒烟：设置窗口中「颜色模式」「语言选择」「保存更改」是否落在同一行。

背景：语言下拉曾与「保存更改」并作一行；2026-10-03 起「颜色模式」也移入该行，
      按需求排在「语言」左侧。整行顺序为：
      「颜色模式:」+ 下拉 →「语言 Language:」+ 下拉 →（stretch）→「保存更改」。

不污染用户数据：设置文件指向临时文件，并在临时目录里 chdir。

用法：QT_QPA_PLATFORM=offscreen python test/__set_lang_row_smoke.py
"""

import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

sys.exit = lambda *a, **k: None

import backup                                      # noqa: E402
import theme                                        # noqa: E402

TMP = tempfile.mkdtemp(prefix='__set_lang_row_')
TMP_SETTINGS = os.path.join(TMP, 'm_xml.txt')
TMP_FILE_DIR = os.path.join(TMP, 'file')
os.makedirs(TMP_FILE_DIR, exist_ok=True)

_SEED = {'m_call': 'BI8SQL', 'm_qth': '成都', 'm_lat': 30.0, 'm_lon': 104.0}
with open(TMP_SETTINGS, 'w', encoding='utf-8') as f:
    f.write(str(_SEED))
with open(os.path.join(TMP_FILE_DIR, 'm_xml.txt'), 'w', encoding='utf-8') as f:
    f.write(str(_SEED))

theme.settings_path = lambda: TMP_SETTINGS
backup.BATCH_BACKUP = os.path.join(TMP, 'batch_backup.fhl')

from PySide6.QtWidgets import (QApplication, QComboBox, QLabel,       # noqa: E402
                               QMainWindow, QPushButton)

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))


app = QApplication.instance() or QApplication(sys.argv)


def pump(n=6):
    for _ in range(n):
        app.processEvents()


import i18n                                          # noqa: E402
i18n.install(app)

os.chdir(TMP)
import set as set_mod                                # noqa: E402

sw = QMainWindow()
set_mod.main(sw)
sw.show()
pump()

cw = sw.centralWidget()
combos = sw.findChildren(QComboBox)
lang_box = next((b for b in combos if b.findData('en') >= 0), None)
sett = next((b for b in sw.findChildren(QPushButton)
             if b.text() in ('保存更改', 'Save changes')), None)
lang_lbl = next((lb for lb in sw.findChildren(QLabel)
                 if lb.text() in ('语言 Language:', 'Language:')), None)

ok('找到语言下拉', lang_box is not None)
ok('找到「保存更改」按钮', sett is not None)
ok('找到「语言 Language:」标签', lang_lbl is not None)

# 「颜色模式」按需求排在「语言」左侧（同一行）
theme_lbl = next((lb for lb in sw.findChildren(QLabel)
                  if lb.text() in ('颜色模式:', 'Theme:')), None)
theme_box = next((b for b in combos if b.findData('dark') >= 0), None)
ok('找到「颜色模式:」标签', theme_lbl is not None)
ok('找到颜色模式下拉', theme_box is not None)

if lang_box is not None and sett is not None and cw is not None:
    # 0) 「颜色模式」在「语言」左侧，且两者与保存按钮落在同一行
    if theme_lbl is not None and theme_box is not None:
        seq = (theme_lbl, theme_box, lang_lbl, lang_box, sett)
        ys_c = [w.mapTo(cw, w.rect().center()).y() for w in seq]
        ok('颜色/语言/保存按钮在同一行', max(ys_c) - min(ys_c) <= 2,
           '行中心 y=%s' % sorted(set(ys_c)))
        xs_c = [w.mapTo(cw, w.rect().center()).x() for w in seq]
        ok('横向顺序为 颜色 < 语言 < 按钮', xs_c == sorted(xs_c), 'x=%s' % xs_c)

    # 1) 同一行：三者中心 y 相同（容差 2px）
    ys = [w.mapTo(cw, w.rect().center()).y() for w in (lang_lbl, lang_box, sett)]
    ok('语言选择与保存按钮在同一行', max(ys) - min(ys) <= 2,
       '行中心 y=%s' % sorted(set(ys)))

    # 2) 横向顺序：标签 < 下拉 < 按钮（按钮在右侧）
    xs = [w.mapTo(cw, w.rect().center()).x() for w in (lang_lbl, lang_box, sett)]
    ok('横向顺序为 标签 < 下拉 < 按钮', xs[0] < xs[1] < xs[2], 'x=%s' % xs)

    # 3) 均未超出窗口右边界、未被压缩
    over = [w.__class__.__name__ for w in (lang_lbl, lang_box, sett)
            if (w.mapTo(cw, w.rect().topLeft()).x() + w.width()) > cw.width()]
    ok('同行控件未超出窗口宽度', not over, ' | '.join(over))
    squeezed = ['%s %d<%d' % (w.__class__.__name__, w.width(), w.sizeHint().width())
                for w in (lang_box, sett) if w.width() < w.sizeHint().width()]
    ok('同行控件未被压缩', not squeezed, ' | '.join(squeezed))

    # 4) 中文下窗口为历史基准尺寸
    ok('中文窗口尺寸=770x475', (sw.width(), sw.height()) == (770, 475),
       '%dx%d' % (sw.width(), sw.height()))

    # 5) 切英文：窗口按需放宽，且按钮仍在同行、未越界
    en_idx = lang_box.findData('en')
    lang_box.setCurrentIndex(en_idx)     # 走真实 on_language_changed（立即生效 + 落盘）
    pump()
    ok('切英文后语言=English', i18n.current_language() == 'en',
       i18n.current_language())
    ys2 = [w.mapTo(cw, w.rect().center()).y() for w in (lang_lbl, lang_box, sett)]
    ok('英文下仍在同一行', max(ys2) - min(ys2) <= 2,
       '行中心 y=%s' % sorted(set(ys2)))
    over2 = [w.__class__.__name__ for w in (lang_lbl, lang_box, sett)
             if (w.mapTo(cw, w.rect().topLeft()).x() + w.width()) > cw.width()]
    ok('英文下未超出窗口宽度', not over2, ' | '.join(over2))
    need = cw.layout().sizeHint().height()
    ok('英文下高度仍有余量', need <= cw.height(),
       '内容需要 %d，可视 %d' % (need, cw.height()))
    print('[英文窗口] %dx%d  按钮=%r  标签=%r'
          % (sw.width(), sw.height(), sett.text(), lang_lbl.text()))

    # 还原中文（避免影响后续/落盘残留）
    lang_box.setCurrentIndex(lang_box.findData('zh'))
    pump()

print()
lines = []
n_fail = 0
for status, name, extra in results:
    if status == 'FAIL':
        n_fail += 1
    lines.append('[%s] %s%s' % (status, name, ('  <- ' + extra) if extra else ''))
lines.append('')
lines.append('合计：%d 项，失败 %d 项' % (len(results), n_fail))
text = '\n'.join(lines)
print(text)
sys.exit(1 if n_fail else 0)
