# -*- coding: utf-8 -*-
"""校验：点「更多」保存（触发 table_update 重建）后，主表格滚动位置回到原处，而非弹回第 1 行。

离屏运行，不触碰 file/ 用户数据（项目备份与设置均重定向临时目录）。
用法：python __scroll_restore_smoke.py [N]
"""
import os
import sys
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets

import backup

N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
BAK = SETTINGS + '.sr_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_srestore_')
TMP_FHL = os.path.join(TMPDIR, 'perf.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 用固定「递增」日期时间造记录：list_time 按 (date,time) 排序后顺序保持不变，
# 从而能精确验证「重建后滚动偏移还原」这一行为本身。
records = []
for i in range(N):
    d = '2026-01-%02d' % (i // 24 + 1)
    h = i % 24
    records.append({
        'date': d if i // 24 + 1 <= 31 else '2026-02-01',
        'time': '%02d:00' % h,
        'm_call': 'BI8SQL', 'o_call': 'BG%05d' % (10000 + i),
        'freq': '144.0', 'freq_rx': '14.0', 'mode': 'LSB', 'prop_mode': 'E',
        'sat_name': '', 'm_rst': '59', 'o_rst': '59',
        'm_qth': '杭州', 'o_qth': '北京', 'm_dig': '', 'o_dig': '',
        'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '', 'notes': '',
    })

import project as pj

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def _cleanup():
    try:
        if os.path.exists(BAK):
            shutil.copyfile(BAK, SETTINGS)
            os.remove(BAK)
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)


import atexit
atexit.register(_cleanup)

win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.resize(1000, 500)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api
table = api['get_table']()

bar = table.verticalScrollBar()
ok('滚动条可滚动（数据量足够）', bar.maximum() > 0, f'max={bar.maximum()}')

# ---------- 滚到中间某处 ----------
target = bar.maximum() // 2
bar.setValue(target)
for _ in range(3):
    app.processEvents()
before = bar.value()
ok('已滚动到目标位置', before == target, f'{before}')

# ---------- 模拟「更多」保存：重建表格（persist=True 会触发 list_time + save）----------
api['table_update']()
for _ in range(6):          # 让 QTimer.singleShot(0) 的恢复回调执行
    app.processEvents()
table2 = api['get_table']()
bar2 = table2.verticalScrollBar()
after = bar2.value()
ok('重建后仍是同一个滚动位置（未弹回顶部）',
   after == before, f'{before} -> {after}')
ok('重建后不是第 1 行', after > 0, f'{after}')

# ---------- 顶部场景：在顶部重建仍留在顶部 ----------
bar2.setValue(0)
for _ in range(3):
    app.processEvents()
api['table_update']()
for _ in range(6):
    app.processEvents()
bar3 = api['get_table']().verticalScrollBar()
ok('原本在顶部时重建仍留在顶部', bar3.value() == 0, str(bar3.value()))

# ---------- 真实链路：滚到中段 → 打开「更多」→ 点「保存更改」→ 位置应还原 ----------
table3 = api['get_table']()
bar5 = table3.verticalScrollBar()
mid = bar5.maximum() * 2 // 3
bar5.setValue(mid)
for _ in range(3):
    app.processEvents()
pos_before = bar5.value()
ok('（真实链路）已滚到中段', pos_before == mid, f'{pos_before}/{bar5.maximum()}')

from PySide6.QtWidgets import QPushButton as _QPB
api['project_others'](10)      # 相当于点击第 10 行的「更多」
for _ in range(4):
    app.processEvents()
_others_win = pj.project_others_window
_save_btn = None
for b in _others_win.findChildren(_QPB):
    if b.text() == '保存更改':
        _save_btn = b
        break
ok('（真实链路）找到「保存更改」按钮', _save_btn is not None)
if _save_btn is not None:
    _save_btn.click()          # 触发 save_changes → table_update
    for _ in range(6):
        app.processEvents()
    bar6 = api['get_table']().verticalScrollBar()
    ok('（真实链路）保存后仍停在原滚动位置',
       bar6.value() == pos_before, f'{pos_before} -> {bar6.value()}')

# ---------- 新建日志：滚到顶部 → 追加记录 → 应跳到最下方 ----------
api['table_update'](scroll_to_bottom=False)   # 先回到某个中间位置
for _ in range(3):
    app.processEvents()
api['get_table']().verticalScrollBar().setValue(0)
for _ in range(3):
    app.processEvents()
ok('新建前处于顶部', api['get_table']().verticalScrollBar().value() == 0)

_n_before = api['get_table']().rowCount()
api['append_to_project']([{
    'date': '2026-09-28', 'time': '23:30', 'm_call': 'BI8SQL', 'o_call': 'BH1NEW',
    'freq': '145.0', 'freq_rx': '145.0', 'mode': 'FM', 'prop_mode': 'E',
    'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
    'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '', 'notes': '',
}])   # 等价于「批量记录 / 卫星记录」保存：追加到 file 后重建
for _ in range(6):
    app.processEvents()
_t_new = api['get_table']()
_bar_new = _t_new.verticalScrollBar()
ok('新建后行数 +1', _t_new.rowCount() == _n_before + 1, f'{_n_before} -> {_t_new.rowCount()}')
ok('新建日志后跳到最后一条',
   _bar_new.value() == _bar_new.maximum() and _bar_new.maximum() > 0,
   f'{_bar_new.value()} / {_bar_new.maximum()}')

# ---------- 真实「新建日志」窗口路径：点按钮新建 → 应跳到最下方 ----------
api['get_table']().verticalScrollBar().setValue(0)
for _ in range(3):
    app.processEvents()
_n2 = api['get_table']().rowCount()
api['new'](preset={'m_call': 'BI8SQL', 'o_call': 'BH9NEW', 'freq': '145.5', 'mode': 'FM'})
for _ in range(4):
    app.processEvents()
_new_win = pj.project_others_window
_new_btn = None
for b in _new_win.findChildren(_QPB):
    if b.text() == '新建日志':
        _new_btn = b
        break
ok('（新建窗口）找到「新建日志」按钮', _new_btn is not None)
if _new_btn is not None:
    _new_btn.click()          # 触发 save_changes → table_update(scroll_to_bottom=True)
    for _ in range(6):
        app.processEvents()
    _t2 = api['get_table']()
    _bar2b = _t2.verticalScrollBar()
    ok('（新建窗口）行数 +1', _t2.rowCount() == _n2 + 1, f'{_n2} -> {_t2.rowCount()}')
    ok('（新建窗口）新建后跳到最后一条',
       _bar2b.value() == _bar2b.maximum() and _bar2b.maximum() > 0,
       f'{_bar2b.value()} / {_bar2b.maximum()}')

# ---------- 首次打开式调用（scroll_to_bottom=True）仍应跳到底部 ----------
api['table_update'](scroll_to_bottom=True)
for _ in range(6):
    app.processEvents()
bar4 = api['get_table']().verticalScrollBar()
ok('scroll_to_bottom=True 仍跳到底部', bar4.value() == bar4.maximum(),
   f'{bar4.value()} / {bar4.maximum()}')

print('', flush=True)

print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)

_cleanup()
atexit.unregister(_cleanup)
sys.exit(0 if all(PASS) else 1)
