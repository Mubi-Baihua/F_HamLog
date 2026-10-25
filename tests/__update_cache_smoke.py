# -*- coding: utf-8 -*-
"""本地已下载安装包的识别（下载前先看有没有下过）。

覆盖：下载后写元数据 → 下次直接命中不联网 / 同名但出处不同不认 / 文件被截断不认 /
摘要校验 / 与远端长度不符不认 / 老缓存（只有文件名）回退 / 缓存命中时进度回调。

用法：python tests/__update_cache_smoke.py
"""
import hashlib
import os
import random
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from f_hamlog import check_update as cu

TMP = tempfile.mkdtemp(prefix='__upd_cache_')
CACHE = os.path.join(TMP, 'cache')
LEGACY = os.path.join(TMP, 'legacy')
os.environ[cu.CACHE_DIR_ENV] = CACHE
cu.legacy_dirs = lambda: [LEGACY]

PAYLOAD = bytes(random.Random(20261025).getrandbits(8) for _ in range(2 << 20))
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


class Handler(BaseHTTPRequestHandler):
    payload = PAYLOAD
    stats = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        stats = Handler.stats
        with stats['lock']:
            stats['requests'] += 1
        rng = self.headers.get('Range')
        try:
            if rng:
                start, end = rng.split('=')[1].split('-')
                start = int(start)
                end = int(end) if end else len(Handler.payload) - 1
                body = Handler.payload[start:end + 1]
                self.send_response(206)
                self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, len(Handler.payload)))
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200)
                self.send_header('Content-Length', str(len(Handler.payload)))
                self.end_headers()
                self.wfile.write(Handler.payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


def make_server(path='/F%20HamLog%202.9%20setup.exe'):
    Handler.stats = {'lock': threading.Lock(), 'requests': 0}
    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d%s' % (srv.server_address[1], path)


NAME = 'F HamLog 2.9 setup.exe'
CACHED = os.path.join(CACHE, NAME)

# ------------------------------------------------------------------ A. 没有任何缓存
srv, url = make_server()
ok('A1 空目录不误报', cu.find_installer(url) is None)
ok('A2 缓存目录取自环境变量', cu.update_dir() == os.path.abspath(CACHE), cu.update_dir())

# ------------------------------------------------------------------ B. 下载 → 写元数据
pings = []
path = cu.download(url, progress=lambda d, t: pings.append((d, t)), version='2.9.0')
ok('B1 落到缓存目录', os.path.abspath(path) == os.path.abspath(CACHED), path)
ok('B2 字节一致', open(path, 'rb').read() == PAYLOAD)
ok('B3 写了元数据', os.path.exists(path + '.json'), path + '.json')
meta = cu.read_meta(path)
ok('B4 元数据记了地址/版本/大小', meta.get('url') == url and meta.get('version') == '2.9.0'
   and meta.get('size') == len(PAYLOAD), str(meta)[:110])
ok('B5 首次下载没走缓存', Handler.stats['requests'] > 0, '%d 个请求' % Handler.stats['requests'])

# ------------------------------------------------------------------ C. 再查：命中
hit = cu.find_installer(url)
ok('C1 命中已下载的包', bool(hit) and os.path.abspath(hit['path']) == os.path.abspath(CACHED),
   str(hit)[:100] if hit else 'None')
ok('C2 凭元数据认出来', bool(hit) and hit['verified'] == 'meta',
   hit['verified'] if hit else '')

# ------------------------------------------------------------------ D. 再下载：一个请求都不发
before = Handler.stats['requests']
pings2 = []
t0 = __import__('time').time()
path2 = cu.download(url, progress=lambda d, t: pings2.append((d, t)), version='2.9.0')
cost = __import__('time').time() - t0
ok('D1 直接复用，不联网', Handler.stats['requests'] == before,
   '请求 %d → %d' % (before, Handler.stats['requests']))
ok('D2 返回同一个文件', os.path.abspath(path2) == os.path.abspath(CACHED))
ok('D3 几乎不耗时', cost < 1.0, '%.3f 秒' % cost)
ok('D4 进度一次性补满', pings2 == [(len(PAYLOAD), len(PAYLOAD))], str(pings2))

# 用户明确选「重新下载」→ force 必须绕过缓存
before_force = Handler.stats['requests']
path4 = cu.download(url, force=True, version='2.9.0')
ok('D5 force 强制重下', Handler.stats['requests'] > before_force,
   '请求 %d → %d' % (before_force, Handler.stats['requests']))
ok('D6 重下内容仍然正确', open(path4, 'rb').read() == PAYLOAD)

# ------------------------------------------------------------------ E. 同名但出处不同
srv2, url2 = make_server('/sub/F%20HamLog%202.9%20setup.exe')
ok('E1 同名不同地址不认', cu.find_installer(url2) is None)
path_e = cu.download(url2, dest=os.path.join(TMP, 'e', NAME))
ok('E2 换了地址仍走下载', bool(path_e) and Handler.stats['requests'] > 0,
   '请求 %d' % Handler.stats['requests'])

# ------------------------------------------------------------------ F. 文件被截断
blob = open(CACHED, 'rb').read()
open(CACHED, 'wb').write(blob[:len(blob) // 2])          # 1 MB，仍 > 1 MB 下限
ok('F1 大小与元数据不符不认', cu.find_installer(url) is None,
   '实际 %d / 记录 %d' % (os.path.getsize(CACHED), len(blob)))
open(CACHED, 'wb').write(blob)                            # 恢复

# ------------------------------------------------------------------ G. 太小的文件
small = os.path.join(CACHE, 'tiny.exe')
open(small, 'wb').write(b'MZ' * 1024)                     # 2 KB
ok('G1 小于 1 MB 不认', cu.find_installer('https://x/tiny.exe') is None)

# ------------------------------------------------------------------ H. 摘要校验
# 下载时没给 sha256 → 元数据里没记摘要；这时只有真算一遍才算数（download 内部就是这么调的）
hit_h = cu.find_installer(url, sha256=DIGEST, verify_hash=True)
ok('H1 摘要正确就认', (hit_h or {}).get('verified') == 'sha256', str(hit_h)[:90])
ok('H1b 不哈希时不信没记录的摘要', cu.find_installer(url, sha256=DIGEST) is None)
wrong = 'f' * 64
ok('H2 摘要不符不认', cu.find_installer(url, sha256=wrong, verify_hash=True) is None)
ok('H3 摘要不符且不哈希时也不认', cu.find_installer(url, sha256=wrong) is None)

# ------------------------------------------------------------------ I. 与远端长度不符
ok('I1 total 不符不认', cu.find_installer(url, total=len(PAYLOAD) + 1024) is None)
ok('I2 total 相符就认', cu.find_installer(url, total=len(PAYLOAD)) is not None)

# ------------------------------------------------------------------ J. 老缓存（只有文件名）
os.makedirs(LEGACY, exist_ok=True)
open(os.path.join(LEGACY, NAME), 'wb').write(PAYLOAD)
os.remove(CACHED)                                         # 只剩旧目录那份
open(os.path.join(LEGACY, NAME + '.json'), 'w').close()    # 坏掉的元数据 → 当没有
hit_legacy = cu.find_installer(url)
ok('J1 旧目录里同名文件也认', bool(hit_legacy)
   and os.path.dirname(hit_legacy['path']) == os.path.abspath(LEGACY),
   str(hit_legacy)[:100] if hit_legacy else 'None')
ok('J2 没有元数据时标记为未校验', bool(hit_legacy) and hit_legacy['verified'] == 'name',
   hit_legacy['verified'] if hit_legacy else '')
ok('J3 元数据坏了不崩', isinstance(cu.read_meta(os.path.join(LEGACY, NAME)), dict))

# ------------------------------------------------------------------ J4 只认 exe 名称
# 判「是不是同一个包」只看 exe 文件名，**不解析文件名里的版本号**：版本号在各版本里
# 位置写法都不统一（`F HamLog 2.9 setup.exe` / `F.HamLog.2.9.0.setup.exe`），拿它做
# 相等比较会把已经下好的包判成「不是这个包」，然后白白重下几十 MB。
ok('J4 版本参数不参与判断，同一个包照样认',
   cu.find_installer(url, version='2.8.1') is not None
   and cu.find_installer(url, version='2.9.0') is not None,
   '2.8.1→%r / 2.9.0→%r' % (bool(cu.find_installer(url, version='2.8.1')),
                             bool(cu.find_installer(url, version='2.9.0'))))
ok('J5 大小写 / 分隔符 / URL 编码都不影响名字比对',
   cu.installer_name('F.HamLog.2.9.Setup.EXE') == cu.installer_name('F HamLog 2.9 setup.exe')
   and cu.installer_name('https://x/F%20HamLog%202.9%20setup.exe') == 'fhamlog29setupexe',
   cu.installer_name('https://x/F%20HamLog%202.9%20setup.exe'))
ok('J6 名字不同就是另一个包',
   cu.installer_name('F.HamLog.2.7.setup.exe') != cu.installer_name('F.HamLog.2.9.setup.exe'))

# ------------------------------------------------------------------ K. 进度回调异常不影响下载
os.remove(os.path.join(LEGACY, NAME))
srv3, url3 = make_server('/F%20HamLog%203.0%20setup.exe')
Handler.payload = PAYLOAD


def boom(done, total):
    raise RuntimeError('界面回调炸了')


try:
    p3 = cu.download(url3, progress=boom)
    ok('K1 回调抛异常也能下载完', os.path.getsize(p3) == len(PAYLOAD), p3)
except Exception as e:
    ok('K1 回调抛异常也能下载完', False, repr(e))
srv.shutdown()
srv2.shutdown()
srv3.shutdown()

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
