# -*- coding: utf-8 -*-
"""冒烟：① 搜索 / 查找替换 / 统计图 能用自定义字段；② 加密日志真能加密、能解回来。

离屏运行（QT_QPA_PLATFORM=offscreen），不触碰 file/ 下的用户数据：
设置文件先备份后还原，项目备份重定向到临时目录，项目文件全在临时目录里。
所有 QMessageBox 都换成记录式桩（模态弹窗在离屏下会直接挂死）。
"""
import os
import sys
import time
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
                               QLineEdit, QMenu, QMessageBox, QMainWindow, QTableWidget)

from f_hamlog import backup
from f_hamlog.paths import app_path
from f_hamlog import data_factory as fhlgen

SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.cf_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_cfenc_')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QApplication.instance() or QApplication(sys.argv)

from f_hamlog import fhl_rw
from f_hamlog import project as pj

# ---- 所有消息框换成桩：记录 (类型, 正文)，绝不弹模态 ----
MSGS = []


def _stub_info(*a, **k):
    MSGS.append(('info', a[2] if len(a) > 2 else ''))
    return QMessageBox.Ok


def _stub_warn(*a, **k):
    MSGS.append(('warn', a[2] if len(a) > 2 else ''))
    return QMessageBox.Ok


def _stub_crit(*a, **k):
    MSGS.append(('crit', a[2] if len(a) > 2 else ''))
    return QMessageBox.Ok


QMessageBox.information = staticmethod(_stub_info)
QMessageBox.warning = staticmethod(_stub_warn)
QMessageBox.critical = staticmethod(_stub_crit)

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def wait_modal_closed(rounds=600):
    for _ in range(rounds):
        app.processEvents()
        if app.activeModalWidget() is None:
            return True
        time.sleep(0.005)
    return False


def drive(trigger, fill):
    """trigger 弹出模态对话框 → 用 fill(dlg) 填好并结束它。"""
    def attempt(tries=[100]):
        dlg = app.activeModalWidget()
        if isinstance(dlg, QDialog):
            fill(dlg)
            return
        tries[0] -= 1
        if tries[0] > 0:
            QTimer.singleShot(30, attempt)
    QTimer.singleShot(0, trigger)
    QTimer.singleShot(50, attempt)
    return wait_modal_closed()


def pick(combo, key):
    for i in range(combo.count()):
        if combo.itemData(i) == key:
            combo.setCurrentIndex(i)
            return True
    return False


def combo_keys(combo):
    return [combo.itemData(i) for i in range(combo.count())]


def menu_action(win, text):
    for m in win.menuBar().findChildren(QMenu):
        for a in m.actions():
            if a.text() == text:
                return a
    return None


# ---------------- 造数据：.fhla + 两个自定义字段 ----------------
records = fhlgen.generate_records(24)
for i, r in enumerate(records):
    r['wx'] = '晴' if i % 2 == 0 else '阴'
    r['rig'] = 'IC-705'
META = pj.normalize_meta({'other_item': {'wx': '天气', 'rig': '设备型号'}})
TMP = os.path.join(TMPDIR, 'cf.fhla')
pj.write_fhla_file(TMP, records, meta=META, editor='BG5ABC')

proj, _k = pj.read_fhla_file(TMP)
RECS = proj.get_fhl()
META2 = proj.get_xml()

win = QMainWindow()
pj.main(win, filee=RECS, save_path=TMP, fhla_meta=META2)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api

# ---------------- ① 自定义字段：搜索 ----------------
entries = api['field_entries']()
ok('字段定义含自定义字段 wx / rig',
   any(e[0] == 'wx' and e[4] for e in entries) and any(e[0] == 'rig' and e[4] for e in entries),
   str([e[0] for e in entries]))

seen = {}


def fill_search(dlg):
    combos = dlg.findChildren(QComboBox)
    seen['keys'] = combo_keys(combos[0])
    seen['picked'] = pick(combos[0], 'wx')
    dlg.findChildren(QLineEdit)[-1].setText('晴')
    dlg.findChild(QDialogButtonBox).accepted.emit()


drive(menu_action(win, '搜索').trigger, fill_search)

ok('搜索字段下拉框含自定义字段', 'wx' in (seen.get('keys') or []), str(seen.get('keys')))
ok('搜索字段下拉框含全部标准字段',
   all(k in (seen.get('keys') or []) for k in ('date', 'time', 'freq_rx', 'm_ant', 'notes')))

rw = None
for w in app.topLevelWidgets():
    if w.windowTitle().startswith('搜索结果'):
        rw = w
        break
ok('能按自定义字段搜到结果', rw is not None,
   str([w.windowTitle() for w in app.topLevelWidgets()][:4]))
if rw is not None:
    tr = rw.findChildren(QTableWidget)[0]
    expect = sum(1 for r in RECS if r.get('wx') == '晴')
    ok('搜索结果行数正确', tr.rowCount() == expect, f'{tr.rowCount()} vs {expect}')
    headers = [tr.horizontalHeaderItem(c).text() for c in range(tr.columnCount())]
    ok('结果表补上被搜字段列', '天气' in headers, str(headers))
    if '天气' in headers:
        ci = headers.index('天气')
        vals = {tr.item(r, ci).text() for r in range(tr.rowCount())}
        ok('该列显示的就是搜到的值', vals == {'晴'}, str(vals))
    ok('「更多」列仍在「定位到此条」之前',
       len(headers) >= 2 and headers[-2] == '更多' and headers[-1] == '定位到此条',
       str(headers[-2:]))
    ok('补列后「更多」委托挂在「更多」列（没跑到新补的字段列上）',
       isinstance(tr.itemDelegateForColumn(headers.index('更多')), pj.MoreButtonDelegate)
       and tr.itemDelegateForColumn(headers.index('天气')) is None)

    # 点「更多」按钮 → 打开「更多信息」窗口（补列后委托没串位的实证）
    _pos = tr.visualRect(tr.model().index(0, headers.index('更多'))).center()
    for _et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        app.sendEvent(tr.viewport(), QMouseEvent(
            _et, _pos, tr.viewport().mapToGlobal(_pos),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    app.processEvents()
    others = [w for w in app.topLevelWidgets() if w.windowTitle() == '更多信息']
    ok('结果表「更多」按钮仍可用', bool(others))
    for _w in others:
        _w.close()
    rw.close()


# ---------------- ① 自定义字段：查找替换 ----------------
def fill_replace(dlg):
    combos = dlg.findChildren(QComboBox)
    pick(combos[0], 'wx')
    edits = dlg.findChildren(QLineEdit)
    edits[0].setText('晴')
    edits[1].setText('多云')
    dlg.findChild(QDialogButtonBox).buttons()[0].click()   # 「替换」


drive(menu_action(win, '查找替换').trigger, fill_replace)
now = api['get_file']()
ok('查找替换能改自定义字段',
   all(r.get('wx') == '多云' for r in now if r.get('wx') != '阴'),
   str(sorted({str(r.get('wx')) for r in now})))
ok('查找替换没误伤其他记录', any(r.get('wx') == '阴' for r in now))
ok('替换完成提示有反馈', any('替换完成' in t for _k2, t in MSGS), str(MSGS[-1:]))


# ---------------- ① 自定义字段：统计图字段列表 ----------------
def fill_stats(dlg):
    combos = dlg.findChildren(QComboBox)
    seen['stat_keys'] = combo_keys(combos[0])
    dlg.findChild(QDialogButtonBox).rejected.emit()


drive(menu_action(win, '统计图').trigger, fill_stats)
sk = seen.get('stat_keys') or []
ok('统计图可选自定义字段', 'wx' in sk and 'rig' in sk, str(sk))
ok('统计图不含日期 / 时间', 'date' not in sk and 'time' not in sk)
ok('统计图含其他标准字段', 'freq_rx' in sk and 'm_rst' in sk and 'o_ant' in sk)

# ---------------- ② 加密：两次输入确认（不一致 / 为空 → 重新输入） ----------------
pair_seq = [('abc', 'abd'), ('', ''), ('pw123', 'pw123')]
orig_pair = fhl_rw._ask_key_pair
fhl_rw._ask_key_pair = lambda parent=None: pair_seq.pop(0)
before_warn = len(MSGS)
got = fhl_rw.get_new_key_dialog()
warns = [t for k2, t in MSGS[before_warn:] if k2 == 'warn']
ok('两次不一致 / 为空会重新输入直到一致', got == 'pw123', f'got={got}')
ok('不一致与为空各提示一次', len(warns) == 2, str(warns))
fhl_rw._ask_key_pair = orig_pair

# 取消（叉号 / 取消按钮）→ 返回 None
fhl_rw._ask_key_pair = lambda parent=None: None
ok('取消时返回 None', fhl_rw.get_new_key_dialog() is None)
fhl_rw._ask_key_pair = orig_pair


# ---------------- ② 加密：真的写到磁盘 ----------------
def is_enc(path):
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        raw.decode('utf-8')
        return False
    except UnicodeDecodeError:
        return True


ok('加密前是明文', not is_enc(TMP))
orig_new_key = fhl_rw.get_new_key_dialog
fhl_rw.get_new_key_dialog = lambda parent=None: 'pw123'
menu_action(win, '加密此项目').trigger()
for _ in range(5):
    app.processEvents()
ok('加密后文件是密文', is_enc(TMP))
recs2 = meta2 = None
try:
    recs2, k2, meta2 = pj.read_project_file(TMP, key='pw123', ask_key=False)
    ok('密文能用密钥读回', recs2 is not None and len(recs2) == len(RECS),
       f'{None if recs2 is None else len(recs2)} vs {len(RECS)}')
    ok('属性块标记已加密', bool((meta2 or {}).get('encrypted')))
except Exception as e:
    ok('密文能用密钥读回', False, repr(e))

# ---------------- ② 解密：也能写回明文 ----------------
if recs2 is not None:
    win2 = QMainWindow()
    pj.main(win2, filee=recs2, save_path=TMP, key_='pw123', fhla_meta=meta2)
    win2.show()
    for _ in range(5):
        app.processEvents()

    orig_ask = fhl_rw.get_user_key_dialog
    # 密钥输错时不能解密（文件必须还是密文）
    fhl_rw.get_user_key_dialog = lambda parent=None: 'wrong'
    menu_action(win2, '不再加密此项目').trigger()
    for _ in range(5):
        app.processEvents()
    ok('密钥错误时不写盘', is_enc(TMP))

    fhl_rw.get_user_key_dialog = lambda parent=None: 'pw123'
    menu_action(win2, '不再加密此项目').trigger()
    for _ in range(5):
        app.processEvents()
    ok('解密后文件是明文', not is_enc(TMP))
    plain, _k3, _m3 = pj.read_project_file(TMP, ask_key=False)
    ok('解密后记录数不变', plain is not None and len(plain) == len(RECS),
       f'{None if plain is None else len(plain)}')
    fhl_rw.get_user_key_dialog = orig_ask
fhl_rw.get_new_key_dialog = orig_new_key

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
sys.exit(0 if all(PASS) else 1)
