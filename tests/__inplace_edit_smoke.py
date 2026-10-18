# -*- coding: utf-8 -*-
"""大项目性能改造的功能回归（离屏，不触碰 file/ 用户数据）。

本轮改动的三条：
1. 「更多信息 → 保存更改」只改一条记录的普通字段时**就地刷新一行**，不再重建整表
   （断言：表格对象还是同一个 = 没有重建；其它行文字一字不变）。
2. 「删除日志」少量删除走 removeRow（就地删），行数与顺序正确、勾选不错位
   —— 由 __delete_select_smoke.py 覆盖。
3. 内容比较从 JSON 字符串换成值快照（脏标记 / 保存跳过 / .fhla 是否算编辑），
   语义必须与旧版一致：编辑后判脏、保存后干净、撤销后又能判脏。

另外守一条硬约束：**文件格式一个字都不改**（.fhl 仍是 list[dict]，
字段集合与写盘前后完全一致）。

用法：python __inplace_edit_smoke.py
"""
import io
import json
import os
import shutil
import sys
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# 槽函数里的 sys.exit() 从 PySide6 C++ 边界直接终止进程，测试前屏蔽
sys.exit = lambda *a, **k: None

from PySide6 import QtWidgets   # noqa: E402

from f_hamlog import backup                # noqa: E402
from f_hamlog.paths import app_path        # noqa: E402
from f_hamlog import data_factory as fhlgen  # noqa: E402

N = 40
SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.inplace_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_inplace_')
TMP_FHL = os.path.join(TMPDIR, 'inplace.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


def mk(i):
    rec = fhlgen.make_record(i)
    rec['o_call'] = f'C{i:03d}'
    rec['notes'] = f'生成日志 {i + 1}'
    return rec


records = [mk(i) for i in range(N)]

from f_hamlog import project as pj     # noqa: E402
from f_hamlog import fhl_rw            # noqa: E402

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''),
          flush=True)


def _cleanup():
    try:
        if os.path.exists(BAK):
            shutil.copyfile(BAK, SETTINGS)
            os.remove(BAK)
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)


import atexit   # noqa: E402
atexit.register(_cleanup)

# 悬浮通知改成记录调用，避免离屏环境下建窗口
TOASTS = []
pj.toast_tip.show_toast = lambda text, parent=None, timeout=1000, kind='info': TOASTS.append(text)

win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api
table = api['get_table']()

entries = api['field_entries']()
VISIBLE = [k for (k, _lb, _req, main, _isc) in entries if main]


def col_of(key):
    """主表里某字段所在的列号（第 0 列是「选择」；列序 = 主页显示字段的顺序）。"""
    return 1 + VISIBLE.index(key)


def cells(tbl, key):
    c = col_of(key)
    return [tbl.item(r, c).text() for r in range(tbl.rowCount())]


def open_more(row):
    api['project_others'](row)
    for _ in range(3):
        app.processEvents()
    for w in app.topLevelWidgets():
        if w.windowTitle() == '更多信息':
            return w
    return None


def set_more_field(dlg, key, text):
    row = [k for (k, *_rest) in entries].index(key)
    tbl = dlg.findChildren(QtWidgets.QTableWidget)[0]
    tbl.item(row, 1).setText(text)


def click(dlg, label):
    for b in dlg.findChildren(QtWidgets.QPushButton):
        if b.text() == label:
            b.click()
            for _ in range(3):
                app.processEvents()
            return True
    return False


# ---------- 1. 改普通字段 → 就地刷新（不重建表格） ----------
before_calls = cells(table, 'o_call')
# 另挑一个「主页显示」的普通字段，用来断言其它列没受影响
other_key = [k for k in VISIBLE if k not in ('o_call', 'date', 'time')][0]
before_other = cells(table, other_key)
target = before_calls.index('C010')
same_table = id(table)

dlg = open_more(target)
ok('「更多」窗已打开', dlg is not None)
set_more_field(dlg, 'o_call', 'BG9XYZ')
click(dlg, '保存更改')

table = api['get_table']()
ok('改普通字段后未重建表格（同一对象）', id(table) == same_table, str(id(table) == same_table))
ok('行数不变', table.rowCount() == N, str(table.rowCount()))
ok('目标行的新值已就地刷新', cells(table, 'o_call')[target] == 'BG9XYZ',
   cells(table, 'o_call')[target])
ok('其它行文字一字不变',
   [c for i, c in enumerate(cells(table, 'o_call')) if i != target]
   == [c for i, c in enumerate(before_calls) if i != target])
ok('其它列不受影响', cells(table, other_key) == before_other,
   other_key)

row_rec = None
for r in range(table.rowCount()):
    if cells(table, 'o_call')[r] == 'BG9XYZ':
        row_rec = r
# 判脏语义与旧版一致：「自动保存」开着时，就地刷新后已经落盘 → 基线复位 → 不脏；
# 关着时才该带 *。两种都验，避免把「值快照替代 JSON 比较」改成另一种语义。
try:
    _s = eval(io.open(SETTINGS, encoding='utf-8').read())
    AUTO_SAVE = bool(_s.get('aouto_save'))
except Exception:
    AUTO_SAVE = False
ok('判脏状态与「自动保存」开关一致', api['_bk_is_dirty']() == (not AUTO_SAVE),
   f'auto_save={AUTO_SAVE} dirty={api["_bk_is_dirty"]()}')
if AUTO_SAVE:
    _disk, _k = fhl_rw.read_fhl_file(TMP_FHL)
    ok('自动保存已把就地修改的这条落盘',
       any(r.get('o_call') == 'BG9XYZ' for r in _disk),
       str([r.get('o_call') for r in _disk[:6]]))

# ---------- 2. 撤销 / 重做（浅拷贝快照不得被污染） ----------
api['undo']()
table = api['get_table']()
ok('撤销后目标行恢复旧呼号', cells(table, 'o_call')[row_rec] == 'C010',
   cells(table, 'o_call')[row_rec])
ok('撤销后其它行不变', cells(table, 'o_call') == before_calls)
api['redo']()
table = api['get_table']()
ok('重做后又是新呼号', cells(table, 'o_call')[row_rec] == 'BG9XYZ',
   cells(table, 'o_call')[row_rec])

# ---------- 3. 改日期（排序键变化）→ 必须重建并重排 ----------
table = api['get_table']()
old_table = id(table)
first_date = cells(table, 'date')[0]
target2 = 5
dlg = open_more(target2)
set_more_field(dlg, 'date', '1990-01-01')
set_more_field(dlg, 'time', '00:00')
click(dlg, '保存更改')
table = api['get_table']()
ok('改日期后走重建（表格已是新对象）', id(table) != old_table, str(id(table) != old_table))
ok('重建后行数不变', table.rowCount() == N, str(table.rowCount()))
ok('改日期的记录被排到最前面', cells(table, 'date')[0] == '1990-01-01',
   cells(table, 'date')[:3])
ok('原来第一行的日期出现在其后', cells(table, 'date')[1] == first_date,
   cells(table, 'date')[:3])

# ---------- 4. 落盘：内容一致、格式未变 ----------
api['save'](message=True)
disk, key2 = fhl_rw.read_fhl_file(TMP_FHL)
ok('落盘成功（.fhl 可读回）', isinstance(disk, list) and len(disk) == N,
   str(type(disk)))
ok('落盘记录数正确', len(disk) == N, str(len(disk)))
keys_now = set(disk[0].keys())
keys_orig = set(records[0].keys())
ok('.fhl 仍是 list[dict]', all(isinstance(r, dict) for r in disk))
ok('字段集合与改动前一致', keys_now == keys_orig, str(sorted(keys_now - keys_orig)))
ok('保存后不再判脏', api['_bk_is_dirty']() is False)

# 磁盘上确实是纯记录列表（顶层不是 {"xml":..,"project":..}）
with open(TMP_FHL, 'r', encoding='utf-8') as f:
    raw = json.load(f)
ok('文件顶层仍是记录数组（未引入新结构）',
   isinstance(raw, list) and isinstance(raw[0], dict), str(type(raw)))

# ---------- 5. 恢复项目：哨兵值仍让状态恒为「未保存」 ----------
# 基线从 JSON 字符串 '' 换成了 None，语义必须保持不变（关闭时要提示保存）。
win2 = QtWidgets.QMainWindow()
pj.main(win2, filee=[mk(i) for i in range(3)], recovered=True)
for _ in range(3):
    app.processEvents()
ok('恢复项目仍恒判脏（关闭会提示保存）',
   win2._perf_api['_bk_is_dirty']() is True)

print()
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)
_cleanup()
os._exit(0 if all(PASS) else 1)
