# -*- coding: utf-8 -*-
"""探针：离屏跑 project.main() 期间，是否会尝试下载 / 改写真实 file/amateur.tle 与 m_xml.txt。

背景：一次 __delete_select_smoke.py 运行后，file/amateur.tle 与 file/m_xml.txt 被改写
（ISS 历元 26271→26274、sat_last_update 变为运行时刻），需要确认是不是 pj.main() 的副作用。
做法：把卫星路径常量重定向到临时目录 + 拦截 urllib.request.urlopen，
      再比对真实文件的 mtime/字节是否变化。
不改动任何真实数据文件。
用法：python test/__tle_write_probe.py
"""
import os
import sys
import time
import shutil
import tempfile
import hashlib
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from f_hamlog.paths import app_path  # noqa: E402
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.exit = lambda *a, **k: None

REAL_TLE = app_path('file/amateur.tle'))
REAL_SET = app_path('file/m_xml.txt'))


def md5(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()[:10]
    except OSError:
        return '(missing)'


TLE_BEFORE, SET_BEFORE = md5(REAL_TLE), md5(REAL_SET)

TMP = tempfile.mkdtemp(prefix='fhl_tleprobe_')

# ---- 拦截一切下载尝试（在 import project 之前）----
import urllib.request
URLS = []
_orig_urlopen = urllib.request.urlopen


def _spy(req, *a, **k):
    URLS.append(getattr(req, 'full_url', str(req)))
    raise RuntimeError('probe-blocked')


urllib.request.urlopen = _spy

# ---- 卫星相关路径常量重定向到临时目录 ----
from f_hamlog import satellite_pred as sp
sp.TLE_CACHE = os.path.join(TMP, 'amateur.tle')
sp.SETTINGS_PATH = os.path.join(TMP, 'm_xml.txt')
sp.TLE_SOURCES_PATH = os.path.join(TMP, 'tle_sources.txt')
shutil.copyfile(REAL_SET, sp.SETTINGS_PATH)
shutil.copyfile(app_path('file/tle_sources.txt')), sp.TLE_SOURCES_PATH)

from f_hamlog import backup
backup.PROJECT_BACKUP = os.path.join(TMP, 'pb.fhl')

from PySide6 import QtWidgets

from f_hamlog import data_factory as fhlgen
records = [fhlgen.make_record(i) for i in range(5)]

THREADS0 = threading.active_count()
TMP_FHL = os.path.join(TMP, 'probe.fhl')

from f_hamlog import project as pj

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
win = QtWidgets.QMainWindow()
T0 = time.time()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
while time.time() - T0 < 8.0:      # 给任何后台线程一点时间动作
    app.processEvents()
    time.sleep(0.05)

print('--- 结果 ---')
print('urlopen 下载尝试次数:', len(URLS))
for u in URLS[:6]:
    print('   ', u)
print('活跃线程数变化:', threading.active_count() - THREADS0)
print('satellite_auto_update 是否被导入:', 'satellite_auto_update' in sys.modules)
print('satellite_window 是否被导入:', 'satellite_window' in sys.modules)
print('真实 amateur.tle  md5:', TLE_BEFORE, '->', md5(REAL_TLE),
      '变化' if TLE_BEFORE != md5(REAL_TLE) else '未变')
print('真实 m_xml.txt    md5:', SET_BEFORE, '->', md5(REAL_SET),
      '变化' if SET_BEFORE != md5(REAL_SET) else '未变')
print('临时目录产物:', sorted(os.listdir(TMP)))

shutil.rmtree(TMP, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
