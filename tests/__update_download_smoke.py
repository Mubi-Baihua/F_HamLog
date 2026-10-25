# -*- coding: utf-8 -*-
"""check_update 下载冒烟：多线程分段下载 / 不支持 Range 时退回单线程 / 取消。

不起外网：本地起一个支持 Range 的 HTTP 服务，用 12 MB 随机数据比对字节。

用法：python tests/__update_download_smoke.py
"""
import hashlib
import os
import random
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from f_hamlog import check_update as cu

PAYLOAD = bytes(random.Random(20261024).getrandbits(8) for _ in range(12 << 20))
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


class Handler(BaseHTTPRequestHandler):
    support_range = True
    stats = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        stats = Handler.stats
        rng = self.headers.get('Range')
        with stats['lock']:
            stats['requests'] += 1
            if rng:
                stats['ranged'] += 1
                stats['active'] += 1
                stats['max_active'] = max(stats['max_active'], stats['active'])
        try:
            if rng and Handler.support_range:
                start, end = rng.split('=')[1].split('-')
                start = int(start)
                end = int(end) if end else len(PAYLOAD) - 1
                end = min(end, len(PAYLOAD) - 1)
                body = PAYLOAD[start:end + 1]
                if stats['ranged'] > 1:
                    time.sleep(0.05)          # 让分段请求真正重叠，验证「并行」
                self.send_response(206)
                self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, len(PAYLOAD)))
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200)
                self.send_header('Content-Length', str(len(PAYLOAD)))
                self.end_headers()
                self.wfile.write(PAYLOAD)
        except (BrokenPipeError, ConnectionResetError):
            pass                          # 探测请求只要 1 字节就关连接，属正常
        finally:
            with stats['lock']:
                if rng and Handler.support_range:
                    stats['active'] -= 1


def make_server(support_range):
    Handler.support_range = support_range
    Handler.stats = {'lock': threading.Lock(), 'requests': 0, 'ranged': 0,
                     'active': 0, 'max_active': 0}
    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d/F%%20HamLog%%202.9%%20setup.exe' % srv.server_address[1]


TMP = tempfile.mkdtemp(prefix='__upd_dl_')
# 默认缓存目录在 %LOCALAPPDATA% 下：测试必须挪走，否则会污染真实目录，
# 而且上一次跑剩下的包会让下一次直接命中缓存（一个请求都不发）。
os.environ[cu.CACHE_DIR_ENV] = os.path.join(TMP, 'cache')
cu.legacy_dirs = lambda: []             # 别去翻真实的 %TEMP%/F_HamLog_update

# ------------------------------------------------------------------ A. 分段并行
srv, url = make_server(True)
pings = []
# 不传 dest → 走「按 URL 推断文件名 + 落到缓存目录」这条路径（真实调用就是这么用的）
t0 = time.time()
path = cu.download(url, progress=lambda d, t: pings.append((d, t)), workers=6)
cost = time.time() - t0
blob = open(path, 'rb').read()
stats = Handler.stats
print('A 分段：%.2f 秒，请求 %d（分段 %d，最大并发 %d），进度回调 %d 次' % (
    cost, stats['requests'], stats['ranged'], stats['max_active'], len(pings)))
ok('A1 文件字节一致', hashlib.sha256(blob).hexdigest() == DIGEST, '%d 字节' % len(blob))
ok('A2 分段数 = 6（12MB / 1MB 上限 6 线程）', stats['ranged'] - 1 == 6,
   '探索请求 1 + 分段 %d' % (stats['ranged'] - 1))
ok('A3 确实并行（最大并发 > 1）', stats['max_active'] > 1, 'max_active=%d' % stats['max_active'])
ok('A4 文件名沿用服务器路径', os.path.basename(path) == 'F HamLog 2.9 setup.exe', path)
ok('A5 进度单调不减且末值为总长', all(b[0] >= a[0] for a, b in zip(pings, pings[1:])) and pings[-1][0] == len(PAYLOAD),
   'first=%r last=%r' % (pings[0] if pings else None, pings[-1] if pings else None))
ok('A6 没有残留分段文件', not [f for f in os.listdir(os.path.dirname(path)) if '.part' in f],
   str(os.listdir(os.path.dirname(path))))
srv.shutdown()

# ------------------------------------------------- B. 不支持 Range → 单线程
srv, url = make_server(False)
dest_b = os.path.join(TMP, 'b', 'setup.exe')
path_b = cu.download(url, dest=dest_b)
blob_b = open(path_b, 'rb').read()
print('B 单线程：请求 %d（分段 %d）' % (Handler.stats['requests'], Handler.stats['ranged']))
ok('B1 文件字节一致', hashlib.sha256(blob_b).hexdigest() == DIGEST)
ok('B2 没有发起分段请求', Handler.stats['ranged'] == 1, '只有探测那次带 Range')
srv.shutdown()

# ------------------------------------------------------------- C. 取消
srv, url = make_server(True)
ev = threading.Event()
ev.set()
try:
    cu.download(url, dest=os.path.join(TMP, 'c', 'setup.exe'), cancel=ev)
    ok('C1 取消抛 Cancelled', False, '没有抛异常')
except cu.Cancelled:
    ok('C1 取消抛 Cancelled', True)
except Exception as e:
    ok('C1 取消抛 Cancelled', False, repr(e))
srv.shutdown()

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
