# -*- coding: utf-8 -*-
"""冒烟：启动器（main.py 主界面）show() 之后**不允许**再发生实际几何变化。

判据
----
把 `QMainWindow.show()` 包一层：show() 一返回就记录中央控件里每个子控件的
geometry，300ms 后再比一次。**只要有任何控件位置/尺寸变了就判失败**——
那正是用户看到的「打开主界面时内容上下跳一下」。

为什么必须用真实平台跑
----------------------
离屏（offscreen）字体度量更小，整列内容不会超高，问题复现不出来。
所以本脚本默认跑真实 Windows 平台；验证命令：

    QT_QPA_PLATFORM=windows .venv/Scripts/python.exe tests/__main_layout_settle_smoke.py

背景（2026-10-18 修的那次）
--------------------------
① 主布局竖向内容约 390px、窗口固定 375px，而副标题下的 `addSpacing(50)` 不可压缩，
   多出来的高度只能从两列网格里挤（行距被压成 3~4px），且挤压发生在 show() 之后
   （QSS 抛光会让布局重算）→ 第一帧和最终帧不同。改为可压缩留白吸收溢出。
② `_style_btn(primary=True)` 里的 `setMinimumHeight(40)` 把主按钮的「固定 46」
   改成「40~46」，两遍排布取了不同高度 → 主按钮上下跳 6px。该行已删。
"""
import io
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from f_hamlog.paths import app_path  # noqa: E402
os.chdir(ROOT)

import f_hamlog.satellite_pred as sp   # noqa: E402

TMP = tempfile.mkdtemp(prefix='fhl_settle_')
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
s['language'] = sys.argv[1] if len(sys.argv) > 1 else 'zh'
io.open(os.path.join(TMP, 'm_xml.txt'), 'w', encoding='utf-8').write(str(s))

from PySide6.QtCore import QTimer                       # noqa: E402
from PySide6.QtWidgets import (QApplication, QMainWindow,  # noqa: E402
                               QWidget)

import f_hamlog.i18n as i18n      # noqa: E402
i18n.settings_path = lambda: os.path.join(TMP, 'm_xml.txt')
import f_hamlog.theme as theme    # noqa: E402
theme.settings_path = lambda: os.path.join(TMP, 'm_xml.txt')

FAILS = []
SNAP = {}


def _snapshot(win):
    """{控件描述: geometry}，键用 类名+序号+文字，避免 hash 不稳。"""
    cw = win.centralWidget()
    out = {}
    for i, w in enumerate(cw.findChildren(QWidget)):
        geo = w.geometry()
        try:
            txt = w.text()
        except Exception:
            txt = ''
        out['%s#%d:%r' % (w.__class__.__name__, i, str(txt)[:10])] = (
            geo.x(), geo.y(), geo.width(), geo.height())
    return out


_orig_show = QMainWindow.show


def _patched_show(self):
    _orig_show(self)
    if not SNAP:            # 只记第一个窗口（启动器）的首帧几何
        SNAP.update(_snapshot(self))


QMainWindow.show = _patched_show

_orig_exec = QApplication.exec


def _patched_exec(self):
    def check():
        from f_hamlog import main as m
        after = _snapshot(m.window)
        for k in sorted(set(SNAP) | set(after)):
            a, b = SNAP.get(k), after.get(k)
            if a != b:
                FAILS.append('%s  show() 时 %s → 300ms 后 %s' % (k, a, b))
        self.quit()

    QTimer.singleShot(300, check)
    return _orig_exec()


QApplication.exec = _patched_exec

from f_hamlog import main as app_main   # noqa: E402
app_main.main()

print('-- 启动器 show() 后几何变化 --')
for line in FAILS:
    print('  ' + line)
print('结果: %s（采集 %d 个控件）' % ('PASS' if not FAILS else 'FAIL', len(SNAP)))
sys.exit(1 if FAILS else 0)
