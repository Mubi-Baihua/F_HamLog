# -*- coding: utf-8 -*-
"""探针：英文模式下，与「自定义日志字段」相关的界面还有哪些中文残留。

覆盖：主表列头 / 文件菜单 / 「新建日志」「更多信息」/「项目属性」/「自定义日志字段」窗口。
用法：QT_QPA_PLATFORM=offscreen python tests/__custom_fields_i18n_probe.py
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
os.chdir(ROOT)

from f_hamlog.paths import app_path  # noqa: E402
CJK = re.compile(r'[\u4e00-\u9fff]')

from PySide6.QtCore import Qt                                      # noqa: E402
from PySide6.QtGui import QAction                            # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog,      # noqa: E402
                               QFileDialog, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QTableWidget,
                               QWidget, QLabel)

QDialog.exec = lambda self, *a, **k: QDialog.DialogCode.Rejected
QMessageBox.exec = lambda self, *a, **k: QMessageBox.StandardButton.Ok
_msgs = []
def _info(parent, title, text, *a, **k):
    _msgs.append((title, text))
    return QMessageBox.StandardButton.Ok
QMessageBox.information = _info
QMessageBox.warning = _info
QMessageBox.critical = _info
QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.No
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ('', ''))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))

TMP = tempfile.mkdtemp(prefix='fhl_cf_i18n_')
SETT = app_path('file/m_xml.txt')
with io.open(SETT, 'rb') as f:
    _BAK = f.read()

dst = os.path.join(TMP, 'm_xml.txt')
shutil.copyfile(SETT, dst)
_s = eval(io.open(dst, encoding='utf-8').read())
_s['language'] = 'en'
io.open(dst, 'w', encoding='utf-8').write(str(_s))

from f_hamlog import backup                     # noqa: E402
backup.is_backup_nonempty = lambda *a, **k: False
backup.PROJECT_BACKUP = os.path.join(TMP, 'project_backup.fhl')
from f_hamlog import satellite_auto_update      # noqa: E402
satellite_auto_update.AutoTleUpdater.start = lambda self: None
from f_hamlog import satellite_pred as sp       # noqa: E402
sp.migrate_legacy_sat_data = lambda *a, **k: None
sp.SETTINGS_PATH = dst
from f_hamlog import theme                      # noqa: E402
theme.settings_path = lambda *a, **k: dst
from f_hamlog import i18n                       # noqa: E402
from f_hamlog import project as pj               # noqa: E402

# 让 project 读这份英文设置
_orig_load = pj.load_settings
pj.load_settings = lambda: eval(io.open(dst, encoding='utf-8').read())

app = QApplication.instance() or QApplication(sys.argv)
i18n.install(app)
print('[语言]', i18n.current_language())

records = [{
    'date': '2026-10-01', 'time': '12:00', 'm_call': 'BI8SQL', 'o_call': 'BG5ABC',
    'freq': '145.0', 'freq_rx': '145.0', 'mode': 'FM', 'prop_mode': 'E',
    'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
    'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
    'notes': '', 'wx': '晴', 'rig2': 'FT-818',
}]
meta = {
    'other_item': {'wx': '天气', 'rig2': '备用设备'},
    'field_meta': {'wx': {'main': True, 'required': False},
                   'notes': {'main': True}},
    'last_editor': 'BI8SQL', 'last_edit_time': '2026-10-25 10:00:00',
    'last_version': '2.9.0', 'encrypted': False,
}

PROJ = os.path.join(TMP, 'a.fhla')
win = QMainWindow()
pj.main(win, filee=records, save_path=PROJ, fhla_meta=meta)
win.resize(1100, 500)
win.show()
for _ in range(6):
    app.processEvents()


def scan(win_obj, tag):
    print('--- %s ---' % tag)
    print('  标题: %r' % win_obj.windowTitle())
    tbl = None
    for t in win_obj.findChildren(QTableWidget):
        m = t.model()
        hdr = [m.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
               for i in range(m.columnCount())]
        print('  表头: %r' % (hdr,))
        cells0 = [t.item(r, 0).text() for r in range(t.rowCount()) if t.item(r, 0)]
        if cells0:
            print('  第一列: %r' % (cells0,))
        tbl = t or tbl
    bad = []
    for lab in win_obj.findChildren(QLabel):
        if lab.text() and CJK.search(lab.text()):
            bad.append(('QLabel', lab.text()[:60]))
    for b in win_obj.findChildren(QPushButton):
        if b.text() and CJK.search(b.text()):
            bad.append(('QPushButton', b.text()))
    for a in win_obj.findChildren(QAction):
        if a.text() and CJK.search(a.text()):
            bad.append(('QAction', a.text()))
    if bad:
        print('  中文残留:')
        for k, v in bad:
            print('    %s %r' % (k, v))
    else:
        print('  无控件中文残留')


scan(win, '主窗口')
for m in win.menuBar().findChildren(QMenu):
    acts = [a.text() for a in m.actions() if a.text()]
    print('  菜单 %r: %r' % (m.title(), acts))

# 项目属性（QMessageBox）
_msgs.clear()
win._perf_api['show_project_props']() if win._perf_api.get('show_project_props') else None
print('--- 项目属性 QMessageBox ---')
for title, text in _msgs:
    print('  标题: %r' % title)
    for ln in text.splitlines():
        mark = '  ★中文' if CJK.search(ln) else ''
        print('    %s%s' % (ln, mark))

# 切回中文：属性窗口必须与历史输出逐字一致（全角冒号、中文属性名）
i18n.set_language('zh', app)
for _ in range(3):
    app.processEvents()
_msgs.clear()
win._perf_api['show_project_props']()
print('--- 项目属性 QMessageBox（中文）---')
for title, text in _msgs:
    print('  标题: %r' % title)
    for ln in text.splitlines():
        print('    %r' % ln)
_zh_lines = _msgs[0][1].splitlines() if _msgs else []
_zh_ok = bool(_zh_lines) and all('：' in ln and ': ' not in ln for ln in _zh_lines)
print('  中文格式未被破坏（全角冒号 / 属性名全中文）: %s' % ('是' if _zh_ok else '否'))

# 自定义日志字段窗口
_msgs.clear()
pj.custom_fields_action if False else None
for a in win.menuBar().actions():
    pass
try:
    win._perf_api['manage_custom_fields']()
except Exception as e:
    print('  （manage_custom_fields 不可直接调用：%s）' % e)
for _ in range(5):
    app.processEvents()
w = pj.custom_fields_window
if w is not None:
    scan(w, '自定义日志字段窗口')
    for ln in _msgs:
        print('  弹窗:', ln)

# ---- 语言来回切换 / 上移后重译：标准字段名跟着翻，自定义字段名一个字都不能变 ----
if w is not None:
    tbl_cf = w.findChildren(QTableWidget)[0]
    def names():
        return [tbl_cf.item(r, 0).text() for r in range(tbl_cf.rowCount())
                if tbl_cf.item(r, 0)]
    print('--- 自定义日志字段：语言切换 ---')
    print('  en: %r' % (names(),))
    i18n.set_language('zh', app)
    for _ in range(4):
        app.processEvents()
    zh = names()
    print('  zh: %r' % (zh,))
    # 上移一行（把「备注」往上挪）后再切英文：断言不串行
    tbl_cf.setCurrentCell(len(zh) - 2, 0)
    for b in w.findChildren(QPushButton):
        if b.text() in ('上移', 'Move up'):
            b.click()
            break
    for _ in range(3):
        app.processEvents()
    i18n.set_language('en', app)
    for _ in range(4):
        app.processEvents()
    en2 = names()
    print('  en(上移后): %r' % (en2,))
    bad = [n for n in en2 if n in ('日期', '时间', '己方呼号', '备注')]
    print('  标准字段残留中文: %r' % (bad or '无'))
    print('  自定义字段名仍在: %r' % ([n for n in en2 if n in ('天气', '备用设备')],))
    # 保存：自定义字段名保持用户填的，标准字段按 key 存中文
    for b in w.findChildren(QPushButton):
        if b.text() in ('保存更改', 'Save changes'):
            b.click()
            break
    for _ in range(4):
        app.processEvents()

# 更多信息
win._perf_api['project_others'](0)
for _ in range(5):
    app.processEvents()
w2 = pj.project_others_window
if w2 is not None:
    scan(w2, '更多信息窗口')

with io.open(SETT, 'wb') as f:
    f.write(_BAK)
shutil.rmtree(TMP, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
