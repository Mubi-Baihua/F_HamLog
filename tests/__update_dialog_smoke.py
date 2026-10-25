"""更新界面冒烟：本地安装包对话框（叉号能不能关）+ 下载进度窗（最小化 / 非模态）。

这两处都是「看着是小事、其实很难发现」的 Qt 坑：

* QMessageBox **没有 RejectRole 按钮时，标题栏叉号和 Esc 都失效**（实测两按钮怎么点
  都不关）。所以 _ask_cached 自己排按钮，这个测试盯住「叉号 / Esc / 稍后」三条退路。
* QProgressDialog 默认窗口标志里没有最小化框；而它是模态的话，最小化自己之后父窗口
  仍被阻塞，点了没反应，看起来像卡死。所以它得是非模态 + 可最小化。

跑：QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/__update_dialog_smoke.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

TMP = tempfile.mkdtemp(prefix='__upd_dlg_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
with open(os.path.join(TMP, 'file', 'm_xml.txt'), 'w', encoding='utf-8') as f:
    f.write(str({'m_call': 'BI8SQL'}))
os.environ['F_HAMLOG_DATA_DIR'] = TMP
os.environ['F_HAMLOG_UPDATE_DIR'] = os.path.join(TMP, 'update')

from PySide6.QtCore import Qt, QThread, QTimer, Signal           # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QMainWindow,  # noqa: E402
                               QProgressDialog, QPushButton)
from PySide6.QtTest import QTest                                  # noqa: E402

from f_hamlog import set as set_mod                               # noqa: E402

app = QApplication(sys.argv)

results = []


def ok(name, cond, detail=''):
    results.append((bool(cond), name, detail))
    print('%s %s  %s' % ('PASS' if cond else 'FAIL', name, detail))


# ---------------------------------------------------------------- 找当前的 QDialog
def find_dialog():
    for w in app.topLevelWidgets():
        if isinstance(w, QDialog) and w.isVisible() and not isinstance(w, QProgressDialog):
            return w
    return None


def answer(action, delay=150):
    """在 exec() 起来之后对对话框做一件事（点按钮 / 关窗 / 按 Esc）。"""
    def run():
        dlg = find_dialog()
        if dlg is None:
            return
        if action == 'close':
            dlg.close()
        elif action == 'esc':
            QTest.keyClick(dlg, Qt.Key_Escape)
        else:
            for b in dlg.findChildren(QPushButton):
                if b.text() == action:
                    b.click()
                    return
    QTimer.singleShot(delay, run)


FOUND = {'path': r'C:\Users\13577\AppData\Local\Temp\F_HamLog_update\F.HamLog.2.7.setup.exe',
         'size': 69746688, 'verified': 'name'}
TRUSTED = dict(FOUND, verified='meta')


# ---------------------------------------------------------------- A. 本地已有安装包
answer('close')
t0 = time.time()
choice = set_mod._ask_cached(None, '2.8.1', FOUND)
ok('A1 点叉能关掉（不再卡死）', choice == '' and time.time() - t0 < 3,
   '返回=%r 用时 %.2fs' % (choice, time.time() - t0))

answer('esc')
choice = set_mod._ask_cached(None, '2.8.1', FOUND)
ok('A2 Esc 也能关', choice == '', '返回=%r' % (choice,))

answer('稍后')
choice = set_mod._ask_cached(None, '2.8.1', FOUND)
ok('A3 「稍后」= 取消', choice == '', '返回=%r' % (choice,))

answer('立即安装')
choice = set_mod._ask_cached(None, '2.8.1', FOUND)
ok('A4 「立即安装」', choice == 'install', '返回=%r' % (choice,))

answer('重新下载')
choice = set_mod._ask_cached(None, '2.8.1', FOUND)
ok('A5 「重新下载」', choice == 'download', '返回=%r' % (choice,))


# 布局与文案（抓一次窗口再关掉）
seen = {}


def inspect():
    dlg = find_dialog()
    if dlg is None:
        return
    seen['title'] = dlg.windowTitle()
    seen['buttons'] = [b.text() for b in dlg.findChildren(QPushButton)]
    seen['default'] = [b.text() for b in dlg.findChildren(QPushButton) if b.isDefault()]
    seen['labels'] = [w.text() for w in dlg.findChildren(QLabel)]
    seen['size'] = (dlg.width(), dlg.height())
    seen['flags'] = dlg.windowFlags()
    # 长路径是否自动换行：主文本标签比一行高，就说明折行了
    for w in dlg.findChildren(QLabel):
        if '安装包' in w.text():
            seen['wrapped'] = w.height() >= 2 * w.fontMetrics().height()
            seen['line_h'] = w.fontMetrics().height()
            seen['label_h'] = w.height()
    dlg.close()


QTimer.singleShot(150, inspect)
set_mod._ask_cached(None, '2.8.1', FOUND)
ok('A6 三个按钮顺序正确（主操作在最左、稍后最右）',
   seen.get('buttons') == ['立即安装', '重新下载', '稍后'], str(seen.get('buttons')))
ok('A7 未校验时默认按钮是「重新下载」', seen.get('default') == ['重新下载'], str(seen.get('default')))
ok('A8 主文本带版本/路径/大小',
   any('2.8.1' in s and 'F.HamLog.2.7.setup.exe' in s and 'MB' in s for s in seen.get('labels') or []),
   str(seen.get('labels'))[:90])
ok('A9 提示未校验', any('没有校验过' in s for s in seen.get('labels') or []),
   str(seen.get('labels'))[:90])
ok('A10 长路径不把窗口撑爆（限宽 460~600）',
   460 <= (seen.get('size') or (0, 0))[0] <= 600,
   '窗口 %s，主文本换行=%s' % (seen.get('size'), seen.get('wrapped')))
ok('A10b 提示框也不可以最大化', not ((seen.get('flags') or Qt.WindowFlags())
                                    & Qt.WindowMaximizeButtonHint),
   hex(int(seen.get('flags') or 0)))

seen.clear()
QTimer.singleShot(150, inspect)
set_mod._ask_cached(None, '2.8.1', TRUSTED)
ok('A11 已校验时默认按钮是「立即安装」', seen.get('default') == ['立即安装'], str(seen.get('default')))
ok('A12 已校验时不用提示风险', not any('没有校验过' in s for s in seen.get('labels') or []),
   str(seen.get('labels'))[:90])


# ---------------------------------------------------------------- B. 下载进度窗
class FakeThread(QThread):
    """假的下载线程：不联网，按帧喂进度，撑住 3 秒好让界面断言。"""

    progressed = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url, sha256, version, force, parent=None):
        super().__init__(parent)
        self._stopped = False

    def run(self):
        for i in range(30):
            if self._stopped:
                return
            time.sleep(0.1)
            self.progressed.emit(i * 1024, 30 * 1024)

    def stop(self):
        self._stopped = True


orig_thread = set_mod._DownloadThread
set_mod._DownloadThread = FakeThread
set_mod._install_update = lambda *a, **k: None

win = QMainWindow()
win.resize(700, 500)
win.move(200, 150)
win.show()

set_mod._start_update_download(win, '2.9.0', 'http://127.0.0.1:1/x.exe')
app.processEvents()
dlg = set_mod._update_dialog

ok('B1 进度窗已创建', dlg is not None)
ok('B2 是独立顶层窗口（关掉设置窗口不中断下载）', dlg is not None and dlg.parent() is None,
   repr(dlg.parent() if dlg else None))
ok('B3 非模态（最小化后主窗口还能用）', dlg is not None and dlg.windowModality() == Qt.NonModal,
   str(dlg.windowModality() if dlg else ''))
ok('B4 窗口带最小化按钮', dlg is not None and bool(dlg.windowFlags() & Qt.WindowMinimizeButtonHint),
   hex(int(dlg.windowFlags())) if dlg else '')
ok('B4b 没有最大化按钮（进度条不该被拉成整屏）', dlg is not None
   and not (dlg.windowFlags() & Qt.WindowMaximizeButtonHint),
   hex(int(dlg.windowFlags())) if dlg else '')
if dlg is not None and sys.platform == 'win32' and not os.environ.get('QT_QPA_PLATFORM', ''):
    # 真机（windows 平台插件）才查得到系统样式；offscreen 下没有窗口句柄样式
    import ctypes
    WS_MAXIMIZEBOX = 0x00010000
    style = ctypes.windll.user32.GetWindowLongW(int(dlg.winId()), -16)
    ok('B4c 系统样式里也没有 WS_MAXIMIZEBOX', not style & WS_MAXIMIZEBOX, hex(style))
ok('B5 不是模态对话框（不阻塞主窗口）', app.activeModalWidget() is None,
   repr(app.activeModalWidget()))

dlg.showMinimized()
app.processEvents()
ok('B6 能最小化', dlg.isMinimized())
dlg.showNormal()
app.processEvents()
ok('B7 能还原', dlg.isVisible() and not dlg.isMinimized())

before = dlg
set_mod._start_update_download(win, '2.9.0', 'http://127.0.0.1:1/x.exe')
app.processEvents()
ok('B8 重复触发不开第二个窗', set_mod._update_dialog is before, 'id 变化=%s'
   % (set_mod._update_dialog is not before))

t0 = time.time()
while time.time() - t0 < 1.5:
    app.processEvents()
    time.sleep(0.02)
ok('B9 进度窗在更新文案', dlg.labelText() != '', dlg.labelText())

dlg.close()
for _ in range(40):
    app.processEvents()
    time.sleep(0.02)
ok('B10 点叉后关掉且不复弹', not dlg.isVisible(), '可见=%s' % dlg.isVisible())
ok('B11 关窗后清掉引用', set_mod._update_dialog is None)
ok('B12 关窗会停下线程', not set_mod._update_download_thread.isRunning(),
   '仍在跑=%s' % set_mod._update_download_thread.isRunning())

set_mod._DownloadThread = orig_thread

bad = [r for r in results if not r[0]]
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
if bad:
    for _, name, detail in bad:
        print('  失败：%s  %s' % (name, detail))
    sys.exit(1)
