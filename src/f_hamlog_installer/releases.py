# -*- coding: utf-8 -*-
"""把 GitHub 的原始 release JSON 整理成「版本 + 安装包」两件事。

GitHub 返回的字段一大坨（正文、作者、上传者、各种 URL），这里只留用得上的，
顺手把「哪个资源才是 F HamLog 的安装包」判掉 —— 仓库里还有服务端 exe、
便携版 zip、以及 1.x 时代名字很朴素（就叫 ``setup.exe``）的安装包。
"""

import os
import re

# 名字里带这些词的资源不是客户端安装包：
#   新命名 F_HamLog_Remote_Log_Server_2.0.0.exe
#   旧命名 F.HamLog.Remote.Log.Server.1.1.0.exe / Remote.Log.Server.for.F.HamLog.1.1.0.exe
_SERVER_WORDS = ('remote', 'server')

KIND_SETUP = 'setup'        # Inno Setup 安装包（exe）
KIND_MSI = 'msi'            # 1.x 时代的 MSI 安装包
KIND_PORTABLE = 'portable'  # 免安装 zip
KIND_SERVER = 'server'      # 多人日志服务端，不是客户端
KIND_OTHER = 'other'

_ALL_KINDS = (KIND_SETUP, KIND_MSI, KIND_PORTABLE, KIND_SERVER, KIND_OTHER)

# 1.x 的 ``setup.exe`` 只有 550 KB —— 那是个联网下载器，不是完整安装包；
# 同一版本里的 msi 才是全套（33～64 MB）。小于这个尺寸的 setup 视为「壳」。
TINY_SETUP_BYTES = 1 << 20


def version_key(tag):
    """``'2.9.1'`` / ``'v1.0.0'`` → ``(2, 9, 1)``；认不出返回 ``None``。"""
    m = re.match(r'^[vV]?\s*(\d+(?:\.\d+)*)\s*$', str(tag or ''))
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split('.'))


def asset_kind(name):
    """按文件名判资源类型。判错只会多下一次/少下一次，不会下错文件。"""
    low = os.path.basename(str(name or '')).strip().lower()
    if any(word in low for word in _SERVER_WORDS):
        return KIND_SERVER
    if low.endswith('.msi'):
        return KIND_MSI
    if low.endswith('.zip'):
        return KIND_PORTABLE
    if low.endswith('.exe'):
        # 2.x 叫 F.HamLog.2.9.1.setup.exe，1.x 干脆就叫 setup.exe
        if 'setup' in low or 'install' in low or 'f.hamlog' in low or 'f_ham_log' in low:
            return KIND_SETUP
        return KIND_OTHER
    return KIND_OTHER


def normalize(raw):
    """原始 release dict → 本项目内部用的精简结构。"""
    tag = str(raw.get('tag_name') or raw.get('name') or '').strip()
    assets = []
    for a in raw.get('assets') or []:
        name = str(a.get('name') or '').strip()
        if not name:
            continue
        assets.append({
            'name': name,
            'size': int(a.get('size') or 0),
            'url': str(a.get('browser_download_url') or ''),
            'kind': asset_kind(name),
            'downloads': int(a.get('download_count') or 0),
        })
    published = str(raw.get('published_at') or raw.get('created_at') or '')
    return {
        'tag': tag,
        'version': version_key(tag),
        'title': str(raw.get('name') or tag).strip(),
        'published': published,
        'date': published[:10],
        'prerelease': bool(raw.get('prerelease')),
        'draft': bool(raw.get('draft')),
        'page': str(raw.get('html_url') or ''),
        'notes': str(raw.get('body') or ''),
        'assets': assets,
    }


def collect(raw_items, include_prerelease=True):
    """过滤草稿/预览版，按版本号从新到旧排好。

    版本号认不出的条目排最后（但保留：万一以后有 ``2026.1`` 这种写法）。
    """
    out = []
    for raw in raw_items or []:
        rel = normalize(raw)
        if rel['draft']:
            continue
        if rel['prerelease'] and not include_prerelease:
            continue
        out.append(rel)
    out.sort(key=lambda r: (r['version'] or (0,), r['published']), reverse=True)
    return out


def latest(releases):
    """最新正式版；一个正式版都没有时退回最新的（含预览版）。"""
    stable = [r for r in releases if not r['prerelease']]
    for group in (stable, releases):
        if group:
            return max(group, key=lambda r: (r['version'] or (0,), r['published']))
    return None


def app_assets(rel, kinds=(KIND_SETUP, KIND_MSI)):
    """挑出属于客户端的安装包，按 ``kinds`` 里的顺序排（setup 优先于 msi）。

    一个 setup 都没有的版本（比如只发了 msi 的 1.x）由调用方决定要不要退回 msi：
    默认 ``kinds`` 里带 msi，所以 ``app_assets(rel)[0]`` 永远是最合适的那个。
    """
    picked = []
    for kind in kinds:
        picked.extend(a for a in rel['assets'] if a['kind'] == kind)
    return picked


def all_app_assets(rel):
    """所有客户端安装包（含 msi），用于 ``--assets all``。"""
    return app_assets(rel, kinds=(KIND_SETUP, KIND_MSI))


def choose_assets(rel, all_assets=False):
    """给这个版本挑要下哪些包。

    默认一个就够，优先级：

    1. 正常尺寸的 Inno Setup exe（2.x 全是这种，60 MB 上下）；
    2. 1.x 只有 ``setup.exe`` + ``msi``，而那个 setup 只有 550 KB（联网下载器的
       壳，装的时候还得再下一遍，老链接多半已经死了）→ 改挑 msi；
    3. 什么都没有就返回空，让调用方说「这个版本没发安装包」。

    ``all_assets=True`` 时把 exe 和 msi 都算上。
    """
    if all_assets:
        return all_app_assets(rel)
    setups = app_assets(rel, kinds=(KIND_SETUP,))
    msis = app_assets(rel, kinds=(KIND_MSI,))
    big_setups = [a for a in setups if a['size'] >= TINY_SETUP_BYTES]
    if big_setups:
        return [max(big_setups, key=lambda a: a['size'])]
    if msis:
        return [max(msis, key=lambda a: a['size'])]
    if setups:
        return [max(setups, key=lambda a: a['size'])]
    return []


def find(releases, text):
    """按版本号找 release，返回 ``(命中的 release 或 None, 候选列表)``。

    匹配顺序：完整 tag（``2.9.1`` / ``v1.0.0``）→ 版本号相同（``2.9`` 也能找到
    ``2.9.0``）→ tag 前缀。前缀命中多个时**不猜**，把候选交回去让用户看清。
    """
    want = str(text or '').strip()
    if not want:
        return None, []
    low = want.lower()
    for rel in releases:
        if rel['tag'].lower() == low:
            return rel, [rel]
    key = version_key(want)
    if key is not None:
        same = [r for r in releases if r['version'] == key]
        if len(same) == 1:
            return same[0], same
        if len(same) > 1:
            return None, same
    prefix = [r for r in releases if r['tag'].lower().startswith(low)
              or low.startswith(r['tag'].lower())]
    if len(prefix) == 1:
        return prefix[0], prefix
    return None, prefix
