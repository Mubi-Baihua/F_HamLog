# -*- coding: utf-8 -*-
"""下载加速冒烟：镜像择优 / 镜像内容校验 / sha256 校验。

全程本地起服务，不出网。为了不走真 GitHub，测试里把 ``mirror_urls`` 换成
「返回几个 127.0.0.1 地址」，这样择优逻辑本身能完整跑到。

用法：python tests/__update_source_smoke.py
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

from f_hamlog import check_update as cu        # noqa: E402

TMP = tempfile.mkdtemp(prefix='__upd_src_')
# 缓存目录挪进临时目录，别读到真实用户目录里已下载的包（会跳过下载，测不成镜像择优）
os.environ[cu.CACHE_DIR_ENV] = os.path.join(TMP, 'cache')
cu.legacy_dirs = lambda: []
PAYLOAD = bytes(random.Random(77).getrandbits(8) for _ in range(6 << 20))
TAMPERED = bytearray(PAYLOAD)
TAMPERED[len(TAMPERED) // 2] ^= 0xFF          # 正中改一个字节：抽样比对必然发现
TAMPERED = bytes(TAMPERED)

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


class Server:
    """一个能限速、能返回被篡改内容的 Range 服务。"""

    def __init__(self, payload, delay=0.0, chunk=32 << 10, no_range=False):
        self.payload = payload
        self.delay = delay
        self.chunk = chunk
        self.no_range = no_range
        self.requests = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.requests += 1
                rng = self.headers.get('Range')
                if outer.no_range:
                    rng = None           # 假装不认 Range：整包 200（有些代理就是这样）
                body = outer.payload
                try:
                    if rng:
                        start, end = rng.split('=')[1].split('-')
                        start = int(start)
                        end = int(end) if end else len(body) - 1
                        end = min(end, len(body) - 1)
                        piece = body[start:end + 1]
                        self.send_response(206)
                        self.send_header('Content-Range',
                                         'bytes %d-%d/%d' % (start, end, len(body)))
                        self.send_header('Content-Length', str(len(piece)))
                        self.end_headers()
                    else:
                        piece = body
                        self.send_response(200)
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                    for i in range(0, len(piece), outer.chunk):
                        self.wfile.write(piece[i:i + outer.chunk])
                        if outer.delay:
                            time.sleep(outer.delay)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d/F%%20HamLog%%202.9%%20setup.exe' % self.srv.server_address[1]

    def stop(self):
        self.srv.shutdown()


# ------------------------------------------------------------------ A. 地址判定
ok('A1 非 GitHub 地址不启镜像', cu.mirror_urls('https://example.com/a.exe') == [],
   str(cu.mirror_urls('https://example.com/a.exe')))
gh = 'https://github.com/u/r/releases/download/1.0/a.exe'
ok('A2 GitHub 地址生成镜像', len(cu.mirror_urls(gh)) == len(cu.MIRROR_PREFIXES)
   and cu.mirror_urls(gh)[0] == cu.MIRROR_PREFIXES[0] + gh, str(cu.mirror_urls(gh))[:60])
ok('A3 objects.githubusercontent 也算', cu.mirror_urls(
    'https://objects.githubusercontent.com/x/a.exe') != [])

# ------------------------------------------------------------------ B. 测速择优
slow = Server(PAYLOAD, delay=0.012)          # 每个 32 KB 停 12 ms → 约 2.5 MB/s
fast = Server(PAYLOAD)
s_slow = cu._window_speed(slow.url)
s_fast = cu._window_speed(fast.url)
ok('B1 时间窗测速能区分快慢', s_fast > s_slow * 1.3,
   '快 %.1f MB/s vs 慢 %.1f MB/s' % (s_fast / 1048576, s_slow / 1048576))
ok('B2 连不上的候选记 0', cu._window_speed('http://127.0.0.1:1/x.exe', seconds=0.5) == 0.0)

_real_mirrors = cu.mirror_urls
cu.mirror_urls = lambda url: [slow.url, fast.url]
chosen, via = cu.choose_source('https://github.com/u/r/releases/download/1.0/a.exe')
ok('B3 择优挑到快的那个', chosen == fast.url and via, 'chosen=%s' % chosen[:40])

cu.mirror_urls = lambda url: [slow.url, slow.url + '?2']
chosen2, via2 = cu.choose_source(fast.url)   # 直连本身很快 → 不该换镜像
ok('B4 镜像不比直连快就不换', chosen2 == fast.url and not via2, 'chosen=%s' % chosen2[:40])

cu.mirror_urls = lambda url: ['http://127.0.0.1:1/dead.exe']
chosen3, via3 = cu.choose_source(fast.url)   # 镜像全死 → 直连
ok('B5 镜像全挂回直连', chosen3 == fast.url and not via3)

# 有些代理不认 Range：单线程跑不过 16 线程直连，不该选它
norange = Server(PAYLOAD, no_range=True)
cu.mirror_urls = lambda url: [norange.url]
chosen4, via4 = cu.choose_source(slow.url)
ok('B6 镜像不支持分段就不换', chosen4 == slow.url and not via4, 'chosen=%s' % chosen4[:40])

# ------------------------------------------------- C. 镜像返回被篡改的内容
# 慢的「官方」+ 快的「镜像」，镜像给的是改过一个字节的文件（长度一样）。
bad = Server(TAMPERED)                       # 快，但内容是假的
cu.mirror_urls = lambda url: [bad.url]
dest_c = os.path.join(TMP, 'c', 'setup.exe')
t0 = time.time()
path = cu.download(slow.url, dest=dest_c)
blob = open(path, 'rb').read()
ok('C1 篡改被抽样比对发现并回退直连',
   hashlib.sha256(blob).hexdigest() == hashlib.sha256(PAYLOAD).hexdigest()
   and bad.requests > 0, '%.1f 秒，镜像被请求 %d 次' % (time.time() - t0, bad.requests))

# ------------------------------------------------------------- D. sha256 校验
cu.mirror_urls = _real_mirrors                # 恢复，本地地址本来就无镜像
dest_d = os.path.join(TMP, 'd', 'setup.exe')
path = cu.download(slow.url, dest=dest_d, sha256=hashlib.sha256(PAYLOAD).hexdigest())
ok('D1 摘要正确时通过', os.path.getsize(path) == len(PAYLOAD))

dest_e = os.path.join(TMP, 'e', 'setup.exe')
try:
    cu.download(slow.url, dest=dest_e, sha256='0' * 64)
    ok('D2 摘要不符要报错', False, '没有抛异常')
except IOError as e:
    ok('D2 摘要不符要报错', '校验失败' in str(e), str(e))
ok('D3 摘要不符的文件被删掉', not os.path.exists(dest_e))

# ------------------------------------------------------- E. parse_text 第三段
v, u, d = cu.parse_text('2.9.0 https://x/y.exe ' + hashlib.sha256(PAYLOAD).hexdigest())
ok('E1 版本文件可带摘要', v == '2.9.0' and len(d) == 64, d[:12] + '…')
v2, u2, d2 = cu.parse_text('2.9.0 https://x/y.exe')
ok('E2 不带摘要仍可用', d2 == '', repr(d2))
v3, u3, d3 = cu.parse_text('2.9.0 https://x/y.exe not-a-digest')
ok('E3 乱写的摘要求忽略', d3 == '', repr(d3))

slow.stop()
fast.stop()
bad.stop()
bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
