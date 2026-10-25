# -*- coding: utf-8 -*-
"""回归：「检查更新」不能把焦点甩到「我的呼号」上（离屏，不联网、不写用户数据）。

历史 bug：_start_update_check 里 button.setEnabled(False) 会让 Qt 立刻把焦点移交到
焦点链上的下一个可聚焦控件 —— 设置页里就是「我的呼号」QLineEdit，而 QLineEdit 因
TabFocusReason 拿到焦点时会**全选文本**，看起来就像"点检查更新自动选中了呼号"。

断言：
1. 点下去之后（后台线程还在跑的那一小段）按钮仍持有焦点，呼号没有被选中；
2. 「检查中…」靠文字表达，按钮不变灰（否则焦点一定被甩走）；
3. 线程返回后按钮文字复原，焦点依旧在按钮上；
4. 全程没写脏设置文件。

数据目录指向临时目录（F_HAMLOG_DATA_DIR），与 __set_update_btn_smoke.py 同款隔离。
用法：QT_QPA_PLATFORM=offscreen python tests/__update_btn_focus_smoke.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

TMP = tempfile.mkdtemp(prefix='__upd_focus_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
_SEED = {'m_call': 'BI8SQL', 'm_qth': '成都', 'm_lat': 30.0, 'm_lon': 104.0}
for _p in (os.path.join(TMP, 'file', 'm_xml.txt'), os.path.join(TMP, 'm_xml.txt')):
    with open(_p, 'w', encoding='utf-8') as _f:
        _f.write(str(_SEED))
os.environ['F_HAMLOG_DATA_DIR'] = TMP

from PySide6.QtWidgets import (QApplication, QLineEdit, QMainWindow,   # noqa: E402
                               QPushButton)

from f_hamlog import check_update, i18n, theme                  # noqa: E402
from f_hamlog import set as set_mod                             # noqa: E402

theme.settings_path = lambda: os.path.join(TMP, 'm_xml.txt')

results = []


def ok(name, cond, extra=''):
    results.append((bool(cond), name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


app = QApplication.instance() or QApplication(sys.argv)
theme.init_app(app)
i18n.install(app)

settings = os.path.join(TMP, 'file', 'm_xml.txt')
before = (os.path.getmtime(settings), os.path.getsize(settings))

win = QMainWindow()
set_mod.main(win)          # 真实设置页
for _ in range(8):
    app.processEvents()

call = [e for e in win.findChildren(QLineEdit)][0]     # main() 里第一个就是「我的呼号」
ok('C1 呼号已填入「我的呼号」', call.text() == 'BI8SQL', repr(call.text()))

label = i18n.tr('检查更新')
btns = [b for b in win.findChildren(QPushButton) if b.text() == label]
ok('C2 找到「检查更新」按钮', bool(btns), repr(label))
if not btns:
    sys.exit(1)
btn = btns[0]

# 结果处理换成哑巴（status=latest 本会弹模态框，把脚本挂住）；联网换成「50 ms 秒回」，
# 留出可观测的「检查中」窗口（0 ms 的话真机上一个事件循环就跑完了，看不见中间态）
got = []
set_mod._on_update_checked = lambda window, info, auto=False: got.append(info)


def _fake_check():
    time.sleep(0.05)
    return {'status': 'latest', 'version': '', 'url': ''}


check_update.check = _fake_check

btn.setFocus()
app.processEvents()
ok('C3 前置：焦点在按钮上', app.focusWidget() is btn)

btn.click()
for _ in range(4):
    app.processEvents()

ok('D1 检查期间按钮没有变灰', btn.isEnabled())
ok('D2 焦点没被甩到呼号框', app.focusWidget() is not call,
   '焦点=%s' % type(app.focusWidget()).__name__)
ok('D3 呼号没有被全选', not call.selectedText(), repr(call.selectedText()))
ok('D4 「检查中…」有文字反馈', btn.text() == i18n.tr('检查中…'), repr(btn.text()))

# 等后台线程回话（最多 2 s）
for _ in range(200):
    if got:
        break
    app.processEvents()
    app.thread().msleep(10)
for _ in range(4):
    app.processEvents()

ok('E1 收到检查结果', bool(got))
ok('E2 按钮文字复原', btn.text() == label, repr(btn.text()))
ok('E3 结果回来后焦点仍在按钮', app.focusWidget() is btn or app.focusWidget() is None,
   '焦点=%s' % type(app.focusWidget()).__name__)
ok('E4 呼号始终没被选中', not call.selectedText(), repr(call.selectedText()))
ok('F1 设置文件没被写脏',
   (os.path.getmtime(settings), os.path.getsize(settings)) == before)

bad = [r for r in results if not r[0]]
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
win.close()
sys.exit(1 if bad else 0)
