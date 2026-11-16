# -*- coding: utf-8 -*-
"""批量记录「自动保存到日志文件」边改边写（实时同步）—— 离屏冒烟。

覆盖点：
  L 项目窗口启动：默认勾选即开始实时同步；改格子 / 新增列 / 删除列 / 撤销都会
    同步到**启动它的那个日志**，项目窗口的表格随之显示（窗口页同步显示）
  H 主页启动：勾选后选好去处就开始实时同步；没填完的记录不写、填完后自动补上
  E 「完成」不再整份追加一遍（否则每点一次就多一份记录）

离屏运行；备份路径重定向到临时目录，不触碰 file/ 里的用户数据。
用法：python tests/__live_sync_smoke.py
"""
import os
import sys
import shutil
import tempfile
import time as _time
import atexit

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtWidgets import (QCheckBox, QDialog, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem)

from f_hamlog import backup
from f_hamlog import project
from f_hamlog import batch_project

TMP = tempfile.mkdtemp(prefix='fhl_live_sync_smoke_')
atexit.register(lambda: shutil.rmtree(TMP, ignore_errors=True))

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

backup.PROJECT_BACKUP = os.path.join(TMP, 'project_backup.fhl')
backup.BATCH_BACKUP = os.path.join(TMP, 'batch_backup.fhl')

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def pump(n=5):
    for _ in range(n):
        app.processEvents()


def wait_until(pred, timeout=4.0):
    """等实时同步的防抖定时器到点（离屏下必须真的走一遍事件循环）。"""
    end = _time.time() + timeout
    while _time.time() < end:
        app.processEvents()
        if pred():
            return True
        _time.sleep(0.02)
    return False


# ---- 模态弹窗全部静默 ----
POPUPS = []
QMessageBox.information = lambda parent=None, title='', text='', *a, **k: (
    POPUPS.append(('info', title, text)), QMessageBox.Ok)[1]
QMessageBox.warning = lambda parent=None, title='', text='', *a, **k: (
    POPUPS.append(('warn', title, text)), QMessageBox.Ok)[1]
QMessageBox.question = lambda *a, **k: QMessageBox.No

DIALOG_TEXTS = []
_real_exec = QDialog.exec


def _fake_exec(self):
    for lb in self.findChildren(QtWidgets.QLabel):
        DIALOG_TEXTS.append(lb.text())
    for rb in self.findChildren(QtWidgets.QRadioButton):
        DIALOG_TEXTS.append('OPT:' + rb.text())
    return QDialog.Rejected


QDialog.exec = _fake_exec


def _button(widget, text):
    return next((b for b in widget.findChildren(QPushButton) if b.text() == text), None)


def _rec(o_call, date='2026-11-16', time='10:00', notes=''):
    return {
        'date': date, 'time': time, 'm_call': 'BI8SQL', 'o_call': o_call,
        'freq': '144.100', 'freq_rx': '', 'mode': 'FM', 'prop_mode': '',
        'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
        'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
        'notes': notes,
    }


def _calls(records):
    return [r.get('o_call') for r in (records or [])]


def _read(path):
    data, _k, _m = project.read_project_file(path)
    return data or []


def _fill_col(tbl, vals, col=None):
    """在表格末尾（或指定列）填一条记录，等价于 Ctrl+N 后逐格输入。"""
    if col is None:
        col = tbl.columnCount()
        tbl.insertColumn(col)
    for r, k in enumerate(batch_project.KEYS):
        tbl.setItem(r, col, QTableWidgetItem(vals.get(k, '')))
    return col


def _set_cell(tbl, col, key, text):
    tbl.setItem(batch_project.KEYS.index(key), col, QTableWidgetItem(text))


FULL = {'date': '2026-11-16', 'time': '10:20', 'm_call': 'BI8SQL',
        'o_call': 'BG7X1', 'freq': '144.200', 'mode': 'FM',
        'm_rst': '59', 'o_rst': '59'}

# ==========================================================================
# L. 项目窗口启动：边改边写
# ==========================================================================
print('--- L 项目窗口启动 ---', flush=True)
A = os.path.join(TMP, 'a.fhla')
project.save_project_file(A, [_rec('BG1A1')])

win = QtWidgets.QMainWindow()
project.main(win, [_rec('BG1A1')], A)
pump()
api = win._perf_api

bw = QtWidgets.QMainWindow()
batch_project.main(bw, on_saved=api['append_to_project'],
                   sync_io=api['live_sync_io']())
pump(3)

cb = next(c for c in bw.findChildren(QCheckBox)
          if c.text().startswith('自动保存到日志文件'))
ok('L1 由项目窗口启动时「自动保存」默认勾选', cb.isChecked())

tbl = bw.findChild(QTableWidget)
# 新加一列并填完整 → 不用点「完成」就该出现在日志里
col1 = _fill_col(tbl, FULL)
ok('L2 填完一条就同步进日志（不用点完成）',
   wait_until(lambda: _calls(_read(A)) == ['BG1A1', 'BG7X1']),
   str(_calls(_read(A))))
ok('L3 项目窗口的表格同步显示出新记录（窗口页同步显示）',
   api['get_table']().rowCount() == 2, str(api['get_table']().rowCount()))
ok('L4 项目窗口的内存里也有这条', _calls(api['get_file']()) == ['BG1A1', 'BG7X1'],
   str(_calls(api['get_file']())))

# 改一个格子（对方呼号）→ 就地更新那一条，不新增
_set_cell(tbl, col1, 'o_call', 'BG7Y2')
ok('L5 改格子后就地更新那一条（不产生重复记录）',
   wait_until(lambda: _calls(_read(A)) == ['BG1A1', 'BG7Y2']),
   str(_calls(_read(A))))

# 再改一个非必填字段 → 也同步过去
_set_cell(tbl, col1, 'notes', '59+')
ok('L6 备注等非必填字段同样同步', wait_until(
    lambda: [r.get('notes') for r in _read(A)][-1:] == ['59+']),
   str([r.get('notes') for r in _read(A)]))

# 没填完的一列（缺对方呼号）→ 先不写日志
col2 = _fill_col(tbl, dict(FULL, o_call=''))
_time.sleep(0.6)
pump(5)
ok('L7 没填完的记录先不写进日志', _calls(_read(A)) == ['BG1A1', 'BG7Y2'],
   str(_calls(_read(A))))
# 填上呼号 → 自动补上
_set_cell(tbl, col2, 'o_call', 'BG7Z3')
ok('L8 填完之后自动补进日志',
   wait_until(lambda: _calls(_read(A)) == ['BG1A1', 'BG7Y2', 'BG7Z3']),
   str(_calls(_read(A))))

# 删除当前列（Ctrl+D）→ 日志里那条也删掉
tbl.setCurrentCell(0, col2)
pump(2)
_button(bw, '删除当前列 (Ctrl+D)').click()
ok('L9 删除一列后日志里那条也没了',
   wait_until(lambda: _calls(_read(A)) == ['BG1A1', 'BG7Y2']),
   str(_calls(_read(A))))
ok('L10 项目窗口的表格跟着少一行', api['get_table']().rowCount() == 2,
   str(api['get_table']().rowCount()))

# 撤销删除 → 记录回来
_button(bw, '撤销 (Ctrl+Z)').click()
ok('L11 撤销删除后记录回到日志',
   wait_until(lambda: _calls(_read(A)) == ['BG1A1', 'BG7Y2', 'BG7Z3']),
   str(_calls(_read(A))))

# 「完成」不再整份追加一遍；已同步的内容一关窗就该干净（不弹未保存提示）
POPUPS.clear()
_button(bw, '完成 (Ctrl+S)').click()
pump(5)
ok('L12 点「完成」不会重复追加同一批记录',
   _calls(_read(A)) == ['BG1A1', 'BG7Y2', 'BG7Z3'], str(_calls(_read(A))))
ok('L13 已实时同步的内容关窗时不问「是否保存」',
   not any('未保存' in (p[1] + p[2]) for p in POPUPS), str(POPUPS))

# ==========================================================================
# H. 主页启动：勾选时选好去处
# ==========================================================================
print('--- H 主页启动 ---', flush=True)
HOME = os.path.join(TMP, 'home.fhla')
project.save_project_file(HOME, [])

_real_choose = batch_project.choose_save_target
bw2 = QtWidgets.QMainWindow()
batch_project.main(bw2)
pump(3)
cb2 = next(c for c in bw2.findChildren(QCheckBox)
           if c.text().startswith('自动保存到日志文件'))
ok('H1 主页启动默认不勾选', not cb2.isChecked())

batch_project.choose_save_target = lambda parent, heading: ('default', HOME)
cb2.setChecked(True)
pump(3)
batch_project.choose_save_target = _real_choose
ok('H2 勾选后就选好了去处（复选框仍是「日志文件」不带文件名）',
   cb2.text() == '自动保存到日志文件', cb2.text())

tbl2 = bw2.findChild(QTableWidget)
c21 = _fill_col(tbl2, dict(FULL, o_call='BG8H1'))
ok('H3 主页启动时边填边写进选定的日志',
   wait_until(lambda: _calls(_read(HOME)) == ['BG8H1']), str(_calls(_read(HOME))))

# 撤掉一个必填项 → 日志里保留上一次的完整内容（别把半条写进去 / 也别整条删掉）
_set_cell(tbl2, c21, 'freq', '')
_time.sleep(0.6)
pump(5)
ok('H4 中途清空必填项时日志里保留上一条完整记录（不写半条，也不删）',
   _calls(_read(HOME)) == ['BG8H1'], str(_calls(_read(HOME))))
_set_cell(tbl2, c21, 'freq', '145.500')
ok('H5 补回来之后同步更新', wait_until(
    lambda: [r.get('freq') for r in _read(HOME)] == ['145.500']),
   str([r.get('freq') for r in _read(HOME)]))

POPUPS.clear()
_button(bw2, '完成 (Ctrl+S)').click()
pump(5)
ok('H6 主页启动同样不会重复追加', _calls(_read(HOME)) == ['BG8H1'],
   str(_calls(_read(HOME))))

# ==========================================================================
# U. 中途取消勾选再点「完成」：不能把已同步的记录再追加一遍
# ==========================================================================
print('--- U 取消勾选后完成 ---', flush=True)
U = os.path.join(TMP, 'u.fhla')
W = os.path.join(TMP, 'w.fhla')
project.save_project_file(U, [])
project.save_project_file(W, [])

win_u = QtWidgets.QMainWindow()
project.main(win_u, [], U)
pump()
api_u = win_u._perf_api
bw_u = QtWidgets.QMainWindow()
batch_project.main(bw_u, on_saved=api_u['append_to_project'],
                   sync_io=api_u['live_sync_io'](), auto_target_path=U)
pump(3)
tbl_u = bw_u.findChild(QTableWidget)
_fill_col(tbl_u, dict(FULL, o_call='BG9U1'))
ok('U1 先实时同步一条', wait_until(lambda: _calls(_read(U)) == ['BG9U1']),
   str(_calls(_read(U))))

cb_u = next(c for c in bw_u.findChildren(QCheckBox)
            if c.text().startswith('自动保存到日志文件'))
cb_u.setChecked(False)
pump(3)
_real_choose2 = batch_project.choose_save_target
batch_project.choose_save_target = lambda parent, heading: ('append', U)
_button(bw_u, '完成 (Ctrl+S)').click()
pump(5)
batch_project.choose_save_target = _real_choose2
ok('U2 取消勾选后仍选同一个日志：不会重复追加',
   _calls(_read(U)) == ['BG9U1'], str(_calls(_read(U))))

# 换成别的日志 → 该全写过去（那才是用户要的）
win_v = QtWidgets.QMainWindow()
project.main(win_v, _read(U), U)
pump()
api_v = win_v._perf_api
bw_v = QtWidgets.QMainWindow()
batch_project.main(bw_v, on_saved=api_v['append_to_project'],
                   sync_io=api_v['live_sync_io'](), auto_target_path=U)
pump(3)
tbl_v = bw_v.findChild(QTableWidget)
_fill_col(tbl_v, dict(FULL, o_call='BG9V1'))
ok('U3 第二个窗口边填边写', wait_until(lambda: _calls(_read(U)) == ['BG9U1', 'BG9V1']),
   str(_calls(_read(U))))
cb_v = next(c for c in bw_v.findChildren(QCheckBox)
            if c.text().startswith('自动保存到日志文件'))
cb_v.setChecked(False)
pump(3)
batch_project.choose_save_target = lambda parent, heading: ('append', W)
_button(bw_v, '完成 (Ctrl+S)').click()
pump(5)
batch_project.choose_save_target = _real_choose2
ok('U4 取消勾选后改存到别的日志：照样写过去（不被去重逻辑误删）',
   _calls(_read(W)) == ['BG9V1'], str(_calls(_read(W))))
ok('U5 原日志两条都在', _calls(_read(U)) == ['BG9U1', 'BG9V1'],
   str(_calls(_read(U))))

# 取消勾选后**再勾回来**：接着同步，改格子仍然就地更新（不重复追加）
bw_r = QtWidgets.QMainWindow()
batch_project.main(bw_r, on_saved=api_u['append_to_project'],
                   sync_io=api_u['live_sync_io'](), auto_target_path=U)
pump(3)
tbl_r = bw_r.findChild(QTableWidget)
col_r = _fill_col(tbl_r, dict(FULL, o_call='BG9R1'))
ok('U6 再开一个窗口：边填边写', wait_until(
    lambda: _calls(_read(U)) == ['BG9U1', 'BG9V1', 'BG9R1']), str(_calls(_read(U))))
cb_r = next(c for c in bw_r.findChildren(QCheckBox)
            if c.text().startswith('自动保存到日志文件'))
cb_r.setChecked(False)
pump(3)
cb_r.setChecked(True)
pump(3)
_set_cell(tbl_r, col_r, 'o_call', 'BG9R2')
ok('U7 取消后又勾回来：改格子仍是就地更新（不产生重复记录）',
   wait_until(lambda: _calls(_read(U)) == ['BG9U1', 'BG9V1', 'BG9R2']),
   str(_calls(_read(U))))

# ==========================================================================
# V. 已同步的记录算已保存；没填完的列算未保存（关窗要问）
# ==========================================================================
print('--- V 未保存的判定 ---', flush=True)
V = os.path.join(TMP, 'v.fhla')
project.save_project_file(V, [])


def _open_v():
    w = QtWidgets.QMainWindow()
    project.main(w, _read(V), V)
    pump()
    b = QtWidgets.QMainWindow()
    batch_project.main(b, on_saved=w._perf_api['append_to_project'],
                       sync_io=w._perf_api['live_sync_io'](), auto_target_path=V)
    pump(3)
    return w, b


# 只填了一条完整的 → 已实时同步 → 直接关窗，不再问「是否保存」
win_v1, bw_v1 = _open_v()
_fill_col(bw_v1.findChild(QTableWidget), dict(FULL, o_call='BG9C1'))
ok('V1 填完整并同步', wait_until(lambda: _calls(_read(V)) == ['BG9C1']),
   str(_calls(_read(V))))
bw_v1.close()
pump(5)
ok('V2 全是已同步的记录 → 关窗直接关掉（不问是否保存）', not bw_v1.isVisible())

# 还有一列没填完（缺对方呼号）→ 关窗要被拦住，内容不能悄悄丢
win_v2, bw_v2 = _open_v()
tbl_v2 = bw_v2.findChild(QTableWidget)
_fill_col(tbl_v2, dict(FULL, o_call='BG9C2'))
ok('V3 第二条同步', wait_until(lambda: _calls(_read(V)) == ['BG9C1', 'BG9C2']),
   str(_calls(_read(V))))
_fill_col(tbl_v2, dict(FULL, o_call=''))
_time.sleep(0.6)
pump(5)
bw_v2.close()
pump(5)
ok('V4 有没填完的列 → 关窗被拦住（不静默丢内容）', bw_v2.isVisible())
ok('V5 没填完的列没有被写进日志', _calls(_read(V)) == ['BG9C1', 'BG9C2'],
   str(_calls(_read(V))))

# ==========================================================================
# 汇总
# ==========================================================================
print('', flush=True)
print('通过 %d/%d' % (sum(PASS), len(PASS)), flush=True)
sys.exit(0 if all(PASS) else 1)
