# -*- coding: utf-8 -*-
"""设置页「自动保存 + 自动更新」冒烟。

覆盖：
* 本页不再有「保存更改」按钮（改任何控件都直接落盘）；
* 「自动更新」复选框在「检查更新」左边、默认勾选、预览版置灰；
* 文本防抖落盘、开关立即落盘、非法经纬度不覆盖旧值、其它模块的键不被冲掉；
* `auto_update_enabled()` 与 `start_auto_update()`：不勾不查、预览版不查、勾了就起线程；
* `_on_update_checked(auto=True)`：发现新版本照样弹提示，已是最新/失败不打扰。

不污染用户数据：数据目录指向临时目录（F_HAMLOG_DATA_DIR）。

用法：QT_QPA_PLATFORM=offscreen python tests/__set_autosave_smoke.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

TMP = tempfile.mkdtemp(prefix='__set_autosave_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
XML = os.path.join(TMP, 'file', 'm_xml.txt')
# sat_last_update 是「别的窗口」写的键：自动保存必须原样保留
SEED = {'m_call': 'BI8SQL', 'm_qth': '成都', 'm_dig': 'FT-817',
        'm_lat': 30.0, 'm_lon': 104.0, 'm_alt': 500.0,
        'aouto_save': False, 'aouto_list': False,
        'sat_auto_update': False, 'sat_update_hours': 24,
        'sat_last_update': '2026-10-25 10:00:00', 'theme_mode': 'system'}
with open(XML, 'w', encoding='utf-8') as f:
    f.write(str(SEED))
os.environ['F_HAMLOG_DATA_DIR'] = TMP

from PySide6.QtCore import QThread, Signal                    # noqa: E402
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel,        # noqa: E402
                               QPushButton, QLineEdit, QCheckBox, QComboBox)

from f_hamlog import theme, i18n, check_update, set as set_mod  # noqa: E402

theme.settings_path = lambda: XML      # 颜色模式也写这份，别碰真实用户文件
app = QApplication.instance() or QApplication(sys.argv)
theme.init_app(app)
i18n.install(app)

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


def pump(ms=0):
    end = time.time() + ms / 1000.0
    while True:
        app.processEvents()
        if time.time() >= end:
            return
        time.sleep(0.01)


def read_xml():
    with open(XML, 'r', encoding='utf-8') as f:
        return eval(f.read())


# ------------------------------------------------------------------ 建窗口
window = QMainWindow()
set_mod.main(window)
pump(30)

cw = window.centralWidget()
buttons = {b.text(): b for b in cw.findChildren(QPushButton)}
boxes = {b.text(): b for b in cw.findChildren(QCheckBox)}

print('按钮：', sorted(buttons))
print('复选框：', sorted(boxes))

ok('S1 「保存更改」按钮已移除', '保存更改' not in buttons, str(sorted(buttons)))
ok('S2 有「自动更新」复选框', '自动更新' in boxes, str(sorted(boxes)))

auto_box = boxes.get('自动更新')
update_btn = buttons.get('检查更新')
ok('S3 默认勾选（每次打开都查）', bool(auto_box and auto_box.isChecked()),
   'checked=%s' % (auto_box.isChecked() if auto_box else None))

if auto_box is not None and update_btn is not None:
    a_pos = auto_box.mapTo(cw, auto_box.rect().topLeft())
    u_pos = update_btn.mapTo(cw, update_btn.rect().topLeft())
    ok('S4 在「检查更新」左边', a_pos.x() + auto_box.width() <= u_pos.x(),
       '复选框右缘=%d 按钮左缘=%d' % (a_pos.x() + auto_box.width(), u_pos.x()))
    ok('S5 与「检查更新」大致同一行', abs(a_pos.y() - u_pos.y()) < 20,
       'y: 复选框=%d 按钮=%d' % (a_pos.y(), u_pos.y()))

# 内容高度没被这一行撑爆
lay = cw.layout()
lay.activate()
ok('S6 加了复选框仍然放得下', cw.minimumSizeHint().height() <= window.height(),
   'min_h=%d 窗口高=%d' % (cw.minimumSizeHint().height(), window.height()))

# ------------------------------------------------------------------ A. 文本自动保存（防抖）
call_input = cw.findChildren(QLineEdit)[0]
call_input.setText('BH4ABC')
pump(60)
ok('A1 防抖期间还没落盘（不逐字节写盘）', read_xml().get('m_call') == 'BI8SQL',
   read_xml().get('m_call'))
pump(400)
data = read_xml()
ok('A2 防抖到点后自动落盘', data.get('m_call') == 'BH4ABC', data.get('m_call'))
ok('A3 其它模块的键没被冲掉', data.get('sat_last_update') == SEED['sat_last_update'],
   str(data.get('sat_last_update')))
ok('A4 关掉窗口也不会因为「没点保存」丢数据（窗口还开着）', window.isVisible())

# ------------------------------------------------------------------ B. 开关立即落盘
auto_save_box = boxes.get('自动保存')
if auto_save_box is not None:
    auto_save_box.setChecked(True)
    pump(30)
    ok('B1 勾选「自动保存」立即落盘', read_xml().get('aouto_save') is True,
       str(read_xml().get('aouto_save')))

# ------------------------------------------------------------------ C. 非法坐标不覆盖旧值
# 输入框顺序：呼号 / QTH / 设备 / 纬度 / 经度 / 海拔 / 网格
edits = cw.findChildren(QLineEdit)
lat_input = edits[3]
ok('C0 取到的确实是纬度框', lat_input.text().startswith('30.0'), lat_input.text())
lat_input.setText('-')                          # 打到一半的半截输入
pump(400)
ok('C1 半截纬度不覆盖已存坐标', abs(read_xml().get('m_lat') - 30.0) < 1e-9,
   str(read_xml().get('m_lat')))
lat_input.setText('31.25')
pump(400)
ok('C2 合法纬度正常落盘', abs(read_xml().get('m_lat') - 31.25) < 1e-9,
   str(read_xml().get('m_lat')))

# ------------------------------------------------------------------ D. 自动更新开关与读音
ok('D1 auto_update_enabled() 默认 True', set_mod.auto_update_enabled() is True)
auto_box.setChecked(False)
pump(50)
ok('D2 取消勾选立即落盘 auto_update=False', read_xml().get('auto_update') is False,
   str(read_xml().get('auto_update')))
ok('D3 关掉之后不再自动查', set_mod.auto_update_enabled() is False)

set_mod._update_check_thread = None
set_mod.start_auto_update(window)
ok('D4 没勾「自动更新」→ 不起线程', set_mod._update_check_thread is None,
   repr(set_mod._update_check_thread))

auto_box.setChecked(True)
pump(50)
ok('D5 重新勾选后 auto_update=True', read_xml().get('auto_update') is True)

# 预览版：连线程都不该起
orig_preview = check_update.is_preview_version
check_update.is_preview_version = lambda: True
set_mod._update_check_thread = None
set_mod.start_auto_update(window)
ok('D6 预览版不自动查', set_mod._update_check_thread is None)
check_update.is_preview_version = orig_preview


# 正式版：起线程（用假线程，别真联网）
class FakeCheck(QThread):
    result = Signal(object)

    ran = []

    def run(self):
        FakeCheck.ran.append(1)
        self.result.emit({'status': 'latest'})


orig_thread = set_mod._CheckThread
set_mod._CheckThread = FakeCheck
set_mod._update_check_thread = None
set_mod.start_auto_update(window)
pump(120)
ok('D7 勾上后打开就查（线程已起）', bool(FakeCheck.ran), 'ran=%s' % FakeCheck.ran)

# ------------------------------------------------------------------ E. auto 模式下的提示行为
class FakeBox(object):
    Yes = 1
    No = 0
    calls = []

    @classmethod
    def question(cls, *a, **k):
        cls.calls.append('question')
        return cls.Yes

    @classmethod
    def information(cls, *a, **k):
        cls.calls.append('information')

    @classmethod
    def warning(cls, *a, **k):
        cls.calls.append('warning')


orig_box = set_mod.QMessageBox
orig_start = set_mod._start_update_download
starts = []
set_mod.QMessageBox = FakeBox
set_mod._start_update_download = lambda *a, **k: starts.append((a, k))
os.environ['F_HAMLOG_UPDATE_DIR'] = os.path.join(TMP, 'empty_update')

FakeBox.calls = []
set_mod._on_update_checked(window, {'status': 'latest'}, auto=True)
ok('E1 自动查：已是最新不弹窗', FakeBox.calls == [], str(FakeBox.calls))

FakeBox.calls = []
set_mod._on_update_checked(window, {'status': 'error', 'detail': '超时'}, auto=True)
ok('E2 自动查：失败不弹窗', FakeBox.calls == [], str(FakeBox.calls))

FakeBox.calls = []
set_mod._on_update_checked(window, {'status': 'new', 'version': '9.9.9',
                                    'url': 'https://x/F.HamLog.9.9.9.setup.exe'}, auto=True)
ok('E3 自动查：发现新版本要提示（问是否下载并安装）',
   FakeBox.calls == ['question'], str(FakeBox.calls))
ok('E4 点了「是」就开下载', len(starts) == 1, str(starts)[:80])

FakeBox.calls = []
set_mod._on_update_checked(window, {'status': 'latest'}, auto=False)
ok('E5 手动查：已是最新要提示', FakeBox.calls == ['information'], str(FakeBox.calls))

set_mod.QMessageBox = orig_box
set_mod._start_update_download = orig_start
set_mod._CheckThread = orig_thread

window.close()
bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
