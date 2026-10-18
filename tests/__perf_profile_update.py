# -*- coding: utf-8 -*-
"""剖析：主表格重建（table_update）的时间都花在哪。

用法：python __perf_profile_update.py [N]
"""
import cProfile
import os
import pstats
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets   # noqa: E402

from f_hamlog import backup     # noqa: E402

TMPDIR = tempfile.mkdtemp(prefix='fhl_prof_')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

from f_hamlog.paths import app_path          # noqa: E402
from f_hamlog import data_factory as fhlgen  # noqa: E402
from f_hamlog import project as pj           # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000

SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.prof_bak'
shutil.copyfile(SETTINGS, BAK)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
records = fhlgen.generate_records(N)
win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=os.path.join(TMPDIR, 'perf.fhl'))
app.processEvents()

api = win._perf_api
api['table_update']()          # 先热一次

pr = cProfile.Profile()
pr.enable()
for _ in range(3):
    api['table_update']()
pr.disable()

st = pstats.Stats(pr)
st.sort_stats('cumulative')
st.print_stats(28)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
