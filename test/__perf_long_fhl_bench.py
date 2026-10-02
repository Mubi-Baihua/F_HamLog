# -*- coding: utf-8 -*-
"""超长日志（默认 10000 条）性能基准：主表格构建 / 全选 / 反选 / 取消选择 / 读取勾选。

离屏运行，不触碰 file/ 下的用户数据：
- file/m_xml.txt 备份后还原（只读配置）
- save_path 指向临时文件，避免写真实数据
用法：
    python __perf_long_fhl_bench.py [N]
"""
import os
import sys
import time
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets

import backup
# 关键：把项目备份重定向到临时目录，绝不写用户的 file/project_backup.fhl
TMPDIR = tempfile.mkdtemp(prefix='fhl_perf_')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

import test as fhlgen
import project as pj

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000

SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
BAK = SETTINGS + '.perf_bak'
shutil.copyfile(SETTINGS, BAK)

TMP_FHL = os.path.join(TMPDIR, 'perf.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

records = fhlgen.generate_records(N)
print('records = %d' % len(records), flush=True)

t0 = time.perf_counter()
_win = QtWidgets.QMainWindow()
pj.main(_win, filee=records, save_path=TMP_FHL)
app.processEvents()
print('main() 含首次建表       : %.3f s' % (time.perf_counter() - t0), flush=True)

api = _win._perf_api
table = api['get_table']()
print('rows = %d, cols = %d' % (table.rowCount(), table.columnCount()), flush=True)


def timeit(label, fn, rounds=3):
    t = time.perf_counter()
    for _ in range(rounds):
        fn()
    dt = (time.perf_counter() - t) / rounds
    print('%-26s: %.4f s' % (label, dt), flush=True)
    return dt


timeit('table_update 重建', api['table_update'])
print('', flush=True)

timeit('全选 (10000 行)', lambda: api['set_all_rows_checked'](True))
timeit('反选 (10000 行)', api['invert_rows_checked'])
timeit('取消选择 (10000 行)', lambda: api['set_all_rows_checked'](False))
print('', flush=True)

api['set_all_rows_checked'](True)
timeit('读取勾选行(已全选)', api['get_selected_row_indexes'])
timeit('导出读取记录(已全选)', api['get_selected_records'])
api['set_all_rows_checked'](False)

print('done', flush=True)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
print('设置已还原', flush=True)
