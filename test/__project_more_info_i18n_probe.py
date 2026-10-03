"""探针：「更多信息」窗口（project.project_others）的字段标签是否随语言翻译。

路径：搜索 → 搜索结果窗口末列「更多」委托 → project_others(index)。
该窗口把字段中文名写在 QTableWidget 的**单元格**里（列 0），与「新建日志」同构，
`translate_widget()` 只翻表头不翻单元格 —— 本探针确认 `bind_cell_texts` 接入生效，
并验证语言来回切换能正确重译 / 还原。

用法：QT_QPA_PLATFORM=offscreen python test/__project_more_info_i18n_probe.py
"""

import io
import os
import re
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

sys.exit = lambda *a, **k: None
CJK = re.compile(r'[\u4e00-\u9fff]')

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog,     # noqa: E402
                               QFileDialog, QLineEdit, QMainWindow,
                               QMessageBox, QTableWidget, QWidget)

QMessageBox.exec = lambda self, *a, **k: QMessageBox.StandardButton.Ok
_noop = lambda *a, **k: QMessageBox.StandardButton.Ok
QMessageBox.information = _noop
QMessageBox.warning = _noop
QMessageBox.critical = _noop
QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.No
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ('', ''))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))

TMP = tempfile.mkdtemp(prefix='fhl_more_info_')
_BK = {}
for p in ('file/m_xml.txt',):
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

# 设置副本：语言 = 英文（不污染真实 file/m_xml.txt）
dst = os.path.join(TMP, 'm_xml.txt')
shutil.copyfile(os.path.join(ROOT, 'file', 'm_xml.txt'), dst)
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

# 搜索对话框：自动填关键词并接受（默认字段=o_call、匹配方式=包含、范围=全部）
QDialog.exec = lambda self, *a, **k: (
    [e.setText('JA1XYZ') for e in self.findChildren(QLineEdit)],
    QDialog.DialogCode.Accepted)[1]

win = QMainWindow()
pj.main(win, filee=[], save_path=os.path.join(TMP, 's.fhl'))
win.show()

# 塞一条记录，让搜索能命中
rec = {'date': '2026-01-01', 'time': '12:00', 'm_call': 'BG1ABC',
       'o_call': 'JA1XYZ', 'freq': '14.074', 'freq_rx': '14.074',
       'mode': 'FT8', 'prop_mode': 'SAT', 'sat_name': '',
       'm_rst': '59', 'o_rst': '59', 'm_qth': 'PM00', 'o_qth': 'PM95',
       'm_dig': 'IC-705', 'o_dig': 'FT-817', 'm_ant': 'GP', 'o_ant': 'DP',
       'm_pow': '5W', 'o_pow': '5W', 'notes': ''}
pj.file.append(rec)
for _ in range(3):
    app.processEvents()

# 打开搜索结果窗口
before = {id(w) for w in app.topLevelWidgets()}
try:
    win._perf_api['research_call'](pj.file)
except Exception as e:
    print('!! research_call 失败:', e)
    restore(); os._exit(1)
for _ in range(4):
    app.processEvents()

news = [w for w in app.topLevelWidgets()
        if id(w) not in before and w is not win and w.isVisible()]
if not news:
    print('!! 搜索结果窗口未出现')
    restore(); os._exit(1)
research = max(news, key=lambda w: len(w.findChildren(QWidget)))
print('[搜索结果窗口] %r' % research.windowTitle())

# 取末列「更多」委托并触发第 0 行
tbl = None
deleg = None
for t in research.findChildren(QTableWidget):
    print('  [委托一览]',
          [(c, type(t.itemDelegateForColumn(c)).__name__,
            getattr(t.itemDelegateForColumn(c), '_text', None))
           for c in range(t.columnCount())])
    for c in range(t.columnCount()):
        d = t.itemDelegateForColumn(c)
        # 末列是「定位到此条」(LocateButtonDelegate)，「更多」是倒数第二列
        if (d is not None and getattr(d, '_click_cb', None) is not None
                and getattr(d, '_text', '') == '更多'):
            tbl, deleg = t, d
            break
    if deleg is not None:
        break
if deleg is None:
    print('!! 未找到「更多」列委托')
    restore(); os._exit(1)

print('[表格] %dx%d  末列=%d  委托=%r'
      % (tbl.rowCount(), tbl.columnCount(), tbl.columnCount() - 1, type(deleg).__name__))

before2 = {id(w) for w in app.topLevelWidgets()}
try:
    deleg._click_cb(0)
except Exception:
    import traceback
    print('!! _click_cb 抛异常：')
    traceback.print_exc()
for _ in range(6):
    app.processEvents()

# 按标题定位「更多信息」窗口（比按 id 差集稳妥）
more = None
for w in app.topLevelWidgets():
    if w is win or w is research:
        continue
    if w.isVisible() and w.windowTitle() in ('More info', '更多信息'):
        more = w
        break
if more is None:
    print('!! 「更多信息」窗口未出现。当前顶层窗口：')
    for w in app.topLevelWidgets():
        if w.isVisible():
            print('    %-28r' % w.windowTitle())
    restore(); os._exit(1)
print('[更多信息窗口] %r  %dx%d' % (more.windowTitle(), more.width(), more.height()))
print()

bad = []
for t in more.findChildren(QTableWidget):
    m = t.model()
    print('--- QTableWidget %dx%d ---' % (t.rowCount(), t.columnCount()))
    for i in range(m.columnCount()):
        h = m.headerData(i, Qt.Orientation.Horizontal,
                         Qt.ItemDataRole.DisplayRole)
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
print('  英文界面下仍为中文 %d 处：%s' % (len(bad), bad if bad else '无'))

# 语言来回切换
print()
print('== 语言切换（窗口保持打开） ==')
_t = more.findChildren(QTableWidget)[0]


def _cells(table):
    return [table.item(r, 0).text() for r in range(table.rowCount())
            if table.item(r, 0)]


i18n.set_language('zh', app)
for _ in range(4):
    app.processEvents()
_zh = _cells(_t)
print('  切到中文: 中文 %d/%d  标题=%r'
      % (len([c for c in _zh if CJK.search(c)]), len(_zh), more.windowTitle()))

i18n.set_language('en', app)
for _ in range(4):
    app.processEvents()
_en = _cells(_t)
print('  切回英文: 残留中文 %d/%d  标题=%r'
      % (len([c for c in _en if CJK.search(c)]), len(_en), more.windowTitle()))

restore()
shutil.rmtree(TMP, ignore_errors=True)
os._exit(0)
