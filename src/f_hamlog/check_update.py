# -*- coding: utf-8 -*-
"""检查更新 / 下载更新包 / 运行安装包。

本模块只做「网络 + 文件 + 起进程」，**不 import 任何 Qt**：
界面（提问、进度条）在 ``set.py`` 的「检查更新」按钮里。这样它可以单独跑
（``python -m f_hamlog.check_update``），离屏测试也不用起窗口。

版本信息来源 ``check_url``：一行文本，形如 ``2.8.0 https://.../setup.exe``。
  · 版本号与本地 ``__version__`` 相同（或更旧）→ ``latest``；
  · 不同 → ``new``，带下载地址；
  · **预览版**（版本串里带 ``UTC`` / ``Preview`` / ``日常开发``）→ ``preview``，
    不去联网、也永不自我更新（预览包是开发中的临时产物，装回正式版会丢功能）。
"""

from f_hamlog import __version__

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

check_url = "https://mubi-baihua.pages.dev/f_hamlog_check_update.txt"

# 必须用浏览器 UA：Cloudflare 会直接 403 掉 "Python-urllib/x.y"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

TIMEOUT = 10        # 单次请求超时（秒）
MAX_RETRIES = 5     # 失败后最多重试 5 次（首次不算，合计最多 6 次请求）
MAX_BACKOFF = 5.0   # 单次重试等待上限（秒）

# 这些状态码「再试也一样」，直接放弃，不浪费 5 次重试
PERMANENT_CODES = (400, 401, 404, 410, 451)

# ---------------------------------------------------------------- 下载参数
WORKERS = 16                # 默认线程数：GitHub 的 CDN 对**单连接**限速，多开几条并行提升最明显
MAX_WORKERS = 32            # 上限：再多只是把带宽切成更碎的片，反而拖慢合并
CHUNK_MIN_BYTES = 4 << 20   # 小于 4 MB 不分段：切块与合并的开销比省下的时间还多
PART_MIN_BYTES = 512 << 10  # 每段至少 512 KB：段太碎时建连开销占大头
READ_BLOCK = 64 << 10       # 单次读 64 KB
PART_TRIES = 3              # 单个分段最多下 3 次（每次重下该段）
PART_TIMEOUT = 15           # 分段连接的空闲超时：卡住 15 秒就断开重连（换条连接常常就快了）

# ---------------------------------------------------------------- 镜像择优
# GitHub 加速镜像都是「前缀式」：把原始 URL 直接拼在前缀后面。
# 只有在测速窗口里比直连快 MIRROR_GAIN 倍才会用，而且下完要抽样比对官方字节
# （见 _spot_check），所以镜像返回被篡改的内容会被发现并回退直连。
GITHUB_HOSTS = ('github.com', 'objects.githubusercontent.com', 'codeload.github.com')
MIRROR_PREFIXES = (
    'https://ghfast.top/',
    'https://gh-proxy.com/',
    'https://ghproxy.net/',
    'https://ghproxy.cc/',
)
MIRROR_GAIN = 1.3           # 镜像要比直连快 30% 才值得换（否则别折腾）
SAMPLE_WINDOW = 2.0         # 测速窗口（秒）：窗口内谁读到的字节多谁快
SAMPLE_BYTES = 256 << 10    # 单个候选在窗口内最多读这么多，够判快慢又不浪费流量
SPOT_BLOCK = 64 << 10       # 镜像下载完成后，与官方比对的抽样块大小

# 预览版标记：构建预览包时 __init__.py 会被改写为
# 「日常开发Preview UTC-yyyyMMdd-HHmm 2.x.y」，命中任意一个都视为预览版
PREVIEW_MARKERS = ('UTC', 'Preview', '日常开发')

# 检查结果状态
PREVIEW = 'preview'
ERROR = 'error'
LATEST = 'latest'
NEW = 'new'


class Cancelled(Exception):
    """下载被用户取消。"""


# ---------------------------------------------------------------- 版本判定

def is_preview_version(version=None):
    """当前（或指定）版本是否为预览版 —— 预览版不参与自动更新。"""
    text = __version__ if version is None else str(version)
    return any(mark in text for mark in PREVIEW_MARKERS)


def _version_tuple(text):
    """'2.8.0' → (2, 8, 0)；不是纯数字点分版本则返回 None。"""
    m = re.match(r'^\s*(\d+(?:\.\d+)*)\s*$', str(text or ''))
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split('.'))


def _same_or_older(remote, local):
    """远端版本是否不比本地新。两边都是纯数字版本时按数值比，否则按字符串相等。"""
    a, b = _version_tuple(remote), _version_tuple(local)
    if a is not None and b is not None:
        n = max(len(a), len(b))
        a = a + (0,) * (n - len(a))
        b = b + (0,) * (n - len(b))
        return a <= b
    return str(remote).strip() == str(local).strip()


# ---------------------------------------------------------------- 联网检查

def get_text(retry=0):
    """取版本信息文本。失败后最多重试 MAX_RETRIES 次，全失败返回 None。

    retry 只是内部计数器，外部调用不用传。
    用 while 循环而不是递归：递归在次数判断写错时会变成无限深，
    且栈溢出后还会被 except 吞掉继续递归。
    """
    err = None
    while True:
        try:
            req = urllib.request.Request(check_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                text = r.read().decode('utf-8', errors='replace').strip()
            #print(text)
            return text

        except urllib.error.HTTPError as e:
            err = e
            if e.code in PERMANENT_CODES:
                print('检查更新失败：%s' % e)
                return 'e'

        except Exception as e:          # URLError / 超时 / 连接重置 / SSL
            err = e

        if retry >= MAX_RETRIES:
            #print('检查更新失败（已重试 %d 次）：%s' % (retry, err))
            return 'e'

        retry += 1
        delay = min(0.5 * 2 ** (retry - 1), MAX_BACKOFF)   # 0.5/1/2/4/5
        print('[重试 %d/%d] %s，%.1f 秒后重试…' % (retry, MAX_RETRIES, err, delay))
        time.sleep(delay)


def parse_text(text):
    """``'2.9.0 https://.../setup.exe [sha256]'`` → ``('2.9.0', url, sha256或'')``。

    第三段（sha256）可选：有它就能校验安装包，也就能放心走镜像。
    """
    parts = str(text or '').split()
    if len(parts) < 2:
        raise ValueError('版本信息格式不正确：%r' % (text,))
    digest = parts[2].strip().lower() if len(parts) > 2 else ''
    if digest and not re.fullmatch(r'[0-9a-f]{64}', digest):
        digest = ''                      # 长得不像摘要就当没写，别把更新卡死
    return parts[0], parts[1], digest


def check():
    """检查更新，返回 ``dict(status, version, url, sha256, detail)``。

    status：``preview`` / ``error`` / ``latest`` / ``new``。
    **不弹窗、不下载**——要不要更新由界面决定。
    """
    info = {'status': ERROR, 'version': '', 'url': '', 'sha256': '', 'detail': ''}
    if is_preview_version():
        info.update(status=PREVIEW, version=__version__, detail='预览版不参与自动更新')
        return info

    text = get_text()
    if text == 'e' or not text:
        info['detail'] = '无法获取版本信息（网络错误或服务器不可用）'
        return info

    try:
        version, url, digest = parse_text(text)
    except ValueError as e:
        info['detail'] = str(e)
        return info

    info['version'] = version
    info['url'] = url
    info['sha256'] = digest
    info['status'] = LATEST if _same_or_older(version, __version__) else NEW
    return info


def main():
    """兼容旧调用：'p' 预览 / 'n' 最新 / 'e' 失败 / (版本, 地址) 有新版本。"""
    info = check()
    status = info['status']
    if status == PREVIEW:
        return 'p'
    if status == ERROR:
        return 'e'
    if status == LATEST:
        return 'n'
    return (info['version'], info['url'])


# ---------------------------------------------------------------- 下载

def _request(url, extra=None):
    headers = dict(HEADERS)
    if extra:
        headers.update(extra)
    return urllib.request.Request(url, headers=headers)


def _filename_of(url, disposition=''):
    """从 Content-Disposition 或 URL 推断文件名，强制成 ``.exe``。"""
    name = ''
    if disposition:
        m = re.search(r"filename\*?\s*=\s*(?:UTF-8'')?\"?([^\";]+)", disposition, re.I)
        if m:
            name = urllib.parse.unquote(m.group(1).strip())
    if not name:
        name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit('/', 1)[-1])
    name = os.path.basename(name.replace('\\', '/')).strip()
    if not name:
        name = 'F HamLog setup.exe'
    if not name.lower().endswith('.exe'):
        name += '.exe'
    return name


def probe(url):
    """探测下载地址：返回 ``(可分段, 总字节数或 None, 文件名)``。

    只请求 1 个字节（``Range: bytes=0-0``）：服务器回 206 且带
    ``Content-Range: bytes 0-0/总长`` 说明支持分段；回 200 说明不支持，
    这时**立刻关掉**（响应体一个字节都没读），别把整包白下一遍。
    """
    req = _request(url, {'Range': 'bytes=0-0'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        status = getattr(r, 'status', None) or r.getcode()
        total = None
        content_range = r.headers.get('Content-Range') or ''
        if status == 206 and '/' in content_range:
            tail = content_range.rsplit('/', 1)[-1].strip()
            if tail.isdigit():
                total = int(tail)
        if total is None and status == 200:
            length = (r.headers.get('Content-Length') or '').strip()
            if length.isdigit():
                total = int(length)
        ranged = status == 206 and bool(total)
        name = _filename_of(url, r.headers.get('Content-Disposition') or '')
    return ranged, total, name


def format_size(n):
    """12345678 → '11.8 MB'（KB / MB / GB 自动选单位）。"""
    n = float(n or 0)
    if n >= 1 << 30:
        return '%.2f GB' % (n / (1 << 30))
    if n >= 1 << 20:
        return '%.1f MB' % (n / (1 << 20))
    if n >= 1 << 10:
        return '%.0f KB' % (n / (1 << 10))
    return '%.0f B' % n


def format_speed(bps):
    """字节/秒 → '1.2 MB/s'（给进度窗用，单位与语言无关，不必进词表）。"""
    return format_size(bps) + '/s'


def format_eta(seconds):
    """剩余秒数 → '00:42' / '01:02:03'（同样与语言无关，'剩余'/'ETA' 走词表）。

    取不到（None / 负数 / 速度还是 0）时返回 ''，调用方据此决定要不要显示这一段。
    """
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return ''
    if s < 0:
        return ''
    s = min(s, 99 * 3600 + 59 * 60 + 59)     # 兜底：再长也只画到 99:59:59，别撑爆窗口
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return '%02d:%02d:%02d' % (h, m, sec) if h else '%02d:%02d' % (m, sec)


class Speedometer:
    """按滑动时间窗估算下载速度（字节/秒）。

    为什么不用「相邻两次的差值 / 差值时间」：进度回调是限流的（约 10 次/秒），
    抖动很大，逐次算会让数字乱跳。这里取最近 ``window`` 秒内的首尾样本平均。

    分段重下时 ``_Meter.add(-got)`` 会把已计字节退回去（done 变小），
    这时整窗丢弃重建 —— 否则会算出一段负速度。
    """

    def __init__(self, window=1.0, clock=time.monotonic):
        self.window = float(window)
        self._clock = clock
        self._samples = []          # [(时刻, 已下载字节)]

    def reset(self):
        self._samples = []

    def update(self, done):
        """喂入最新的已下载字节数，返回当前速度（字节/秒）。"""
        done = int(done or 0)
        now = self._clock()
        s = self._samples
        if s and done < s[-1][1]:
            s = self._samples = []          # 重下某一段：旧的样本全部作废
        s.append((now, done))
        # 只保留窗口内的样本，但至少留两个（否则短窗口内算不出速度）
        while len(s) > 2 and now - s[0][0] > self.window:
            s.pop(0)
        if len(s) < 2:
            return 0.0
        t0, d0 = s[0]
        dt = now - t0
        if dt <= 1e-3:
            return 0.0
        return max(0.0, (done - d0) / dt)


class EtaEstimator:
    """估算剩余时间（秒），并压掉因速度抖动导致的跳变。

    为什么不直接 ``(总长 - 已下载) / 当前速度``：短窗速度本身就在抖（同一个连接
    前后两秒差一倍是常事），算出来的剩余时间会来回跳几十秒，看着像坏了。

    这里三条规则：

    1. 速度只认**自开始以来的累计平均**（样本越多越稳），不碰短窗；
    2. 新估算变小就跟着走（自然倒计时）；
    3. 新估算变大时，先要超出死区 ``max(0.3, min(deadband, 20%))``（说明真的变慢了），
       再按「每次最多 5%（至少 0.5 秒）」一帧一帧挪上去 —— 不会一帧从 12 秒蹦到 40 秒。

    ``done`` 回退（分段重下 / 换镜像）时换基准、**保留当前显示值**，避免文案一会儿
    有剩余时间一会儿没有。速度还测不出来（``warmup`` 内）或总长未知时返回 ``None``。
    """

    def __init__(self, clock=time.monotonic, warmup=1.0, deadband=2.0, step_ratio=0.05):
        self._clock = clock
        self.warmup = float(warmup)
        self.deadband = float(deadband)
        self.step_ratio = float(step_ratio)
        self.reset()

    def reset(self):
        self._t0 = None
        self._done0 = 0
        self._last = 0
        self._eta = None

    def update(self, done, total):
        """喂入最新的已下载字节数，返回平滑后的剩余秒数（或 ``None``）。"""
        done = int(done or 0)
        total = int(total or 0)
        if total <= 0:
            return None
        now = self._clock()
        if self._t0 is None:
            self._t0, self._done0, self._last = now, done, done
            return None
        if done < self._last:
            # 进度倒退（分段重下 / 信号乱序）：这一帧不重新估算，显示值保持不变。
            # **不要重设基准**——否则每次小回退都要重新预热，剩余时间会一直不显示。
            return self._eta
        self._last = done
        dt = now - self._t0
        if dt < self.warmup:
            return None                     # 样本太短，估出来全是噪声
        moved = done - self._done0
        if moved <= 0:
            return self._eta
        speed = moved / dt                  # 累计平均速度，天生比短窗稳
        raw = max(0.0, (total - done) / speed)
        eta = self._eta
        if eta is None:
            self._eta = raw
        elif raw < eta:
            self._eta = raw                 # 往下走就跟着倒计时
        elif raw - eta > max(0.3, min(self.deadband, eta * 0.2)):
            # 真的慢了：允许上调，但一帧只挪一小步，别跳。
            # 死区随剩余时间缩放：剩几秒时容忍 0.3 秒，剩几十秒时才用满 deadband，
            # 否则末尾几秒会一直卡在 00:00。
            step = max(0.5, eta * self.step_ratio)
            self._eta = eta + min(raw - eta, step)
        return self._eta


class _Meter:
    """跨线程累计进度 + 限流回调。

    8 个线程各读 64 KB 就回调一次的话，界面每秒要处理上千次信号；
    这里只在「百分比变了且距上次超过 interval」时才回调。
    """

    def __init__(self, total, callback, interval=0.1):
        self.total = int(total or 0)
        self.callback = callback
        self.interval = interval
        self.done = 0
        self._lock = threading.Lock()
        self._last_time = 0.0
        self._last_pct = -1
        self._warned = False

    def add(self, n):
        if not self.callback:
            with self._lock:
                self.done += n
            return
        # 回调**必须在锁内**调用：多个工作线程同时 add 时，如果在锁外回调，
        # 后算出来的小 done 可能先送到界面（信号按发射顺序排队），界面就会看到
        # 「8.25 MB → 8.19 MB」这种倒退，剩余时间被反复重置。
        with self._lock:
            self.done += n
            done, total = self.done, self.total
            now = time.time()
            pct = int(done * 100 / total) if total > 0 else -1
            if now - self._last_time < self.interval and pct == self._last_pct:
                return
            self._last_time = now
            self._last_pct = pct
            # 界面回调（Qt 信号 emit）理论上不会抛，但真抛了也不该让整个下载失败 ——
            # 进度只是显示，包下不完整才是大问题。
            try:
                self.callback(done, total)
            except Exception as e:
                if not self._warned:
                    self._warned = True
                    print('[更新] 进度回调出错（继续下载）：%s' % e)

    def flush(self):
        if self.callback:
            try:
                self.callback(self.done, self.total)
            except Exception:
                pass


def _clean_parts(dest):
    """删掉上次留下的分段文件（``xxx.exe.part0`` / ``xxx.exe.merging``）。"""
    folder = os.path.dirname(dest) or '.'
    base = os.path.basename(dest)
    try:
        for fn in os.listdir(folder):
            if fn.startswith(base + '.part') or fn == base + '.merging':
                try:
                    os.remove(os.path.join(folder, fn))
                except OSError:
                    pass
    except OSError:
        pass


def _download_stream(url, dest, meter, cancel):
    """单线程整包下载（服务器不支持分段 / 文件太小 / 分段失败时用）。"""
    tmp = dest + '.part0'
    try:
        with urllib.request.urlopen(_request(url), timeout=PART_TIMEOUT) as r, open(tmp, 'wb') as f:
            if not meter.total:
                length = (r.headers.get('Content-Length') or '').strip()
                meter.total = int(length) if length.isdigit() else 0
            while True:
                if cancel.is_set():
                    raise Cancelled()
                buf = r.read(READ_BLOCK)
                if not buf:
                    break
                f.write(buf)
                meter.add(len(buf))
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _download_parts(url, dest, total, parts, meter, cancel):
    """把文件切成 parts 段并行下载，最后合并成 ``dest``。"""
    step = total // parts
    spans = []
    start = 0
    for i in range(parts):
        end = total - 1 if i == parts - 1 else start + step - 1
        spans.append((i, start, end))
        start = end + 1

    def work(idx, start, end):
        part = '%s.part%d' % (dest, idx)
        expect = end - start + 1
        for attempt in range(PART_TRIES):
            if cancel.is_set():
                raise Cancelled()
            got = 0
            try:
                req = _request(url, {'Range': 'bytes=%d-%d' % (start, end)})
                with urllib.request.urlopen(req, timeout=PART_TIMEOUT) as r, open(part, 'wb') as f:
                    while True:
                        if cancel.is_set():
                            raise Cancelled()
                        buf = r.read(READ_BLOCK)
                        if not buf:
                            break
                        f.write(buf)
                        got += len(buf)
                        meter.add(len(buf))
                if got != expect:
                    raise IOError('分段 %d 长度不符：%d/%d 字节' % (idx, got, expect))
                return
            except Cancelled:
                raise
            except Exception as e:
                if got:
                    meter.add(-got)        # 这一段要重下，先把已计的数字退回去
                try:
                    os.remove(part)
                except OSError:
                    pass
                if attempt == PART_TRIES - 1:
                    raise IOError('分段 %d 下载失败：%s' % (idx, e))
                time.sleep(0.5 * (attempt + 1))

    failures = []

    def runner(idx, start, end):
        try:
            work(idx, start, end)
        except Cancelled:
            failures.append(Cancelled())
        except Exception as e:
            failures.append(e)

    threads = [threading.Thread(target=runner, args=(i, s, e), daemon=True)
               for i, s, e in spans]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if cancel.is_set():
        raise Cancelled()
    if failures:
        raise failures[0]

    merging = dest + '.merging'
    with open(merging, 'wb') as out:
        for i in range(parts):
            with open('%s.part%d' % (dest, i), 'rb') as f:
                shutil.copyfileobj(f, out, 1 << 20)
    os.replace(merging, dest)
    _clean_parts(dest)


def _host_of(url):
    return (urllib.parse.urlparse(str(url or '')).hostname or '').lower()


def mirror_urls(url):
    """GitHub 地址 → 一组镜像地址（前缀式拼接）；其它地址返回空列表。"""
    if _host_of(url) not in GITHUB_HOSTS:
        return []
    return [prefix + url for prefix in MIRROR_PREFIXES]


def _window_speed(url, seconds=SAMPLE_WINDOW, limit=SAMPLE_BYTES, cancel=None):
    """在固定时间窗内尽量多地读，返回窗口内的平均速度（字节/秒）。

    用「固定时间窗」而不是「固定字节数」：慢的候选会一直读到超时，
    快的候选更早读完 —— 两种情况的原始速度数据没法直接比。
    读不到 / 连不上返回 0，不抛异常（本来就是择优，失败只是淘汰）。
    """
    t0 = time.monotonic()
    deadline = t0 + seconds
    got = 0
    try:
        req = _request(url, {'Range': 'bytes=0-%d' % (limit - 1)})
        with urllib.request.urlopen(req, timeout=max(seconds, 1.0)) as r:
            while got < limit and time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    break
                buf = r.read(READ_BLOCK)
                if not buf:
                    break
                got += len(buf)
    except Exception:
        pass
    dt = max(time.monotonic() - t0, 1e-3)
    return got / dt


def choose_source(url, cancel=None):
    """挑下载地址：直连 vs 各个镜像，并行跑同一个测速窗口后取最快。

    返回 ``(地址, 是否用了镜像)``。规则：
      · 非 GitHub 地址（或镜像列表为空）→ 直接直连，**不多发任何请求**；
      · 镜像没比直连快 MIRROR_GAIN 倍 → 仍走直连（宁可慢点也别乱换）。
    并发测速的偏差是「大家一起分带宽」，正好对应国内最常见的
    「单连接被限速」场景：直连被掐住而镜像跑得动时，比值会明显大于 1。
    """
    mirrors = mirror_urls(url)
    if not mirrors:
        return url, False

    scores = {}
    lock = threading.Lock()

    def run(target):
        value = _window_speed(target, cancel=cancel)
        with lock:
            scores[target] = value

    cands = [url] + mirrors
    threads = [threading.Thread(target=run, args=(u,), daemon=True) for u in cands]
    for t in threads:
        t.start()
    # 别无限等：DNS 卡住之类的极端情况最多多花一个窗口的时间，
    # 没回来的候选按 0 分处理（daemon 线程，进程退出时自灭）。
    for t in threads:
        t.join(max(SAMPLE_WINDOW * 2, 3.0))

    best = max(mirrors, key=lambda u: scores.get(u, 0.0))
    direct = scores.get(url, 0.0)
    mirror = scores.get(best, 0.0)
    if mirror > 0 and mirror > direct * MIRROR_GAIN:
        # 有些代理不认 Range（返回 200 整包）→ 只能单线程，反而比 16 线程直连慢
        try:
            ranged, _total, _name = probe(best)
        except Exception as e:
            print('[更新] 镜像探测失败，仍走直连：%s' % e)
            return url, False
        if not ranged:
            print('[更新] 镜像不支持分段，仍走直连')
            return url, False
        print('[更新] 镜像更快，改用 %s（%.0f KB/s，直连 %.0f KB/s）' % (
            _host_of(best), mirror / 1024, direct / 1024))
        return best, True
    return url, False


def _spot_check(official, path, total, block=SPOT_BLOCK):
    """把本地文件与「官方地址」抽样比对（头 / 中 / 尾各一块）。

    走镜像时用：镜像内容被替换成别的东西，抽样几乎必然对不上。
    返回 ``(是否一致, 说明)``；取不到官方数据时按「一致」放过（不能让比对失败反客为主）。
    """
    if not total:
        return True, ''
    size = int(min(block, total))
    if size <= 0:
        return True, ''
    offsets = sorted({0, max(total // 2 - size // 2, 0), max(total - size, 0)})
    try:
        with open(path, 'rb') as f:
            for off in offsets:
                f.seek(off)
                local = f.read(size)
                req = _request(official, {'Range': 'bytes=%d-%d' % (off, off + size - 1)})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    remote = r.read(size)
                if remote[:len(local)] != local[:len(remote)]:
                    return False, '偏移 %d 处与官方不一致' % off
    except Exception as e:
        print('[更新] 抽样比对跳过（官方地址取不到）：%s' % e)
        return True, ''
    return True, ''


def _download_once(source, dest, total_hint, progress, workers, cancel):
    """从 ``source`` 下一次完整文件并写到 ``dest``，返回 (总字节或 None, 文件名)。"""
    try:
        ranged, total, name = probe(source)
    except Exception as e:
        # 探测失败（老服务器不认 Range、返回 416 等）→ 老实单线程
        print('[更新] 不支持分段探测，改单线程：%s' % e)
        ranged, total, name = False, total_hint, _filename_of(source)

    parts = 1
    if ranged and total and total >= CHUNK_MIN_BYTES:
        parts = max(1, min(workers, int(total // PART_MIN_BYTES)))

    _clean_parts(dest)
    meter = _Meter(total, progress)
    if parts > 1:
        try:
            _download_parts(source, dest, total, parts, meter, cancel)
        except Cancelled:
            _clean_parts(dest)
            raise
        except Exception as e:
            print('[更新] %d 线程分段下载失败，改用单线程：%s' % (parts, e))
            _clean_parts(dest)
            meter = _Meter(total, progress)
            _download_stream(source, dest, meter, cancel)
    else:
        _download_stream(source, dest, meter, cancel)

    size = os.path.getsize(dest)
    if total and size != total:
        raise IOError('下载不完整：%d/%d 字节' % (size, total))
    meter.flush()
    return total, name


def _sha256_of(path, cancel=None):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            buf = f.read(1 << 20)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


# ---------------------------------------------------------------- 本地已下载的安装包
#
# 用户点了「检查更新」→「下载并安装」，但上一次可能已经下完只是没装（选了「稍后」、
# 装到一半取消了、或者只是把窗口关了）。每次都重下几十 MB 很冤，所以下载前先翻一遍
# 本地：找到同一个包就直接用。
#
# 怎么确认「就是它」——凭据从硬到软：
#   1. sha256：版本文件里给了第三段就只认摘要；
#   2. 伴随的 .json 元数据：记着下载地址与大小，两者都对得上才算；
#   3. 只有 exe 名称：老版本留在 TEMP 里、没元数据的包，名字对得上且够大才认（调用方可提示未校验）。
# 名字一词只指 exe 文件名本身，**不拿版本号去比**（见 :func:`installer_name` 的说明）。
# 元数据也会在下载成功时写一份，这样下次判断不用再联网、也不必重算摘要。

CACHE_DIR_ENV = 'F_HAMLOG_UPDATE_DIR'   # 环境变量可改缓存目录（测试/调试用）
MIN_INSTALLER_BYTES = 1 << 20           # 小于 1 MB 的 exe 不可能是安装包 → 挡半截文件
META_SUFFIX = '.json'


def update_dir():
    """已下载安装包的存放目录。

    ``%LOCALAPPDATA%/F_HamLog/update`` 优先：TEMP 会被系统清理，放那儿的话「上次下好
    了这次直接装」经常落空；拿不到 LOCALAPPDATA（精简环境）再退回 TEMP。
    """
    env = os.environ.get(CACHE_DIR_ENV)
    if env:
        return os.path.abspath(env)
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if base:
        return os.path.join(base, 'F_HamLog', 'update')
    return os.path.join(tempfile.gettempdir(), 'F_HamLog_update')


def legacy_dirs():
    """旧版本用过的缓存目录（仍然认，免得升级后把已下好的包白白丢掉）。"""
    return [os.path.join(tempfile.gettempdir(), 'F_HamLog_update')]


def _meta_path(path):
    return path + META_SUFFIX


def read_meta(path):
    """读安装包旁边那份 ``.json`` 元数据；没有 / 读坏了都返回 ``{}``。"""
    try:
        with open(_meta_path(path), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_meta(path, url='', version='', sha256=''):
    """记下这个安装包的出处与大小，供下次检查更新时判断「就是它」。失败不影响安装。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    data = {
        'url': str(url or ''),
        'version': str(version or ''),
        'size': size,
        'sha256': str(sha256 or '').lower(),
        'time': int(time.time()),
    }
    try:
        with open(_meta_path(path), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print('[更新] 写缓存元数据失败（不影响安装）：%s' % e)


def installer_name(path_or_url):
    """安装包的「名字指纹」：只看 exe 文件名，忽略大小写、把空格/点/下划线/连字符都当分隔符。

    **判「是不是同一个安装包」只认这个名字，不解析文件名里的版本号。** 版本号在各版本里
    的写法和位置并不统一（``F.HamLog.2.9.0.setup.exe`` / ``F HamLog 2.9 setup.exe``），
    拿它去做相等比较，动不动就判成「不是同一个包」而白白重下几十 MB；而真正要防的
    「装回旧版」，靠元数据里的下载地址 + 字节数（必要时再加 sha256）已经足够 ——
    何况我们要装的，本来就是这个下载地址指着的那个文件。
    """
    text = str(path_or_url or '').replace('\\', '/')
    if '://' in text:
        text = urllib.parse.urlparse(text).path
    name = urllib.parse.unquote(os.path.basename(text)).strip().lower()
    return re.sub(r'[\s._\-]+', '', name)


def find_installer(url, dest=None, sha256=None, total=None, version=None, verify_hash=False,
                   cancel=None):
    """找本地已经下载好的安装包，返回 ``dict(path, size, meta, verified)``；没有则 ``None``。

    ``verified`` 说明凭什么认出来的：``sha256`` / ``meta``（地址 + 大小都对得上）/
    ``name``（只有 exe 名称对得上，老缓存，可信度最低）。

    ``version`` 只为兼容旧调用保留，**不参与判断**：认不认这个包只看 exe 名称、地址、
    大小和摘要（见 :func:`installer_name`）。

    **不联网**：只 stat + 读 json。``verify_hash=True`` 会读整包算 sha256（70 MB 约
    0.3 秒），必须放工作线程里调；给了 ``sha256`` 而它又和元数据不符时，只有这时才
    真去算哈希。
    """
    name = _filename_of(url) if url else ''
    want_name = installer_name(name) if name else ''
    cands = []                              # (路径, 是否核对 exe 名称)
    if dest:
        # dest 是调用方指定的落点，名字由调用方定，不必再跟下载地址的文件名比
        cands.append((os.path.abspath(dest), False))
    if name:
        cands.append((os.path.join(update_dir(), name), True))
        for folder in legacy_dirs():
            cands.append((os.path.join(folder, name), True))

    want = str(sha256 or '').strip().lower()
    seen = set()
    for path, need_name in cands:
        if path in seen:
            continue
        seen.add(path)
        if need_name and want_name and installer_name(path) != want_name:
            print('[更新] exe 名称与 %s 不符，忽略：%s' % (name, path))
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size < MIN_INSTALLER_BYTES:
            continue                        # 半截文件 / 占位小文件：不认
        if total and int(total) != size:
            continue                        # 与远端长度不符，肯定不是同一个包
        meta = read_meta(path)

        if want:                            # 有摘要：只认摘要
            if str(meta.get('sha256') or '').lower() == want:
                return {'path': path, 'size': size, 'meta': meta, 'verified': 'sha256'}
            if not verify_hash:
                continue                    # 元数据没记摘要又没让算：宁可重下
            try:
                digest = _sha256_of(path, cancel)
            except OSError:
                continue
            if digest != want:
                print('[更新] 已有安装包摘要不符，忽略：%s' % path)
                continue
            return {'path': path, 'size': size, 'meta': meta, 'verified': 'sha256'}

        meta_url = str(meta.get('url') or '')
        if meta_url:
            if meta_url != str(url or ''):
                continue                    # 同名但出处不同（换过版本 / 换过地址）
            if int(meta.get('size') or 0) != size:
                continue                    # 大小对不上：被截断或被改过
            return {'path': path, 'size': size, 'meta': meta, 'verified': 'meta'}

        # 没有元数据的老缓存：只凭 exe 名称 + 够大认下来，调用方可以据此提示「未校验」。
        # 这里**不拿版本号比对**：名字对上就说明是本项目的安装包，装谁由下载地址决定。
        return {'path': path, 'size': size, 'meta': meta, 'verified': 'name'}
    return None


def download(url, dest=None, progress=None, workers=None, cancel=None, sha256=None, version='',
             force=False):
    """多线程下载 ``url``，返回本地文件绝对路径。

    能分段就分段并行（默认 16 线程，按文件大小自动减少段数）；服务器不支持
    Range、文件太小、或分段中途失败时，**自动退回单线程**重下，不让用户卡在错误里。
    GitHub 地址会先跟镜像比一比速度（见 :func:`choose_source`），走镜像时用
    :func:`_spot_check` 抽样比对官方字节；给了 ``sha256`` 就整包校验。

    progress：``progress(done, total)``，可能在任意工作线程里被调用，
              界面要经 Qt 信号转回 UI 线程；``total`` 为 0 表示未知总长。
    cancel：``threading.Event``，置位后尽快抛 :class:`Cancelled`。
    sha256：期望的整包摘要（十六进制小写），为空则跳过整包校验。
    version：只用于写缓存元数据（下次判断「本地已有这个包」），不影响下载。
    force：``True`` 时忽略本地已有的包，强制重下（用户在「本地已有安装包」里
           选了「重新下载」）。
    """
    cancel = cancel or threading.Event()
    workers = WORKERS if workers is None else int(workers)
    workers = max(1, min(workers, MAX_WORKERS))

    if dest is None:
        dest = os.path.join(update_dir(), _filename_of(url))
    dest = os.path.abspath(dest)
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)

    # 0) 本地已有同一个包就直接用：一个字节都不重下，也不跟镜像测速（不联网）
    if cancel.is_set():
        raise Cancelled()
    if not force:
        hit = find_installer(url, dest=dest, sha256=sha256, version=version,
                             verify_hash=True, cancel=cancel)
        if hit:
            print('[更新] 本地已有安装包，跳过下载：%s（%s）' % (
                hit['path'], format_size(hit['size'])))
            if progress:
                try:
                    progress(hit['size'], hit['size'])
                except Exception:
                    pass                    # 界面回调出问题不该拖垮下载
            return hit['path']

    # 1) 选路：GitHub 才比镜像，其它地址这一步零开销
    source, via_mirror = choose_source(url, cancel)
    if cancel.is_set():
        raise Cancelled()

    # 2) 下载
    total, _name = _download_once(source, dest, None, progress, workers, cancel)

    # 3) 校验：有摘要按摘要；没摘要但走了镜像，就跟官方抽样比一比
    digest = ''
    if sha256:
        digest = _sha256_of(dest, cancel)
        if digest != str(sha256).strip().lower():
            os.remove(dest)
            raise IOError('更新包校验失败（摘要不符），已删除下载的文件')
    elif via_mirror:
        same, detail = _spot_check(url, dest, total)
        if not same:
            print('[更新] 镜像内容与官方不一致（%s），改用直连重下' % detail)
            os.remove(dest)
            total, _name = _download_once(url, dest, total, progress, workers, cancel)

    # 4) 记下出处：下次检查更新时凭这个认出「本地已经有这个包了」
    write_meta(dest, url=url, version=version, sha256=digest)
    return dest


# ---------------------------------------------------------------- 运行安装包

def run_installer(path, silent=True):
    """运行下载好的安装包（Inno Setup），返回 ``subprocess.Popen``。

    silent=True：不出向导，只留进度窗口（``/SILENT``）；安装器仍会自己弹 UAC。
    ``/CLOSEAPPLICATIONS`` 让安装器处理仍被占用的文件——调用方一般紧接着退出本程序。
    安装包需要管理员权限（见 .iss 的 PrivilegesRequired=admin），这里不额外提权，
    交给 Inno 自己申请，避免出现「双重提权」被系统拒绝。
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    args = [path]
    if silent:
        args += ['/SILENT', '/CLOSEAPPLICATIONS', '/NORESTART']
    return subprocess.Popen(args, cwd=os.path.dirname(path) or '.', close_fds=True)


if __name__ == "__main__":
    print(main())
