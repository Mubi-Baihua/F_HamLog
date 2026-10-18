# -*- coding: utf-8 -*-
"""剖析：打开一个 1 万条项目时 main() 的时间分布（找开表之外的隐藏大头）。

用法：python __perf_profile_open.py [N]
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

TMPDIR = tempfile.mkdtemp(prefix='fhl_profopen_')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

from f_hamlog.paths import app_path          # noqa: E402
from f_hamlog import data_factory as fhlgen  # noqa: E402
from f_hamlog import project as pj           # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
SETTINGS = app_path('file/m_xml.txt')
BAK = SETTINGS + '.profopen_bak'
shutil.copyfile(SETTINGS, BAK)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
recs = fhlgen.generate_records(N)

pr = cProfile.Profile()
pr.enable()
win = QtWidgets.QMainWindow()
pj.main(win, filee=recs, save_path=os.path.join(TMPDIR, 'open.fhl'))
app.processEvents()
pr.disable()

st = pstats.Stats(pr)
st.sort_stats('cumulative')
st.print_stats(22)

shutil.copyfile(BAK, SETTINGS)
os.remove(BAK)
shutil.rmtree(TMPDIR, ignore_errors=True)
