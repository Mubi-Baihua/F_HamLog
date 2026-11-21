# -*- coding: utf-8 -*-
"""命令行界面：``python -m f_hamlog_installer``（或 ``f-hamlog-installer``）。

五个动作，够用就好：

    list       列出 GitHub 上所有版本（顺带标出本地已下好的）
    latest     只看最新版本，不下载
    download   下指定版本；不带参数=最新，``--all``=所有版本
    install    下载并安装（不带参数=最新）
    verify     核对本地已下载的安装包

进度显示复用 ``check_update`` 的测速与剩余时间估算：短窗速度天然乱跳，那套平滑
逻辑已经调过一轮，再写一份只会更难用。
"""

import argparse
import os
import shutil
import sys
import threading
import time

from f_hamlog import check_update as cu

from . import __version__, config, download, github, install, releases

PROG = 'f-hamlog-installer'


class CliError(Exception):
    """给用户看的错误（不用打 traceback 的那种）。"""


# ---------------------------------------------------------------- 进度行

class _Progress:
    """一行滚动进度：``[#####-----] 52%  35.7/68.6 MB  3.1 MB/s  ETA 00:12``。

    总长未知（服务器没给 Content-Length）时退化成「已下载 + 速度」。
    行宽按终端宽度裁，超宽换行会让 ``\\r`` 失效、进度条变成满屏乱码。

    下到 100% 时**立刻换行收尾**：下载器在返回后还会打印「抽样比对 / 走镜像」
    之类的消息，进度行没断行的话，那些字会糊在进度条尾巴上。
    """

    def __init__(self, label, stream=None):
        self.label = label
        self.stream = stream or sys.stdout
        self.speed = cu.Speedometer()
        self.eta = cu.EtaEstimator()
        self._last = 0.0
        self._last_speed = 0.0
        self._width = 0
        self._closed = False

    def _columns(self):
        try:
            return max(40, shutil.get_terminal_size((100, 24)).columns)
        except Exception:
            return 100

    def __call__(self, done, total):
        if self._closed:
            return
        done = int(done or 0)
        total = int(total or 0)
        final = total > 0 and done >= total
        now = time.monotonic()
        if not final:
            if now - self._last < 0.2:
                return
            self._last_speed = self.speed.update(done)
        # 末帧的「当前速度」常被最后的 flush 打成 0，用上一帧的值更可信
        speed = self._last_speed
        eta = self.eta.update(done, total)

        if total > 0:
            pct = done * 100.0 / total
            cells = 20
            filled = int(round(cells * done / total))
            bar = '#' * filled + '-' * (cells - filled)
            line = '  %s [%s] %3.0f%% %s/%s %s' % (
                self.label, bar, pct, cu.format_size(done), cu.format_size(total),
                cu.format_speed(speed))
        else:
            line = '  %s %s %s' % (self.label, cu.format_size(done), cu.format_speed(speed))

        rest = cu.format_eta(eta)
        if rest:
            line += '  ETA ' + rest
        self._write(line)
        if final:
            self._finish()

    def _write(self, line):
        line = line[:self._columns() - 1]
        pad = max(0, self._width - len(line))
        self.stream.write('\r' + line + ' ' * pad)
        self.stream.flush()
        self._width = len(line)

    def _finish(self):
        if self._closed:
            return
        self.stream.write('\n')
        self.stream.flush()
        self._closed = True
        self._width = 0

    def close(self, note=''):
        """收尾：该换行就换行，然后另起一行写结论（不与进度行粘在一起）。"""
        if not self._closed and self._width:
            self._finish()
        if note:
            self.stream.write('  ' + note + '\n')
            self.stream.flush()


# ---------------------------------------------------------------- 小工具

def _prefer(args):
    """``--mirror`` → ``check_update.choose_source`` 认的三种模式。"""
    return {'auto': 'auto', 'on': 'mirror', 'off': 'direct'}.get(
        getattr(args, 'mirror', 'auto'), 'auto')


def _out(args):
    return os.path.abspath(getattr(args, 'out', None) or config.out_dir())


def _load(args, include_prerelease=True):
    raw = github.list_releases(token=getattr(args, 'token', ''),
                               refresh=getattr(args, 'refresh', False),
                               offline=getattr(args, 'offline', False))
    rels = releases.collect(raw, include_prerelease=include_prerelease)
    if not rels:
        raise CliError('GitHub 上没取到任何版本（仓库地址或网络有问题）')
    return rels


def _resolve(rels, text):
    """按用户给的版本号找版本；找不到 / 有歧义都把候选列出来，别猜。"""
    rel, cands = releases.find(rels, text)
    if rel is not None:
        return rel
    if cands:
        raise CliError('「%s」对应多个版本，请写全：%s'
                       % (text, '、'.join(r['tag'] for r in cands)))
    raise CliError('找不到版本「%s」。用 list 看看都有哪些' % text)


def _targets(rels, args):
    """``download`` / ``install`` 要处理哪些版本。

    ``download`` 的位置参数是列表，``install`` 是单个字符串 —— 直接把字符串丢给
    ``list()`` 会拆成一个个字符（'1.9.0' → ['1','.','9',…]），所以先归一化。
    """
    raw = getattr(args, 'version', None) or []
    versions = [raw] if isinstance(raw, str) else list(raw)
    versions = [v for v in versions if v]
    if getattr(args, 'all', False):
        return list(rels)
    if versions:
        return [_resolve(rels, v) for v in versions]
    rel = releases.latest(rels)
    if rel is None:
        raise CliError('没有可安装的版本')
    return [rel]


def _state(out, rel, asset, manifest):
    """本地状态：已下载 / 不完整 / 未下载。"""
    dest = download.dest_path(out, rel['tag'], asset['name'])
    rec = manifest.get(download.record_key(rel['tag'], asset['name']))
    if download.complete(dest, asset.get('size') or 0):
        return '已下载'
    if os.path.exists(dest):
        return '不完整'
    if rec:
        return '记录在册但文件没了'
    return ''


def _print_asset(rel, asset):
    print('  版本 %s  %s（%s）  发布 %s' % (
        rel['tag'], asset['name'], cu.format_size(asset.get('size') or 0),
        rel['date'] or '未知'))


def _width(text):
    """字符串在等宽终端里占几列（中文/全角算 2）。表格对齐用。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in str(text))


def _pad(text, width):
    text = str(text)
    return text + ' ' * max(0, width - _width(text))


def _row(cells, widths):
    """按显示宽度补齐前几列，最后一列不补（行尾不留空格）。"""
    padded = [_pad(text, width) for text, width in zip(cells, widths)]
    return ''.join(padded + [str(c) for c in cells[len(widths):]])


# ---------------------------------------------------------------- 命令

def cmd_list(args):
    rels = _load(args)
    out = _out(args)
    manifest = download.load_manifest(out)
    widths = (10, 8, 12, 12)
    print('目录：%s' % out)
    print('共 %d 个版本%s' % (len(rels), '（来自本地缓存）' if args.offline else ''))
    print()
    print(_row(('版本', '类型', '大小', '发布', '本地'), widths))
    for rel in rels:
        picked = releases.choose_assets(rel)
        flag = rel['tag'] + ('*' if rel['prerelease'] else '')
        if not picked:
            print(_row((flag, '-', '-', rel['date'] or '-', '没发安装包'), widths))
            continue
        asset = picked[0]
        print(_row((flag, asset['kind'], cu.format_size(asset.get('size') or 0),
                    rel['date'] or '-', _state(out, rel, asset, manifest)), widths))
    if any(r['prerelease'] for r in rels):
        print()
        print('* 预览版（prerelease）')
    return 0


def cmd_latest(args):
    rels = _load(args)
    rel = releases.latest(rels)
    if rel is None:
        raise CliError('没有可安装的版本')
    picked = releases.choose_assets(rel)
    print('最新版本：%s%s' % (rel['tag'], '（预览版）' if rel['prerelease'] else ''))
    print('发布：%s' % (rel['date'] or '未知'))
    print('页面：%s' % (rel['page'] or config.RELEASES_URL))
    if not picked:
        print('安装包：这个版本没有发布安装包')
        return 1
    _print_asset(rel, picked[0])
    print('  地址 %s' % picked[0]['url'])
    print('  本地 %s' % download.dest_path(_out(args), rel['tag'], picked[0]['name']))
    return 0


def cmd_download(args):
    rels = _load(args)
    out = _out(args)
    targets = _targets(rels, args)
    jobs = download.plan(targets, out, all_assets=(args.assets == 'all'))

    if args.dry_run:
        for job in jobs:
            if job['asset'] is None:
                print('%s  没有安装包，跳过' % job['release']['tag'])
                continue
            print('%s  %s（%s）→ %s' % (
                job['release']['tag'], job['asset']['name'],
                cu.format_size(job['asset'].get('size') or 0), job['dest']))
        print('合计 %d 个文件，输出目录 %s' % (len([j for j in jobs if j['asset']]), out))
        return 0

    manifest = download.load_manifest(out)
    prefer = _prefer(args)
    saved = skipped = failed = 0
    total = len(jobs)
    for index, job in enumerate(jobs, 1):
        rel, asset = job['release'], job['asset']
        if asset is None:
            print('[%d/%d] %s  没有发布安装包，跳过' % (index, total, rel['tag']))
            continue
        head = '[%d/%d] %s  %s  %s' % (index, total, rel['tag'], asset['name'],
                                       cu.format_size(asset.get('size') or 0))
        print(head)
        bar = _Progress(rel['tag'])
        try:
            rec = download.download_asset(asset, job['dest'], version=rel['tag'],
                                          prefer=prefer, force=args.force,
                                          progress=bar, cancel=threading.Event())
        except cu.Cancelled:
            bar.close('已取消')
            raise
        except Exception as e:
            bar.close('失败：%s' % e)
            failed += 1
            continue
        if rec['skipped']:
            bar.close('本地已有，跳过')
            skipped += 1
        else:
            bar.close('完成')
            saved += 1
        manifest[download.record_key(rel['tag'], rec['name'])] = rec
        download.save_manifest(out, manifest)

    print()
    print('完成：下载 %d，跳过 %d，失败 %d；目录 %s' % (saved, skipped, failed, out))
    return 1 if failed else 0


def cmd_install(args):
    rels = _load(args)
    out = _out(args)
    targets = _targets(rels, args)
    rel = targets[-1]                      # 装最后一个：一次装一个才说得通
    picked = releases.choose_assets(rel)
    if not picked:
        raise CliError('版本 %s 没有发布安装包' % rel['tag'])
    asset = picked[0]
    dest = download.dest_path(out, rel['tag'], asset['name'])

    print('F HamLog %s  %s（%s）' % (rel['tag'], asset['name'],
                                    cu.format_size(asset.get('size') or 0)))
    if args.dry_run:
        print('将下载到 %s 并%s安装' % (dest, '静默' if not args.gui else '交互'))
        return 0

    bar = _Progress(rel['tag'])
    try:
        rec = download.download_asset(asset, dest, version=rel['tag'], prefer=_prefer(args),
                                      force=args.force, progress=bar,
                                      cancel=threading.Event())
    except cu.Cancelled:
        bar.close('已取消')
        raise
    bar.close('本地已有，跳过' if rec['skipped'] else '下载完成')

    ok, detail = download.verify_file(rec['path'], asset.get('size') or 0, rec['sha256'])
    if not ok:
        raise CliError('安装包校验失败：%s' % detail)
    print('校验：%s' % detail)

    if not args.yes and sys.stdin.isatty():
        mode = '静默安装' if not args.gui else '打开安装向导'
        answer = input('开始%s？会弹 UAC 提权（Y/n）：' % mode).strip().lower()
        if answer and answer not in ('y', 'yes', '是', ''):
            print('已取消，安装包留在：%s' % rec['path'])
            return 0

    print('正在启动安装包…')
    try:
        code = install.run(rec['path'], silent=not args.gui, wait=not args.no_wait)
    except OSError as e:
        raise CliError('启动安装包失败：%s' % e)
    if code is None:
        print('已拉起安装包（未等待结束）：%s' % rec['path'])
        return 0
    print(install.code_text(code))
    # 3010 = 装好了但要重启（msi 常见），算成功
    return 0 if code in (0, 3010) else 1


def cmd_verify(args):
    out = _out(args)
    manifest = download.load_manifest(out)
    if not manifest:
        print('本地没有下载记录（%s）' % download.manifest_path(out))
        return 1
    bad = 0
    for key in sorted(manifest):
        rec = manifest[key]
        path = rec.get('path') or ''
        if not os.path.isabs(path):
            path = os.path.join(out, path)
        if not os.path.exists(path):
            # 整个目录被搬过家：按「版本/文件名」重新拼一次，尽量还能找到
            alt = download.dest_path(out, rec.get('version') or key.split('/')[0],
                                     rec.get('name') or '')
            if os.path.exists(alt):
                path = alt
        ok, detail = download.verify_file(path, rec.get('size') or 0, rec.get('sha256') or '')
        print('%-8s %-42s %s' % (rec.get('version') or key.split('/')[0],
                                 rec.get('name') or key,
                                 '正常（%s）' % detail if ok else '异常：' + detail))
        if not ok:
            bad += 1
    print()
    print('共 %d 个，异常 %d 个' % (len(manifest), bad))
    return 1 if bad else 0


def cmd_cache(args):
    if args.action == 'clear':
        print('已清空版本列表缓存' if github.clear_cache() else '本来就没什么可清的')
        return 0
    cached = github.load_cache()
    if not cached:
        print('缓存位置：%s（空）' % github.cache_file())
        return 0
    stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cached.get('time', 0)))
    print('缓存位置：%s' % github.cache_file())
    print('记录时间：%s，共 %d 条' % (stamp, len(cached.get('items') or [])))
    return 0


# ---------------------------------------------------------------- 参数

_COMMON = (
    (('--out',), {'metavar': 'DIR', 'default': None,
                  'help': '历史版本存放目录（默认 %s）' % config.out_dir()}),
    (('--mirror',), {'choices': ('auto', 'on', 'off'), 'default': 'auto',
                     'help': 'GitHub 加速：auto=测速择优（默认），on=强制走镜像，off=只用直连'}),
    (('--token',), {'metavar': 'TOKEN', 'default': '',
                    'help': 'GitHub token，提高接口额度（也能用 GITHUB_TOKEN 环境变量）'}),
    (('--offline',), {'action': 'store_true', 'default': False,
                      'help': '不联网，只用本地缓存的版本列表'}),
    (('--refresh',), {'action': 'store_true', 'default': False,
                      'help': '忽略缓存，重新拉取版本列表'}),
)


def _common_args(parser, top):
    """全局选项既能在命令前写，也能在命令后写。

    写在子命令里的一律 ``default=SUPPRESS``：不给值就不碰顶层已解析的字段，
    否则 ``install --mirror on`` 里的默认值会把 ``--mirror off`` 覆盖掉。
    """
    for names, kw in _COMMON:
        kw = dict(kw)
        if not top:
            kw['default'] = argparse.SUPPRESS
        parser.add_argument(*names, **kw)


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description='F HamLog 安装器：下载最新版并安装，或把 GitHub 上所有版本收下来。',
        epilog='示例：\n'
               '  %s                       下载并安装最新版\n'
               '  %s list                  看所有版本\n'
               '  %s install 2.9.1 --yes   装指定版本，不问\n'
               '  %s download --all        把所有版本的安装包下到本地\n'
               '  %s download --all --mirror on   同上，强制走镜像加速\n'
               '  %s verify                核对本地已下载的安装包\n'
               % ((PROG,) * 6),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version',
                        version='%s %s' % (PROG, __version__))
    _common_args(parser, top=True)

    sub = parser.add_subparsers(dest='command', metavar='命令')

    p = sub.add_parser('list', help='列出 GitHub 上所有版本')
    _common_args(p, top=False)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('latest', help='显示最新版本')
    _common_args(p, top=False)
    p.set_defaults(func=cmd_latest)

    p = sub.add_parser('download', help='下载安装包（不带版本=最新）')
    _common_args(p, top=False)
    p.add_argument('version', nargs='*', help='版本号，可写多个（如 2.9.1 v1.0.0）')
    p.add_argument('--all', action='store_true', help='下载所有版本')
    p.add_argument('--assets', choices=('first', 'all'), default='first',
                   help='每个版本下几个包：first=优先 exe（默认），all=exe 和 msi 都要')
    p.add_argument('--force', action='store_true', help='本地已有也重新下载')
    p.add_argument('--dry-run', action='store_true', help='只列计划，不下载')
    p.set_defaults(func=cmd_download)

    p = sub.add_parser('install', help='下载并安装（不带版本=最新）')
    _common_args(p, top=False)
    p.add_argument('version', nargs='?', help='版本号，默认最新')
    p.add_argument('--gui', action='store_true', help='走安装向导（默认静默安装）')
    p.add_argument('--no-wait', action='store_true', help='拉起安装包就返回，不等装完')
    p.add_argument('--force', action='store_true', help='本地已有也重新下载')
    p.add_argument('--yes', '-y', action='store_true', help='不再确认，直接安装')
    p.add_argument('--dry-run', action='store_true', help='只看会下哪个包，不下载不安装')
    p.set_defaults(func=cmd_install)

    p = sub.add_parser('verify', help='核对本地已下载的安装包')
    _common_args(p, top=False)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser('cache', help='版本列表缓存')
    _common_args(p, top=False)
    p.add_argument('action', nargs='?', choices=('show', 'clear'), default='show')
    p.set_defaults(func=cmd_cache)

    return parser


COMMANDS = ('list', 'latest', 'download', 'install', 'verify', 'cache')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # 什么命令都没写（只给了 --mirror 之类的全局选项，或者干脆没参数）
    # → 按「下载并安装最新版」办，这才是安装器该干的事。
    if not argv:
        argv = ['install']
    elif argv[0] not in COMMANDS and argv[0] not in ('-h', '--help', '--version'):
        argv = ['install'] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    print('%s %s' % (PROG, __version__))
    print('仓库：%s' % config.REPO_URL)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print('\n已取消')
        return 130
    except github.RateLimited as e:
        print('错误：%s' % e)
        return 1
    except (CliError, github.GithubError, cu.Cancelled, OSError, ValueError) as e:
        print('错误：%s' % e)
        return 1
