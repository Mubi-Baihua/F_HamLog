# -*- coding: utf-8 -*-
"""探针：抓启动器首帧图（确认留白/网格行距/底边距观感）。

用法：QT_QPA_PLATFORM=windows python __main_grab_probe.py [out.png]
"""
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from f_hamlog.paths import app_path  # noqa: E402
os.chdir(ROOT)

import f_hamlog.satellite_pred as sp   # noqa: E402

TMP = tempfile.mkdtemp(prefix='fhl_grab_')
for name, attr in (('m_xml.txt', 'SETTINGS_PATH'),
                   ('tle_sources.txt', 'TLE_SOURCES_PATH')):
    src = app_path('file/' + name)
    dst = os.path.join(TMP, name)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
    else:
        io.open(dst, 'w', encoding='utf-8').write('{}')
    setattr(sp, attr, dst)
try:
    s = eval(io.open(os.path.join(TMP, 'm_xml.txt'), encoding='utf-8').read())
    if not isinstance(s, dict):
        s = {}
except Exception:
    s = {}
s['language'] = 'zh'
io.open(os.path.join(TMP, 'm_xml.txt'), 'w', encoding='utf-8').write(str(s))

from PySide6.QtCore import QTimer                    # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

import f_hamlog.i18n as i18n      # noqa: E402
i18n.settings_path = lambda: os.path.join(TMP, 'm_xml.txt')
import f_hamlog.theme as theme    # noqa: E402
theme.settings_path = lambda: os.path.join(TMP, 'm_xml.txt')

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'tests', '__main_grab.png')

_orig_exec = QApplication.exec


def _patched_exec(self):
    def shot():
        from f_hamlog import main as m
        m.window.grab().save(OUT)
        print('saved', OUT)
        self.quit()
    QTimer.singleShot(350, shot)
    return _orig_exec()


QApplication.exec = _patched_exec

from f_hamlog import main as app_main   # noqa: E402
app_main.main()
