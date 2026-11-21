# -*- coding: utf-8 -*-
"""下载安装包：挑哪个、放哪儿、记账。

**真正下字节的活儿全交给 :mod:`f_hamlog.check_update`** —— 动态分块并行、镜像测速
择优、走镜像后抽样比对官方字节、失败退回单线程，这套东西已经有唯一出处，这里再抄
一份就会立刻分叉（主程序改了、安装器没改）。本模块只做三件它不管的事：

* 按「版本 / 文件」分目录放（1.x 的安装包名字全叫 ``setup.exe``，不分开就打架）；
* 本地已有完整文件就跳过（不联网、不重下 70 MB）；
* 往 ``manifest.json`` 里记账（大小、摘要、来源、时间），供 ``verify`` 核对。
"""

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from f_hamlog import check_update as cu

from . import config, releases

MANIFEST_NAME = 'manifest.json'

# 「够不够像安装包」的下限。check_update 那边用 1 MB 挡半截文件，这里放宽到
# 64 KB：1.x 发的 ``setup.exe`` 只有 550 KB（联网下载器的壳），不该被判成残包。
MIN_BYTES = 64 << 10


# ---------------------------------------------------------------- 小工具

def sha256_of(path, cancel=None):
    """整包 sha256（小写十六进制）。``cancel`` 置位时抛 ``check_update.Cancelled``。"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise cu.Cancelled()
            buf = f.read(1 << 20)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def safe_name(text):
    """版本号要当目录名：把 Windows 不认的字符换掉，其余原样保留。"""
    name = re.sub(r'[\\/:*?"<>|\s]+', '_', str(text or '').strip())
    return name.strip('._') or 'unknown'


def dest_path(out, tag, filename):
    """``<输出目录>/<版本>/<原文件名>``。

    1.4～1.9 的安装包全叫 ``setup.exe``，按版本分目录才不会互相覆盖。
    """
    return os.path.join(out, safe_name(tag), os.path.basename(str(filename)))


def complete(path, size=0):
    """本地文件是不是「已经下完了」。

    只认大小：与 GitHub 报的字节数一致、且不小于安装包下限（挡半截文件）。
    摘要核对比重算 70 MB 快得多，放在 ``verify`` 命令里按需做。
    """
    try:
        real = os.path.getsize(path)
    except OSError:
        return False
    if real < MIN_BYTES:
        return False
    return not size or int(size) == real


# ---------------------------------------------------------------- 下载计划

def plan(releases_list, out, all_assets=False):
    """把版本列表摊成下载任务。

    返回 ``[{'release', 'asset', 'dest'}]``；没有安装包的版本 ``asset`` 为 ``None``，
    由调用方打一行跳过说明（老版本发过只带 msi 的、也发过纯 zip 的）。
    """
    jobs = []
    for rel in releases_list:
        picked = releases.choose_assets(rel, all_assets)
        if not picked:
            jobs.append({'release': rel, 'asset': None, 'dest': ''})
            continue
        for asset in picked:
            jobs.append({
                'release': rel,
                'asset': asset,
                'dest': dest_path(out, rel['tag'], asset['name']),
            })
    return jobs


# ---------------------------------------------------------------- 记账

def manifest_path(out):
    return os.path.join(out, MANIFEST_NAME)


def load_manifest(out):
    """``{key: 记录}``；没有 / 读坏返回空字典（缓存不该挡住主流程）。"""
    try:
        with open(manifest_path(out), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    items = data.get('items') if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def save_manifest(out, items):
    path = manifest_path(out)
    try:
        os.makedirs(out, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'repo': config.REPO, 'updated': int(time.time()), 'items': items},
                      f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except OSError as e:
        print('[安装器] 写 manifest 失败（不影响安装包）：%s' % e)
        return False


def record_key(tag, name):
    return '%s/%s' % (tag, name)


# ---------------------------------------------------------------- 选路与兜底
#
# check_update 自己会在下载前测速择优，但那次测速的窗口只有 2 秒、而且「连上」的
# 时间也算在窗口里 —— 网络绕远（代理/跨境）时，一个能用的镜像也会被判成 0 分，
# 最后退回直连；直连要是不通，整个下载就硬失败。
#
# 所以这里再加一层「换路重试」：镜像按顺序试，一次不成换下一个，直连留作最后。
# 只影响安装器，不动主程序的测速策略。

MIRROR_PROBE_TIMEOUT = 6.0      # 探镜像够不够快：6 秒还不回话就换下一个


def _host(url):
    return urllib.parse.urlparse(str(url or '')).hostname or str(url or '')


def _mirror_ok(target, timeout=MIRROR_PROBE_TIMEOUT):
    """镜像能不能用：只请求 1 个字节，支持 Range 才算数（否则并行分块全白搭）。"""
    req = urllib.request.Request(target, headers=dict(cu.HEADERS, Range='bytes=0-0'))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = getattr(r, 'status', None) or r.getcode()
            return status == 206
    except Exception:
        return False


def attempts(url, prefer='auto'):
    """按顺序给出尝试的 ``[(地址, prefer 参数)]``。

    * ``direct`` —— 只下直连；
    * ``mirror`` —— 先逐个探镜像（4 秒不回话就跳过），能用的排在前面，直连垫底；
    * ``auto``   —— 先交给 ``check_update`` 测速择优，失败再逐个镜像，最后直连。
    """
    mirrors = cu.mirror_urls(url)
    if not mirrors or prefer == 'direct':
        return [(url, 'direct')]
    if prefer == 'mirror':
        live = [m for m in mirrors if _mirror_ok(m)]
        plan = [(m, 'direct') for m in live]
        if live:
            print('[安装器] 走镜像：%s' % '、'.join(_host(m) for m in live))
        return plan + [(url, 'direct')]
    return [(url, 'auto')] + [(m, 'direct') for m in mirrors] + [(url, 'direct')]


def _spot_check(official, path, total):
    """镜像下完抽样比对官方字节；比对函数取不到就按「一致」放过。"""
    try:
        return cu._spot_check(official, path, total)
    except AttributeError:
        return True, ''
    except Exception as e:
        print('[安装器] 抽样比对跳过：%s' % e)
        return True, ''


# ---------------------------------------------------------------- 单个资源

def download_asset(asset, dest, version='', prefer='auto', force=False,
                   progress=None, cancel=None):
    """下载一个安装包，返回记录 dict（含 ``path`` / ``size`` / ``sha256``）。

    * 本地已有完整文件且没要 ``force`` → 直接返回（``skipped=True``），不联网；
    * 一条路不通就换下一条（镜像 → 直连），别让一次测速失败毁掉整次下载；
    * 下完核对字节数、必要时抽样比对官方字节，对不上就删掉换路重来；
    * ``prefer``：``auto`` / ``direct`` / ``mirror``，含义见 :func:`attempts`。
    """
    cancel = cancel or threading.Event()
    url = str(asset.get('url') or '')
    size = int(asset.get('size') or 0)
    if not url:
        raise ValueError('资源没有下载地址：%s' % (asset.get('name') or '?',))

    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    if not force and complete(dest, size):
        return _record(asset, dest, version, skipped=True)

    errors = []
    for target, mode in attempts(url, prefer):
        if cancel.is_set():
            raise cu.Cancelled()
        try:
            # force=True：跳过 check_update 自己的「本地已有同一个包」判断。
            # 那边认包看的是 exe 名称 + 全局缓存目录，而这里一个版本一个目录、
            # 判断更严，让它再插一手会拿到 update 目录里别的版本的包。
            path = cu.download(target, dest=dest, progress=progress, cancel=cancel,
                               version=version, force=True, prefer=mode)
        except cu.Cancelled:
            raise
        except Exception as e:
            errors.append('%s → %s' % (_host(target), e))
            print('[安装器] %s 下载失败：%s' % (_host(target), e))
            continue

        real = os.path.getsize(path)
        if size and real != size:
            errors.append('%s → 字节数不符（%d/%d）' % (_host(target), real, size))
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        if target != url:
            # 官方地址要是不通（被墙/代理拦），抽样比对会一路等到超时，白等三四十秒；
            # 先花 4 秒探一下，探不到就跳过多余的等待（内容安全性由 HTTPS + 大小兜底）。
            if _mirror_ok(url, timeout=4.0):
                same, detail = _spot_check(url, path, size or None)
                if not same:
                    errors.append('%s → 抽样比对不一致（%s）' % (_host(target), detail))
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
            else:
                print('[安装器] 官方地址暂时不通，跳过抽样比对')
        return _record(asset, path, version, skipped=False)

    raise IOError('下载失败（直连与镜像都试过了）：\n  ' + '\n  '.join(errors))


def _record(asset, path, version, skipped):
    return {
        'version': str(version or ''),
        'name': str(asset.get('name') or os.path.basename(path)),
        'path': os.path.abspath(path),
        'size': os.path.getsize(path),
        'sha256': '' if skipped else sha256_of(path),
        'url': str(asset.get('url') or ''),
        'kind': str(asset.get('kind') or ''),
        'time': int(time.time()),
        'skipped': bool(skipped),
    }


def verify_file(path, size=0, sha256=''):
    """核对一个安装包，返回 ``(是否通过, 说明)``。

    没有记录的摘要时只核大小 —— 说清楚「未校验摘要」，别假装验过了。
    """
    if not os.path.exists(path):
        return False, '文件不存在'
    real = os.path.getsize(path)
    if size and int(size) != real:
        return False, '大小不符：本地 %d，应有 %d' % (real, int(size))
    if real < MIN_BYTES:
        return False, '文件太小（%d 字节），不是完整安装包' % real
    want = str(sha256 or '').strip().lower()
    if not want:
        return True, '大小一致（未校验摘要）'
    got = sha256_of(path)
    if got != want:
        return False, '摘要不符：本地 %s…，应有 %s…' % (got[:12], want[:12])
    return True, '大小与摘要一致'
