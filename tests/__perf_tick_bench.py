# -*- coding: utf-8 -*-
"""对照：判脏 / 定时器 / 保存（未变化）/ 编辑一行 的成本。

用法：python __perf_tick_bench.py [N]
用于优化前后的 A/B 对照（老版本没有 table_refresh_row 时会跳过该项）。
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets   # noqa: E402

from f_hamlog import backup     # noqa: E402

TMPDIR = tempfile.mkdtemp(prefix='fhl_tick_')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

from f_hamlog.paths import app_path          # noqa: E402
from f_hamlog import data_factory as fhlgen  # noqa: E402
from f_hamlog import project as pj           # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.tick_bak'
shutil.copyfile(SETTINGS, BAK)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
recs = fhlgen.generate_records(N)
win = QtWidgets.QMainWindow()
pj.main(win, filee=recs, save_path=os.path.join(TMPDIR, 'perf.fhl'))
app.processEvents()
api = win._perf_api


def timeit(label, fn, rounds=3):
    fn()
    t = time.perf_counter()
    for _ in range(rounds):
        fn()
    print('%-28s %.4f s' % (label, (time.perf_counter() - t) / rounds), flush=True)


print('N = %d' % N)
if '_bk_is_dirty' in api:
    timeit('_bk_is_dirty 判脏', api['_bk_is_dirty'])
if '_bk_tick' in api:
    timeit('_bk_tick 定时器一次', api['_bk_tick'])
timeit('save 未变化（跳过写盘）', lambda: api['save'](message=False))
if 'table_refresh_row' in api:
    timeit('table_refresh_row 一行', lambda: api['table_refresh_row'](N // 2))

# 记撤销点：新写法逐条浅拷贝，旧写法 deepcopy（编辑一条日志时的固定开销）
import copy   # noqa: E402

timeit('[dict(r)] 记撤销点（新）', lambda: [dict(r) for r in recs])
timeit('deepcopy 记撤销点（旧）', lambda: copy.deepcopy(recs), rounds=1)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
