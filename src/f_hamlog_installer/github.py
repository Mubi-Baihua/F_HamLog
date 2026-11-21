# -*- coding: utf-8 -*-
"""访问 GitHub 接口：直连优先，不通就走加速镜像，并把结果缓存到本地。

「加速」在这里分两层，别混：

* **安装包本体**：交给 :mod:`f_hamlog.check_update` —— 它本来就有动态分块并行、
  镜像测速择优、走镜像后抽样比对官方字节。本文不重复实现。
* **版本列表**（api.github.com）：这里自己走一遍。``check_update`` 只认
  ``github.com`` 系主机，``api.github.com`` 不在它的镜像名单里，所以单独处理。

镜像一律是「前缀式」：把原始 URL 拼在前缀后面（``https://<镜像>/https://api...``）。
能通的镜像会被记住（``_sticky``），后续请求第一个试它，避免每次都从头试错。
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, config

TIMEOUT = 15
UA = 'F-HamLog-Installer/%s (+%s)' % (__version__, config.REPO_URL)

# 上次能通的来源：'' = 直连，None = 还不知道，其它 = 镜像前缀
_sticky = None
_lock = threading.Lock()


class GithubError(Exception):
    """连不上 / 返回格式不对 —— 调用方只需负责「说清楚 + 退回缓存」。"""


class RateLimited(GithubError):
    """接口额度用完（未登录 60 次/小时），提示填 token 或等一会儿。"""


def mirror_prefixes():
    """镜像前缀直接取自 ``check_update`` —— 加速名单只有一份，改一处就够。"""
    try:
        from f_hamlog.check_update import MIRROR_PREFIXES
    except Exception:
        return ()
    return tuple(MIRROR_PREFIXES)


def _host(url):
    try:
        return urllib.parse.urlparse(url).hostname or url
    except Exception:
        return url


def _remember(source, url):
    """记下这次成功的来源，下次先试它：``''`` = 直连，否则是镜像前缀。"""
    global _sticky
    prefix = '' if source == url else source[:-len(url)]
    with _lock:
        _sticky = prefix


def _sources(url):
    """候选地址：上次成功的来源排第一，其余按 直连 → 镜像 的顺序补上。"""
    prefixes = mirror_prefixes()
    direct = url
    mirrored = [p + url for p in prefixes]
    with _lock:
        sticky = _sticky
    if sticky is None or sticky == '':
        return [direct] + mirrored
    return [sticky + url, direct] + [p + url for p in prefixes if p != sticky]


def _headers(token=None):
    head = {'User-Agent': UA, 'Accept': 'application/vnd.github+json'}
    tok = config.token(token)
    if tok:
        head['Authorization'] = 'Bearer ' + tok
    return head


def _snippet(err, limit=400):
    """错误体只取一小段：镜像返回的 HTML 整页塞进日志没法看。"""
    try:
        return err.read(limit).decode('utf-8', 'replace')
    except Exception:
        return ''


def _get_json(url, token=None):
    req = urllib.request.Request(url, headers=_headers(token))
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    return json.loads(raw.decode('utf-8', 'replace'))


def api_get(url, token=None, retries=1):
    """取一个接口 JSON：逐个来源试，全都失败才抛 :class:`GithubError`。

    ``retries`` 只针对「同一个来源再试一次」（网络抖动），不放大到所有来源 ——
    被墙的来源多试几次只是白等。
    """
    errors = []
    for source in _sources(url):
        for attempt in range(retries + 1):
            try:
                data = _get_json(source, token)
            except urllib.error.HTTPError as e:
                body = _snippet(e)
                low = body.lower()
                if e.code == 404:
                    # 资源真不存在，换镜像也一样：别浪费时间
                    raise GithubError('GitHub 上找不到这个资源（HTTP 404）：%s' % url)
                if e.code in (403, 429) and ('rate limit' in low or 'api rate' in low):
                    raise RateLimited(
                        'GitHub 接口额度已用尽（未登录限制为 60 次/小时）。\n'
                        '  方式一：设置环境变量 GITHUB_TOKEN（或 --token 参数）后重试；\n'
                        '  方式二：等待一小时；\n'
                        '  方式三：使用 --offline 读取本地缓存的版本列表。')
                errors.append('%s → HTTP %s' % (_host(source), e.code))
                break
            except Exception as e:          # 超时 / DNS / TLS / 连接重置 / JSON 坏
                errors.append('%s → %s' % (_host(source), e))
                if attempt < retries:
                    time.sleep(0.8)
                continue
            _remember(source, url)
            return data
    detail = '\n'.join('  ' + e for e in errors) or '  （没有任何可用来源）'
    raise GithubError('访问 GitHub 失败（直连与 %d 个镜像均不可用）：\n%s'
                      % (len(mirror_prefixes()), detail))


# ---------------------------------------------------------------- 本地缓存
#
# GitHub 未登录每小时只给 60 次接口调用，而「列全部版本」一次就翻好几页。
# 缓存一份列表：十分钟内直接复用，断网/被墙时也能靠它干活（--offline）。

def cache_file():
    return os.path.join(config.cache_dir(), 'releases.json')


def load_cache():
    """读缓存，返回 ``{'time': 秒, 'items': [...]}``；没有/读坏返回 ``None``。"""
    try:
        with open(cache_file(), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        return None
    return data


def save_cache(items):
    """写缓存。失败不影响主流程（缓存只是加速与兜底）。"""
    path = cache_file()
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'time': int(time.time()), 'items': items}, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        print('[安装器] 写缓存失败（不影响使用）：%s' % e)


def clear_cache():
    try:
        os.remove(cache_file())
        return True
    except OSError:
        return False


def _fetch_all(token=None):
    """翻页取全部 release（含草稿，由上层过滤）。"""
    items = []
    page = 1
    while page <= config.MAX_PAGES:
        url = '%s?per_page=%d&page=%d' % (config.API_RELEASES, config.PER_PAGE, page)
        data = api_get(url, token)
        if not isinstance(data, list):
            raise GithubError('GitHub 返回的不是版本列表：%r' % (type(data).__name__,))
        items.extend(data)
        if len(data) < config.PER_PAGE:
            break
        page += 1
    return items


def list_releases(token=None, refresh=False, offline=False):
    """取全部 release 的原始 JSON 列表。

    * ``offline``：只读缓存，没有就报错（离线时别假装能联网）；
    * 缓存未过期（``CACHE_TTL``）且没要求 ``refresh``：直接用缓存，一次请求都不发；
    * 联网失败：有缓存就用缓存并提示版本可能不是最新的，没缓存才抛错。
    """
    cached = load_cache()
    if offline:
        if cached:
            return cached['items']
        raise GithubError('离线模式下无本地版本列表缓存，请联网执行一次 list')
    if cached and not refresh and time.time() - cached.get('time', 0) <= config.CACHE_TTL:
        return cached['items']
    try:
        items = _fetch_all(token)
    except GithubError as e:
        if cached:
            stamp = time.strftime('%Y-%m-%d %H:%M', time.localtime(cached.get('time', 0)))
            print('[安装器] 取线上版本列表失败，改用本地缓存（%s）：%s' % (stamp, e))
            return cached['items']
        raise
    save_cache(items)
    return items
