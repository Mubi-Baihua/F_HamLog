# -*- coding: utf-8 -*-
"""更新流程整体冒烟（界面链路）：检查 → 多线程下载 → 进入安装分支。

真下载（本地 Range 服务），只把「最后运行安装包」这一步换成记录，
避免真的启动安装器 / 关掉程序。

用法：QT_QPA_PLATFORM=offscreen python tests/__update_flow_smoke.py
"""
import hashlib
import os
import random
import re
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

TMP = tempfile.mkdtemp(prefix='__upd_flow_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
with open(os.path.join(TMP, 'file', 'm_xml.txt'), 'w', encoding='utf-8') as f:
    f.write(str({'m_call': 'BI8SQL', 'm_lat': 30.0, 'm_lon': 104.0}))
os.environ['F_HAMLOG_DATA_DIR'] = TMP

PAYLOAD = bytes(random.Random(7).getrandbits(8) for _ in range(8 << 20))

from f_hamlog import check_update as cu, set as set_mod       # noqa: E402
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                               QMessageBox, QProgressDialog)  # noqa: E402

# 缓存目录挪进临时目录：否则会读到上一轮（或真实用户目录里）已下载的包，
# 一上来就命中缓存，整个下载链路一个请求都不发。
UPDATE_DIR = os.path.join(TMP, 'update')
os.environ[cu.CACHE_DIR_ENV] = UPDATE_DIR
cu.legacy_dirs = lambda: []

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _write(self, body):
        # 故意每 32 KB 停顿 120 ms：本地回环一秒就能下完 8 MB，进度回调太少
        # 就测不到速度与剩余时间（EtaEstimator 有 1 秒预热期，太快会一直不显示）。
        for i in range(0, len(body), 32 << 10):
            self.wfile.write(body[i:i + (32 << 10)])
            time.sleep(0.12)

    def do_GET(self):
        rng = self.headers.get('Range')
        try:
            if rng:
                start, end = rng.split('=')[1].split('-')
                start = int(start)
                end = int(end) if end else len(PAYLOAD) - 1
                body = PAYLOAD[start:end + 1]
                self.send_response(206)
                self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, len(PAYLOAD)))
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self._write(body)
            else:
                self.send_response(200)
                self.send_header('Content-Length', str(len(PAYLOAD)))
                self.end_headers()
                self._write(PAYLOAD)
        except (BrokenPipeError, ConnectionResetError):
            pass


srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/F%%20HamLog%%202.9%%20setup.exe' % srv.server_address[1]

app = QApplication.instance() or QApplication(sys.argv)

# 不弹任何模态框：一律「是」，提示类直接吞掉
asked = []
set_mod.QMessageBox.question = staticmethod(
    lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ''), QMessageBox.Yes)[1])
set_mod.QMessageBox.information = staticmethod(lambda *a, **k: None)
set_mod.QMessageBox.warning = staticmethod(lambda *a, **k: None)

# 只替换「拿到版本信息」这一步，下载走真实代码
cu.check = lambda: {'status': 'new', 'version': '2.9.0', 'url': URL, 'detail': ''}
installed = []
set_mod._install_update = lambda window, path, version, confirm=True: installed.append(
    (path, version, confirm))

window = QMainWindow()
button = QPushButton('检查更新', window)
button.show()
window.show()

t0 = time.time()
set_mod._start_update_check(window, button)
ok('F0 检查期间按钮变灰', not button.isEnabled(), button.text())
# 等后台查版本线程回来（check() 是异步的，立刻断言会读到「检查中…」）
while button.text() != '检查更新' and time.time() - t0 < 10:
    app.processEvents()
    time.sleep(0.02)
ok('F1 检查后按钮已恢复可用', button.isEnabled() and button.text() == '检查更新', button.text())
ok('F2 询问过是否下载', any('是否下载并安装' in a for a in asked), str(asked)[:80])

labels = []
widths = []
while not installed and time.time() - t0 < 30:
    app.processEvents()
    for w in app.topLevelWidgets():      # 边下边采进度窗文案
        if isinstance(w, QProgressDialog) and w.isVisible():
            widths.append(w.width())
            label = w.labelText()
            if label and (not labels or labels[-1] != label):
                labels.append(label)
    time.sleep(0.02)


def segments():
    """截出文案里「已下载/总大小 · 速度 · 剩余 xx:xx」的第二段（速度）。"""
    out = []
    for s in labels:
        parts = [p.strip() for p in s.split(' · ')]
        if len(parts) >= 2:
            out.append(parts[1])
    return out


def etas():
    """截出文案里的剩余时间（秒）；没有这一段就跳过。"""
    out = []
    for s in labels:
        m = re.search(r'剩余 (\d{2}):(\d{2})(?::(\d{2}))?', s)
        if not m:
            continue
        a, b, c = m.groups()
        out.append(int(a) * 3600 + int(b) * 60 + int(c or 0) if c else int(a) * 60 + int(b))
    return out


def etajump(seq):
    return max((abs(b - a) for a, b in zip(seq, seq[1:])), default=0)


ok('F3 下载完成并进入安装分支', bool(installed), str(installed))
ok('F3a 采到进度文案', len(labels) >= 2, '%d 条，最后一条：%s' % (
    len(labels), labels[-1] if labels else '（无）'))
ok('F3b 文案带已下载/总大小', any('/' in s and 'MB' in s for s in labels),
   labels[-1] if labels else '')
ok('F3c 文案带速度', any('/s' in s or '—' in s for s in labels),
   '；'.join(labels[-3:]))
ok('F3d 速度有非零值', any(v.endswith('/s') and not v.startswith('0 ') for v in segments()),
   str(segments()[-3:]))
ok('F3e 进度窗宽度 480 左右', bool(widths) and min(widths) >= 470 and max(widths) <= 560,
   '%d 次采样，%s~%s' % (len(widths), min(widths) if widths else 0,
                        max(widths) if widths else 0))
ok('F3f 文案带剩余时间', len(etas()) >= 3, str(etas()[-5:]))
ok('F3g 剩余时间不跳变', etajump(etas()) <= 3,
   '最大跳变 %d 秒，序列尾部 %s' % (etajump(etas()), str(etas()[-6:])))

if installed:
    path, version = installed[0][0], installed[0][1]
    blob = open(path, 'rb').read()
    ok('F4 下载内容一致', hashlib.sha256(blob).hexdigest() == hashlib.sha256(PAYLOAD).hexdigest(),
       '%d 字节' % len(blob))
    ok('F5 版本号透传正确', version == '2.9.0', version)
    ok('F6 落在更新缓存目录', os.path.dirname(os.path.abspath(path)) == os.path.abspath(UPDATE_DIR),
       path)
    ok('F6b 下载后留下元数据', os.path.exists(path + '.json'), path + '.json')
ok('F7 下载线程已结束', set_mod._update_download_thread is None
   or not set_mod._update_download_thread.isRunning())

# ------------------------------------------------- H. 已有下载好的包 → 不再重下
# 回归：用户上次选了「稍后」/ 装到一半取消，这次点检查更新不该再白下几十 MB。
installed.clear()
asked.clear()
cached_hit = []
thread_before = set_mod._update_download_thread      # F 段那个（已结束）线程对象
set_mod._ask_cached = lambda window, version, found: (
    cached_hit.append((version, found)), 'install')[1]
set_mod._start_update_check(window, button)
t4 = time.time()
while not installed and time.time() - t4 < 10:
    app.processEvents()
    time.sleep(0.02)
ok('H1 走了「本地已有安装包」分支', bool(cached_hit), str(cached_hit)[:80])
ok('H2 没再弹下载询问', not any('是否下载并安装' in a for a in asked), str(asked)[:60])
ok('H3 直接进安装分支', bool(installed), str(installed)[:80])
ok('H4 没启动新的下载线程', set_mod._update_download_thread is thread_before,
   '线程对象%s' % ('没变' if set_mod._update_download_thread is thread_before else '被换掉了'))
if cached_hit and installed:
    found_version, found = cached_hit[0]
    ok('H5 认出来的是同一个文件',
       os.path.abspath(found['path']) == os.path.abspath(installed[0][0]), found['path'])
    ok('H6 凭元数据/摘要认出（已校验）', found['verified'] in ('meta', 'sha256'),
       found['verified'])
    ok('H7 缓存命中不再二次确认', installed[0][2] is False, 'confirm=%r' % (installed[0][2],))

# --------------------------------------------- I. 选「重新下载」要真的重下
# 否则 download() 会又命中同一个包，用户点了「重新下载」却什么都没发生。
installed.clear()
asked.clear()
cached_path = cached_hit[0][1]['path'] if cached_hit else ''
mtime_before = os.stat(cached_path).st_mtime_ns if cached_path else 0
set_mod._ask_cached = lambda window, version, found: 'download'
set_mod._start_update_check(window, button)
t5 = time.time()
while not installed and time.time() - t5 < 60:
    app.processEvents()
    time.sleep(0.02)
ok('I1 选重新下载后仍会下载并安装', bool(installed) and installed[0][2] is True,
   str(installed)[:80])
ok('I2 文件确实被重写过',
   bool(cached_path) and os.stat(cached_path).st_mtime_ns != mtime_before,
   '%s → %s' % (mtime_before, os.stat(cached_path).st_mtime_ns if cached_path else 0))

# ---------------------------------------------------------------- G. 点叉能真的关掉
# 回归：QProgressDialog 的 setValue() 内部会 ensureDialog() → show()，
# 关窗后只要还有一帧进度进来，窗口就会自己弹回来（看起来「关不掉」）。
# 先把缓存清掉，让下面这段走真下载。
shutil.rmtree(UPDATE_DIR, ignore_errors=True)
installed.clear()
set_mod._start_update_download(window, '2.9.0', URL)
t1 = time.time()
box = None
while time.time() - t1 < 15:
    app.processEvents()
    for w in app.topLevelWidgets():
        if isinstance(w, QProgressDialog) and w.isVisible():
            box = w
    if box is not None and box.value() > 0:
        break
    time.sleep(0.01)
ok('G1 下载中窗口可见', box is not None and box.isVisible(),
   '值=%s' % (box.value() if box is not None else '无窗口'))

if box is not None:
    box.close()                      # 等价于点标题栏的叉
    app.processEvents()
    bounced = 0
    t2 = time.time()
    while time.time() - t2 < 1.2:    # 1.2 秒内足够漏进十几帧进度
        app.processEvents()
        if box.isVisible():
            bounced += 1
        time.sleep(0.02)
    ok('G2 点叉后不再弹回来', bounced == 0, '弹回 %d 帧' % bounced)

t3 = time.time()
while time.time() - t3 < 15:
    app.processEvents()
    th = set_mod._update_download_thread
    if th is None or not th.isRunning():
        break
    time.sleep(0.02)
ok('G3 取消后线程已停', set_mod._update_download_thread is None
   or not set_mod._update_download_thread.isRunning())
ok('G4 取消不当成下载完成', not installed, str(installed))

# 预览版：点按钮不联网、不下载，只提示
installed.clear()
asked.clear()
cu.is_preview_version = lambda version=None: True
set_mod._start_update_check(window, button)
app.processEvents()
ok('F8 预览版不发起检查/下载', not installed and not asked, str(asked)[:60])

srv.shutdown()
bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
