# -*- coding: utf-8 -*-
r"""请求3离屏冒烟：卫星窗 + 互助窗 全链路（含磁头真实数据回写与备份/还原）。

执行目录 D:/F-Dev/BIG/F_HamLog（与用户主项目同构）。
前置：
  venv: D:/F-Dev/BIG/F_HamLog/.venv/Scripts/python.exe  (PySide6)
  QT_QPA_PLATFORM=offscreen (脚本内 os.environ 设置，进程内默认可见)

验证三件事：
  A. 清空星历之后刷新星历，「星历更新时间」显示新时间戳（不再「尚未获取」）
     — satellite_window 刷新星历回写 sat_last_update；
     — mutual_window 刷新星历同样回写（共享设置键）。
  B. 清空星历时自选卫星选择保留（selected_numbers / sat_sats 不被清掉）。
  C. 界面可见文案（窗口标题/标签/按钮/工具提示/状态栏/菜单/对话框）任何位置
     不出现配置文件名与位置：file/、file\、file\amateur.tle、file\m_xml.txt、
     file\tle_sources.txt、satellite_pred.py、satellite_window.py、mutual_window.py、
     user_settings.txt。

会改写 file/m_xml.txt 与 file/amateur.tle —— 先备份字节，结束时恢复 + md5 校验。

复用 __clear_tle_smoke.py 骨架：按钮直点 + FakeWorker + 全模态补丁。
"""

import ast
import glob
import hashlib
import os
import shutil
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(PROJ, '__req3_smoke_out.txt')
OUT_LINES = []


def out(s):
    OUT_LINES.append(str(s))
    print(s)


os.chdir(PROJ)
sys.path.insert(0, PROJ)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

# ---------------------------------------------------------------- 前置备份
TLE_CACHE = os.path.join(PROJ, 'file', 'amateur.tle')
SETTINGS = os.path.join(PROJ, 'file', 'm_xml.txt')


def _md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


_baks = []
for _p in (TLE_CACHE, SETTINGS):
    if os.path.exists(_p):
        _bak = _p + '.req3_bak'
        shutil.copyfile(_p, _bak)
        _baks.append((_p, _bak, _md5(_p)))
    else:
        _baks.append((_p, None, None))
out('备份: %s' % [(os.path.basename(p), b is not None) for p, b, _ in _baks])


def _restore():
    for _p, _bak, _h in _baks:
        if _bak is None:
            if os.path.exists(_p):
                os.remove(_p)
        else:
            shutil.copyfile(_bak, _p)
            if _md5(_p) != _h:
                out('!!! 恢复后 md5 不一致: %s' % _p)
    for _p, _bak, _h in _baks:
        if _bak is not None and os.path.exists(_bak):
            os.remove(_bak)


# ---------------------------------------------------------------- seed settings
SEED_EPOCH = time.time() - 3 * 86400
SEED = {
    'm_call': 'BA1ABC',
    'm_lat': 39.9042,
    'm_lon': 116.4074,
    'm_alt': 50.0,
    'sat_sats': ['25544'],
    'sat_last_update': SEED_EPOCH,
}
with open(SETTINGS, 'w', encoding='utf-8') as f:
    f.write(repr(SEED))

# 造一个假 TLE 缓存（2 颗，编号 25544/99901，都在 5 位以内）
FAKE_TLE = (
    'ISS (ZARYA)\n'
    '1 25544U 98067A   26270.50000000  .00010000  00000-0  20000-3 0  9990\n'
    '2 25544  51.6000 170.0000 0006000  70.0000 290.0000 15.50000000 10009\n'
    'MOCK-SAT-B\n'
    '1 99901U 98067B   26270.60000000  .00009000  00000-0  18000-3 0  9991\n'
    '2 99901  51.6000 170.0000 0006000  70.0000 290.0000 15.50000000 10019\n'
)
with open(TLE_CACHE, 'w', encoding='utf-8') as f:
    f.write(FAKE_TLE)

# ---------------------------------------------------------------- Qt / 模块
from PySide6 import QtWidgets
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import satellite_pred as sp
import satellite_window as sw

# FakeWorker：不做网络请求；emit 的卫星列表与真实 TleFetchWorker 相同形态。
FAKE_SATS = list(sp.parse_tle_text(FAKE_TLE))


class FakeWorker(QObject):
    fetched = Signal(list)
    progress = Signal(str)
    progress_pct = Signal(int)
    warning = Signal(str)
    error = Signal(str)
    canceled = Signal()
    finished = Signal()   # 真实 refresh_tle 会 connect(worker.finished, deleteLater)

    def __init__(self, force=False, *a, **k):
        super().__init__()
        self._force = force

    def isRunning(self):
        return False

    def requestInterruption(self):
        pass

    def wait(self, m=0):
        return True

    def start(self):
        # 同步发 fetched：主线程槽立即执行，无需等真实下载线程
        self.fetched.emit(list(FAKE_SATS))


# mutual_window 从 satellite_window 导入了 TleFetchWorker —— 两处命名空间都打补丁
sw.TleFetchWorker = FakeWorker
import mutual_window as mw  # noqa: E402

mw.TleFetchWorker = FakeWorker

# ---------------------------------------------------------------- 弹窗记录
BOX_MSGS = []   # (kind, title, text)


def _box(kind, ret):
    def _f(*a, **k):
        title = a[1] if len(a) > 1 else ''
        text = a[2] if len(a) > 2 else ''
        BOX_MSGS.append((kind, title, text))
        return ret
    return _f


QMessageBox.information = staticmethod(_box('information', QMessageBox.Ok))
QMessageBox.warning = staticmethod(_box('warning', QMessageBox.Ok))
QMessageBox.critical = staticmethod(_box('critical', QMessageBox.Ok))
QMessageBox.question = staticmethod(_box('question', QMessageBox.Yes))
QMessageBox.about = staticmethod(_box('about', None))

sw.ObserverDialog.exec = lambda self: QDialog.Rejected

# ---------------------------------------------------------------- 选择对话框补丁
# SatelliteSelectDialog.exec：不真弹，记录 get_selected()；可按模式注入勾选并 Accepted。
SEL_CAPTURE = []          # 每次 exec 记录 (tag, get_selected() 或 None)
DLG_TEXTS = []            # 对话框内可见文案（扫描用）
DLG_MODE = {'inject': None}   # 注入勾选的卫星名，None=直接 Rejected

_real_sel_exec = sw.SatelliteSelectDialog.exec


def _sel_exec(self):
    try:
        if DLG_MODE['inject'] is not None:
            it = self.items.get(DLG_MODE['inject'])
            if it is not None:
                it.setCheckState(Qt.CheckState.Checked)
        try:
            SEL_CAPTURE.append(self.get_selected())
        except Exception as e:
            SEL_CAPTURE.append(None)
            out('get_selected 异常: %r' % e)
        for w in self.findChildren(QtWidgets.QWidget):
            for attr in ('toolTip', 'windowTitle'):
                try:
                    v = getattr(w, attr)()
                except Exception:
                    v = ''
                if v:
                    DLG_TEXTS.append(v)
            if isinstance(w, QtWidgets.QLabel):
                DLG_TEXTS.append(w.text())
            elif isinstance(w, (QtWidgets.QPushButton, QtWidgets.QCheckBox,
                                QtWidgets.QRadioButton)):
                DLG_TEXTS.append(w.text())
            elif isinstance(w, QtWidgets.QGroupBox):
                DLG_TEXTS.append(w.title())
        return QDialog.Accepted if DLG_MODE['inject'] is not None else QDialog.Rejected
    finally:
        pass


sw.SatelliteSelectDialog.exec = _sel_exec

# ---------------------------------------------------------------- 可见文案扫描
FORBID = [
    'file/', 'file\\', 'file/',
    'amateur.tle', 'm_xml.txt', 'tle_sources.txt',
    'satellite_pred.py', 'satellite_window.py', 'mutual_window.py',
    'user_settings.txt',
]


def scan_widget_tree(root, tag):
    """收集 root 下所有可见文案，返回命中的禁用串列表 [(位置, 文本)]。"""
    hits = []
    texts = []

    def add(v):
        if isinstance(v, str) and v:
            texts.append(v)

    add(root.windowTitle())
    for w in root.findChildren(QtWidgets.QWidget):
        add(w.toolTip())
        add(w.windowTitle())
        add(w.statusTip())
        if isinstance(w, QtWidgets.QLabel):
            add(w.text())
        elif isinstance(w, (QtWidgets.QPushButton, QtWidgets.QCheckBox,
                            QtWidgets.QRadioButton, QtWidgets.QToolButton)):
            add(w.text())
        elif isinstance(w, QtWidgets.QGroupBox):
            add(w.title())
        elif isinstance(w, QtWidgets.QTabWidget):
            for i in range(w.count()):
                add(w.tabText(i))
        elif isinstance(w, QtWidgets.QComboBox):
            for i in range(w.count()):
                add(w.itemText(i))
        elif isinstance(w, QtWidgets.QListWidget):
            for i in range(w.count()):
                add(w.item(i).text())
        elif isinstance(w, QtWidgets.QTableWidget):
            for c in range(w.columnCount()):
                it = w.horizontalHeaderItem(c)
                if it is not None:
                    add(it.text())
    # 菜单栏
    mb = getattr(root, 'menuBar', None)
    if callable(mb):
        try:
            for men in root.menuBar().findChildren(QtWidgets.QMenu):
                add(men.title())
                for act in men.actions():
                    add(act.text())
        except Exception:
            pass
    for t in texts:
        for f in FORBID:
            if f in t:
                hits.append((tag, f, t.replace('\n', ' ⏎ ')[:120]))
    return hits


def wait_until(cond, timeout_s=10, what=''):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        app.processEvents()
        time.sleep(0.01)
        if cond():
            app.processEvents()
            return True
    out('!! wait_until 超时: %s' % what)
    return False


def find_btn(win, text):
    for b in win.findChildren(QPushButton):
        if b.text() == text:
            return b
    return None


def find_time_label(win):
    for l in win.findChildren(QtWidgets.QLabel):
        if l.text().startswith('星历更新时间：'):
            return l
    return None


def read_settings():
    """优先走 sw._load_settings，兜底直接 eval 文件。"""
    try:
        if hasattr(sw, '_load_settings'):
            st = sw._load_settings()
            if isinstance(st, dict):
                return dict(st)
    except Exception:
        pass
    with open(SETTINGS, encoding='utf-8') as f:
        return ast.literal_eval(f.read())


RESULTS = []


def ok(name, cond, extra=''):
    RESULTS.append(cond)
    out('%s - %s%s' % ('PASS' if cond else 'FAIL', name,
                       ('  [%s]' % extra) if extra else ''))


# ================================================================ 卫星过境窗口
out('=' * 60)
out('A/B/C · satellite_window')
out('=' * 60)
try:
    sw.main(None)
    win = sw._open_windows[-1]
except Exception as e:
    import traceback
    out('sw.main 异常: %r' % e)
    traceback.print_exc(file=sys.stdout)
    raise

# 等初始刷新（FakeWorker 同步完成）与预测线程结束
ok('窗口打开', win is not None)
wait_until(lambda: getattr(win, '_tle_worker', None) is None, 10, 'tle_worker')
wait_until(lambda: getattr(win, '_worker', None) is None, 20, 'predict worker')

# ---- 基线：标签显示旧时间戳（来自 seed）----
lab = find_time_label(win)
ok('A0 基线：打开时「星历更新时间」显示 seed 旧时间戳',
   lab is not None and '尚未获取' not in lab.text()
   and lab.text() != '星历更新时间：', lab.text() if lab else '(无标签)')

# ---- 基线：自选卫星 = seed 的 25544 ----
sel_before = None
DLG_MODE['inject'] = None
SEL_CAPTURE.clear()
btn_sel = find_btn(win, '选择卫星…')
if btn_sel is None:
    ok('B0 基线：找到「选择卫星…」按钮', False)
else:
    btn_sel.click()
    app.processEvents()
    if SEL_CAPTURE:
        sel_before = SEL_CAPTURE[-1]
ok('B0 基线：打开选择框可见自选卫星（seed 25544）',
   isinstance(sel_before, (set, frozenset)) and len(sel_before) == 1,
   repr(sel_before))

# ---- 清空星历（确认框 → Yes）----
btn_clear = find_btn(win, '清空星历')
ok('找到「清空星历」按钮', btn_clear is not None)
BOX_MSGS.clear()
btn_clear.click()
app.processEvents()
ok('清空确认框出现且不再提及文件路径',
   len(BOX_MSGS) == 1 and BOX_MSGS[0][0] == 'question'
   and 'amateur' not in BOX_MSGS[0][2] and 'file/' not in BOX_MSGS[0][2],
   repr(BOX_MSGS[:1]))
lab = find_time_label(win)
ok('A1 清空后「星历更新时间」= 尚未获取',
   lab is not None and '尚未获取' in lab.text(), lab.text() if lab else '(无标签)')
st = read_settings()
ok('A1b 清空后设置键 sat_last_update 已移除', 'sat_last_update' not in st,
   'keys=%s' % sorted(k for k in st if k.startswith('sat')))
ok('B1 清空后自选卫星仍在设置里（sat_sats）',
   st.get('sat_sats') == ['25544'], repr(st.get('sat_sats')))

# ---- 手动刷新星历 ----
btn_ref = find_btn(win, '刷新星历')
ok('找到「刷新星历」按钮', btn_ref is not None)
BOX_MSGS.clear()
btn_ref.click()
app.processEvents()
wait_until(lambda: getattr(win, '_tle_worker', None) is None, 10, 'tle refetch')
wait_until(lambda: getattr(win, '_worker', None) is None, 20, 'predict refetch')
lab = find_time_label(win)
ok('A2 刷新后「星历更新时间」显示新时间戳（不再「尚未获取」）',
   lab is not None and '尚未获取' not in lab.text(), lab.text() if lab else '(无标签)')
st = read_settings()
new_ts = st.get('sat_last_update')
ok('A2b 刷新后设置键 sat_last_update 已回写且为当前时间',
   isinstance(new_ts, (int, float)) and abs(new_ts - time.time()) < 120,
   repr(new_ts))
# on_fetched 里时间戳回写后，因自选卫星非空会立即 run_prediction()，
# 状态栏「已更新星历…」是瞬态文案（随即被预测状态覆盖）——断言接受链路上
# 任一稳定标志：瞬态「已更新星历」/「正在计算过境」/预测完成「已选 1 颗」。
_st_texts = [b.text() for b in win.findChildren(QtWidgets.QLabel)]
ok('A2c 刷新链路完成（瞬态已更新星历→自动预测已选 1 颗）',
   any(('已更新星历' in t) or ('正在计算过境' in t) or ('已选 1 颗' in t)
       for t in _st_texts),
   repr([t for t in _st_texts if t][:3]))

# ---- 刷新后再开选择框：选择保留 ----
DLG_MODE['inject'] = None
SEL_CAPTURE.clear()
btn_sel.click()
app.processEvents()
sel_after = SEL_CAPTURE[-1] if SEL_CAPTURE else None
ok('B2 清空→刷新后自选卫星保留（选择框内容与刷新前一致）',
   sel_after == sel_before and bool(sel_after), repr(sel_after))

# ---- C：卫星窗口可见文案扫描 ----
hits = scan_widget_tree(win, 'satellite_window')
ok('C1 卫星窗口可见文案无配置文件名/路径', not hits, repr(hits[:4]))
ok('C1b 选择对话框可见文案无配置文件名/路径',
   not [t for t in DLG_TEXTS for f in FORBID if f in t],
   repr([t for t in DLG_TEXTS for f in FORBID if f in t][:3]))
ok('C1c 弹窗文案无配置文件名/路径',
   not [m for m in BOX_MSGS for f in FORBID if f in m[2]],
   repr([m for m in BOX_MSGS for f in FORBID if f in m[2]][:3]))

# ================================================================ 互助/通联预测窗口
out('=' * 60)
out('A/C · mutual_window')
out('=' * 60)
mw.TleFetchWorker = FakeWorker   # 再钉一次（防同名覆盖）
try:
    mw.main(None)
    mwin = mw._open_windows[-1]
except Exception as e:
    import traceback
    out('mw.main 异常: %r' % e)
    traceback.print_exc(file=sys.stdout)
    raise

ok('互助窗口打开', mwin is not None)
wait_until(lambda: getattr(mwin, '_tle_worker', None) is None, 10, 'm tle')
wait_until(lambda: getattr(mwin, '_worker', None) is None, 20, 'm worker')

# ---- 互助：清空 → 刷新 → 时间戳回写 ----
mclear = find_btn(mwin, '清空星历')
mref = find_btn(mwin, '刷新星历')
ok('互助窗口找到「清空星历」「刷新星历」按钮',
   mclear is not None and mref is not None)
BOX_MSGS.clear()
mclear.click()
app.processEvents()
st = read_settings()
ok('A3 互助清空后设置键 sat_last_update 已移除', 'sat_last_update' not in st, '')
BOX_MSGS.clear()
mref.click()
app.processEvents()
wait_until(lambda: getattr(mwin, '_tle_worker', None) is None, 10, 'm refetch')
wait_until(lambda: getattr(mwin, '_worker', None) is None, 20, 'm worker')
st = read_settings()
new_ts2 = st.get('sat_last_update')
ok('A4 互助刷新后设置键 sat_last_update 回写且为当前时间',
   isinstance(new_ts2, (int, float)) and abs(new_ts2 - time.time()) < 120,
   repr(new_ts2))
ok('A4b 互助刷新后状态栏为「已载入星历：…」',
   any('已载入星历' in b.text() for b in mwin.findChildren(QtWidgets.QLabel)), '')

# ---- 互助：清空后自选卫星保留 ----
sel_m1 = None
DLG_MODE['inject'] = None
SEL_CAPTURE.clear()
mbtn = find_btn(mwin, '选择卫星…')
if mbtn is None:
    ok('互助窗口找到「选择卫星…」按钮', False)
else:
    mbtn.click()
    app.processEvents()
    sel_m1 = SEL_CAPTURE[-1] if SEL_CAPTURE else None
ok('B3 互助窗口清空→刷新后自选卫星保留',
   isinstance(sel_m1, (set, frozenset)) and len(sel_m1) == 1, repr(sel_m1))

# ---- C：互助窗口可见文案扫描 ----
hits_m = scan_widget_tree(mwin, 'mutual_window')
ok('C2 互助窗口可见文案无配置文件名/路径', not hits_m, repr(hits_m[:4]))
ok('C2b 互助弹窗文案无配置文件名/路径',
   not [m for m in BOX_MSGS for f in FORBID if f in m[2]],
   repr([m for m in BOX_MSGS for f in FORBID if f in m[2]][:3]))

# ---------------------------------------------------------------- 汇总
out('=' * 60)
n_pass = sum(1 for r in RESULTS if r)
n_all = len(RESULTS)
out('RESULT: %d/%d PASS %s' % (n_pass, n_all,
                               'ALL_OK' if n_pass == n_all else 'FAIL'))

# ---------------------------------------------------------------- 还原
win.close()
mwin.close()
app.processEvents()
_restore()
out('已还原 file/m_xml.txt 与 file/amateur.tle（字节级备份）。')

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT_LINES) + '\n')

sys.exit(0 if n_pass == n_all else 1)
