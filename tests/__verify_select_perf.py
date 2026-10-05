# -*- coding: utf-8 -*-
import os, sys, time
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, D)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
os.chdir(D)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtWidgets
from f_hamlog.paths import app_path
from f_hamlog import satellite_window as sw

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
lines = open(app_path('file/amateur.tle')), encoding='utf-8-sig', errors='replace').read().splitlines()
names = [ln.strip() for ln in lines if ln.strip() and not ln.startswith('1 ') and not ln.startswith('2 ')]
print('TLE names:', len(names), flush=True)
for n in (500, 1000, 2000, 4000):
    nm = names[:n]
    t0 = time.perf_counter()
    dlg = sw.SatelliteSelectDialog(None, nm, set())
    t1 = time.perf_counter()
    t2 = time.perf_counter()
    dlg._select_all()
    t3 = time.perf_counter()
    t4 = time.perf_counter()
    dlg._select_none()
    t5 = time.perf_counter()
    print('n=%-6d build=%.3f all=%.3f none=%.3f' % (len(nm), t1 - t0, t3 - t2, t5 - t4), flush=True)
    dlg.close()
print('done', flush=True)
