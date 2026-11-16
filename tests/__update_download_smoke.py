# -*- coding: utf-8 -*-
"""check_update 下载冒烟：动态分块并行 / 不支持 Range 退回单线程 / 取消 / 收尾不掉速。

不起外网：本地起一个支持 Range 的 HTTP 服务，用 12 MB 随机数据比对字节。
D 组专门复现「前面快、后面慢」：服务端每条连接先给一阵高速再限速（CDN 就是这么干的），
对着旧实现（定长 N 段 + 合并）做 A/B。

用法：python tests/__update_download_smoke.py
"""
import hashlib
import os
import random
import sys
import tempfile
import threading
import time
import urllib.request
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
                if end > start:           # 探测那次是 bytes=0-0，不算「块」
                    with stats['lock']:
                        stats['spans'].append(len(body))
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
                     'active': 0, 'max_active': 0, 'spans': []}
    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d/F%%20HamLog%%202.9%%20setup.exe' % srv.server_address[1]


TMP = tempfile.mkdtemp(prefix='__upd_dl_')
# 默认缓存目录在 %LOCALAPPDATA% 下：测试必须挪走，否则会污染真实目录，
# 而且上一次跑剩下的包会让下一次直接命中缓存（一个请求都不发）。
os.environ[cu.CACHE_DIR_ENV] = os.path.join(TMP, 'cache')
cu.legacy_dirs = lambda: []             # 别去翻真实的 %TEMP%/F_HamLog_update

# ------------------------------------------------------------------ A. 分块并行
srv, url = make_server(True)
pings = []
# 不传 dest → 走「按 URL 推断文件名 + 落到缓存目录」这条路径（真实调用就是这么用的）
t0 = time.time()
path = cu.download(url, progress=lambda d, t: pings.append((d, t)), workers=6)
cost = time.time() - t0
blob = open(path, 'rb').read()
stats = Handler.stats
expect_chunks = len(cu.chunk_spans(len(PAYLOAD), 6))
print('A 分段：%.2f 秒，请求 %d（分段 %d，最大并发 %d），块数 %d，进度回调 %d 次' % (
    cost, stats['requests'], stats['ranged'], stats['max_active'],
    len(stats['spans']), len(pings)))
ok('A1 文件字节一致', hashlib.sha256(blob).hexdigest() == DIGEST, '%d 字节' % len(blob))
ok('A2 块数 = 线程数 × 3（动态划分，不是「段数 = 线程数」）', stats['ranged'] - 1 == expect_chunks,
   '%d 块（探测请求 1）' % expect_chunks)
ok('A3 确实并行（最大并发 > 1）', stats['max_active'] > 1, 'max_active=%d' % stats['max_active'])
ok('A4 文件名沿用服务器路径', os.path.basename(path) == 'F HamLog 2.9 setup.exe', path)
ok('A5 进度单调不减且末值为总长', all(b[0] >= a[0] for a, b in zip(pings, pings[1:])) and pings[-1][0] == len(PAYLOAD),
   'first=%r last=%r' % (pings[0] if pings else None, pings[-1] if pings else None))
ok('A6 没有残留分段 / 合并文件', not [f for f in os.listdir(os.path.dirname(path))
                                    if '.part' in f or '.merging' in f],
   str(os.listdir(os.path.dirname(path))))
# 「前面快后面慢」的结构性根因：块太大 → 尾部只剩一条连接在跑。这里查两件事：
# ① 每个请求只下「一块」，不再是一整段（总长 / 线程数）；② 块均匀，没有超长尾块。
biggest = max(stats['spans'])
ok('A7 单请求不超过单块上限（没有定长大段）',
   biggest <= cu.chunk_bytes(len(PAYLOAD), 6), '最大 %d 字节' % biggest)
ok('A8 块是均分的（无碎块/超长块）', max(stats['spans']) - min(stats['spans']) <= 4096,
   'min=%d max=%d' % (min(stats['spans']), max(stats['spans'])))
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
left = [f for f in os.listdir(os.path.join(TMP, 'c'))] if os.path.isdir(os.path.join(TMP, 'c')) else []
ok('C2 取消后不留半成品', not [f for f in left if f.endswith('.exe') or '.part' in f], str(left))
srv.shutdown()


# --------------------------------------- D. 收尾不掉速：先给高速再限速的服务器
class DecayServer:
    """每条连接先给 ``burst`` 字节的全速，之后掐到 ``rate`` 字节/秒。

    这就是 CDN / 镜像的真实脾气：新连接先痛快一阵，然后单连接限速。
    旧实现（段数 = 线程数）里每条连接只建一次，于是「前面快、后面慢」；
    动态分块每块一条新连接，等于反复白拿那阵高速。
    """

    def __init__(self, payload, burst=384 << 10, rate=256 << 10, block=32 << 10):
        self.payload = payload
        self.burst = burst
        self.rate = rate
        self.block = block
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get('Range')
                body = outer.payload
                try:
                    if rng:
                        start, end = rng.split('=')[1].split('-')
                        start = int(start)
                        end = int(end) if end else len(body) - 1
                        end = min(end, len(body) - 1)
                        piece = body[start:end + 1]
                        self.send_response(206)
                        self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, len(body)))
                        self.send_header('Content-Length', str(len(piece)))
                        self.end_headers()
                    else:
                        piece = body
                        self.send_response(200)
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                    sent = 0
                    for i in range(0, len(piece), outer.block):
                        self.wfile.write(piece[i:i + outer.block])
                        sent += outer.block
                        if sent > outer.burst:
                            time.sleep(outer.block / float(outer.rate))
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d/decay.exe' % self.srv.server_address[1]

    def stop(self):
        self.srv.shutdown()


def old_style_download(url, dest, workers):
    """旧实现对照：定长 N 段（段数 = 线程数）+ 最后合并。只用来比时间。"""
    with urllib.request.urlopen(cu._request(url, {'Range': 'bytes=0-0'}), timeout=15) as r:
        total = int((r.headers.get('Content-Range') or '').rsplit('/', 1)[-1])
    step = total // workers
    spans = []
    start = 0
    for i in range(workers):
        end = total - 1 if i == workers - 1 else start + step - 1
        spans.append((start, end))
        start = end + 1

    def work(i, s, e):
        req = cu._request(url, {'Range': 'bytes=%d-%d' % (s, e)})
        with urllib.request.urlopen(req, timeout=15) as r:
            blob = r.read()
        with open('%s.part%d' % (dest, i), 'wb') as f:
            f.write(blob)

    ts = [threading.Thread(target=work, args=(i, s, e)) for i, (s, e) in enumerate(spans)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    with open(dest, 'wb') as out:
        for i in range(workers):
            with open('%s.part%d' % (dest, i), 'rb') as f:
                out.write(f.read())
            os.remove('%s.part%d' % (dest, i))
    return total


DECAY = bytes(random.Random(4242).getrandbits(8) for _ in range(6 << 20))
decay = DecayServer(DECAY)
os.makedirs(os.path.join(TMP, 'd'), exist_ok=True)
dest_old = os.path.join(TMP, 'd', 'old.exe')
dest_new = os.path.join(TMP, 'd', 'new.exe')
t0 = time.time()
old_style_download(decay.url, dest_old, 4)
t_old = time.time() - t0
t0 = time.time()
cu.download(decay.url, dest=dest_new, workers=4)
t_new = time.time() - t0
same_old = open(dest_old, 'rb').read() == DECAY
same_new = open(dest_new, 'rb').read() == DECAY
print('D 先快后限速：旧实现 %.2f 秒，动态分块 %.2f 秒（%.2f×）' % (
    t_old, t_new, (t_old / t_new) if t_new else 0))
ok('D1 两边字节都正确', same_old and same_new, 'old=%s new=%s' % (same_old, same_new))
ok('D2 动态分块明显更快（收尾不再被单连接拖住）', t_new < t_old * 0.75,
   '%.2f 秒 vs %.2f 秒' % (t_new, t_old))
decay.stop()

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
