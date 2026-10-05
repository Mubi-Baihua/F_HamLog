"""探针：英文模式下「新建日志」窗口的字段标签是否仍为中文。

背景：`project.new()` 把字段中文名放在 QTableWidget 的**单元格文字**里
（`QTableWidgetItem(translation_dict[i])`），而 `i18n.translate_widget()` 对
QTableView 只翻 model 的**表头**，不翻单元格 → 英文界面下这一列可能仍是中文。

用法：QT_QPA_PLATFORM=offscreen python test/__project_new_window_i18n_probe.py
"""

import io
import os
import re
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from f_hamlog.paths import app_path  # noqa: E402
os.chdir(ROOT)

sys.exit = lambda *a, **k: None
CJK = re.compile(r'[\u4e00-\u9fff]')

from PySide6.QtCore import Qt                                     # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,  # noqa: E402
                               QMainWindow, QMessageBox, QTableWidget,
                               QWidget)

QDialog.exec = lambda self, *a, **k: QDialog.DialogCode.Rejected
QMessageBox.exec = lambda self, *a, **k: QMessageBox.StandardButton.Ok
_noop = lambda *a, **k: QMessageBox.StandardButton.Ok
QMessageBox.information = _noop
QMessageBox.warning = _noop
QMessageBox.critical = _noop
QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.No
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ('', ''))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))

TMP = tempfile.mkdtemp(prefix='fhl_new_win_')
_BK = {}
for p in (app_path('file/m_xml.txt'),):
    if os.path.exists(p):
        with io.open(p, 'rb') as f:
            _BK[p] = f.read()


def restore():
    for p, b in _BK.items():
        with io.open(p, 'wb') as f:
            f.write(b)


import backup                        # noqa: E402
backup.is_backup_nonempty = lambda *a, **k: False
import satellite_auto_update         # noqa: E402
satellite_auto_update.AutoTleUpdater.start = lambda self: None
import satellite_pred as sp          # noqa: E402
sp.migrate_legacy_sat_data = lambda *a, **k: None

# 设置副本：把语言改成英文（不污染真实 file/m_xml.txt）
dst = os.path.join(TMP, 'm_xml.txt')
shutil.copyfile(app_path('file/m_xml.txt')), dst)
_s = eval(io.open(dst, encoding='utf-8').read())
_s['language'] = 'en'
io.open(dst, 'w', encoding='utf-8').write(str(_s))
sp.SETTINGS_PATH = dst
import theme                          # noqa: E402
theme.settings_path = lambda *a, **k: dst

import i18n                           # noqa: E402
import project as pj                  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
i18n.install(app)
print('[语言]', i18n.current_language())

win = QMainWindow()
pj.main(win, filee=[], save_path=os.path.join(TMP, 's.fhl'))
win.show()
for _ in range(3):
    app.processEvents()

before = {id(w) for w in app.topLevelWidgets()}
win._new_qso()
for _ in range(4):
    app.processEvents()

news = [w for w in app.topLevelWidgets()
        if id(w) not in before and w is not win and w.isVisible()]
if not news:
    print('!! 未出现新的顶层窗口（新建日志没能打开）')
    restore()
    sys.exit(1)

dlg = max(news, key=lambda w: len(w.findChildren(QWidget)))
print('[窗口] %r  %dx%d' % (dlg.windowTitle(), dlg.width(), dlg.height()))
print()

bad = []
for t in dlg.findChildren(QTableWidget):
    m = t.model()
    print('--- QTableWidget %dx%d ---' % (t.rowCount(), t.columnCount()))
    for i in range(m.columnCount()):
        h = m.headerData(i, Qt.Orientation.Horizontal,
                         Qt.ItemDataRole.DisplayRole)   # 横向表头 / 显示角色
        print('    表头[%d] = %r' % (i, h))
        if h and CJK.search(str(h)):
            bad.append('表头: %r' % h)
    for r in range(t.rowCount()):
        it = t.item(r, 0)
        txt = it.text() if it else ''
        mark = '  ★仍为中文' if txt and CJK.search(txt) else ''
        print('    单元格[%d,0] = %r%s' % (r, txt, mark))
        if txt and CJK.search(txt):
            bad.append('单元格: %r' % txt)

print()
print('== 结论 ==')
if bad:
    print('  英文界面下仍为中文的字段标签 %d 处：' % len(bad))
    for s in bad:
        print('    ' + s)
else:
    print('  无中文残留')

# --- 语言来回切换：窗口保持打开，应即时重译且可还原（不重建窗口） ---
print()
print('== 语言切换（窗口保持打开） ==')
_tbl = dlg.findChildren(QTableWidget)[0]


def _cells(table):
    return [table.item(r, 0).text() for r in range(table.rowCount())
            if table.item(r, 0)]


i18n.set_language('zh', app)
for _ in range(4):
    app.processEvents()
_zh = _cells(_tbl)
_cjk = [c for c in _zh if CJK.search(c)]
print('  切到中文: 中文标签 %d/%d  标题=%r  例: %s'
      % (len(_cjk), len(_zh), dlg.windowTitle(), _zh[:3]))

i18n.set_language('en', app)
for _ in range(4):
    app.processEvents()
_en = _cells(_tbl)
_cjk2 = [c for c in _en if CJK.search(c)]
print('  切回英文: 残留中文 %d/%d  标题=%r  例: %s'
      % (len(_cjk2), len(_en), dlg.windowTitle(), _en[:3]))
print('  还原一致: %s' % ('是' if _en == [t for t in
      ['Date', 'Time', 'My call', 'Other call', 'Freq', 'RX freq', 'Prop',
       'Satellite', 'Mode', 'My RST', 'Other RST', 'My QTH', 'Other QTH',
       'My rig', 'Other rig', 'My ant', 'Other ant', 'My pwr', 'Other pwr',
       'Note']] else '否'))

# 顺带看看 更多信息 窗口
print()
print('[顺带] 检查「更多信息」窗口…')
before2 = {id(w) for w in app.topLevelWidgets()}
try:
    win._more_info(0) if hasattr(win, '_more_info') else None
except Exception as e:
    print('   （无 _more_info 入口：%s）' % e)
for _ in range(3):
    app.processEvents()
news2 = [w for w in app.topLevelWidgets()
         if id(w) not in before2 and w.isVisible()]
for w in news2:
    for t in w.findChildren(QTableWidget):
        cells = [t.item(r, 0).text() for r in range(t.rowCount())
                 if t.item(r, 0)]
        cjk = [c for c in cells if CJK.search(c)]
        print('  %r 单元格中文 %d/%d 例：%s'
              % (w.windowTitle(), len(cjk), len(cells), cjk[:3]))

restore()
shutil.rmtree(TMP, ignore_errors=True)
os._exit(0)
