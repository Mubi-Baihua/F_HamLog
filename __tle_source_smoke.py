# -*- coding: utf-8 -*-
"""数据源 / 按编号增量更新 的离线烟测（不联网）。

覆盖：
  1. normalize_tle_sources / load_tle_sources 的容错与规整；
  2. merge_tle_texts 的多源优先级（靠前优先）；
  3. fetch_amateur_tle 多源合并 + 与旧缓存按编号合并（旧卫星保留）；
  4. merge_update_satellites 的「同编号更新 / 新编号追加 / 旧的其他保留」；
  5. satellites_to_tle_text ↔ parse_tle_text 往返；
  6. MAX_SELECTED_SATELLITES == 250 与裁剪语义。
"""

import io
import os
import sys
import tempfile

import satellite_pred as sp

RESULT = []


def ok(name, cond, extra=''):
    RESULT.append(('PASS' if cond else 'FAIL', name, extra))
    print(('PASS' if cond else 'FAIL'), '-', name, extra)


# ---- 构造 TLE 文本的小工具 -------------------------------------------------

def tle(name, num, epoch, inc=51.6):
    l1 = ('1 %05dU 98067A   %s  .00010000  00000-0  20000-3 0  9990'
          % (num, epoch))
    l2 = ('2 %05d  %7.4f 170.0000 0006000  70.0000 290.0000 15.50000000 10009'
          % (num, inc))
    return '%s\n%s\n%s\n' % (name, l1, l2)


S1_OLD = tle('SAT-1', 1, '24001.50000000')     # 编号 1，旧历元
S1_NEW = tle('SAT-1', 1, '26268.50000000')     # 编号 1，新历元
S2 = tle('SAT-2', 2, '26268.10000000')
S3 = tle('SAT-3', 3, '26268.20000000')
ID = lambda t: t.splitlines()[1][2:7].strip()  # noqa: E731

print('=' * 72)
print('1. normalize_tle_sources / load_tle_sources')
print('=' * 72)
ok('None → 内置默认', sp.normalize_tle_sources(None) == list(sp.DEFAULT_TLE_SOURCES))
ok('空列表 → 内置默认', sp.normalize_tle_sources([]) == list(sp.DEFAULT_TLE_SOURCES))
ok('默认值为 Celestrak 全量活动卫星',
   sp.DEFAULT_TLE_SOURCES == (sp.CELESTRAK_ACTIVE_URL,)
   and 'GROUP=active' in sp.DEFAULT_TLE_SOURCES[0])
_dup = sp.normalize_tle_sources(['  https://a/x.txt ', '', 'https://a/x.txt',
                                 'https://b/y.txt', '# 注释'])
ok('去空白/去重/忽略空项与注释',
   _dup == ['https://a/x.txt', 'https://b/y.txt'], str(_dup))
ok('单个字符串按一个地址处理',
   sp.normalize_tle_sources(' https://c/z.txt ') == ['https://c/z.txt'])

_old_path = sp.SETTINGS_PATH
_old_src = sp.TLE_SOURCES_PATH
_tmpdir = tempfile.mkdtemp(prefix='fhl_tle_src_')
_tmp_settings = os.path.join(_tmpdir, 'm_xml.txt')
_tmp_src = os.path.join(_tmpdir, 'tle_sources.txt')   # 不创建 → 走旧键分支
try:
    sp.SETTINGS_PATH = _tmp_settings
    sp.TLE_SOURCES_PATH = _tmp_src
    with open(_tmp_settings, 'w', encoding='utf-8') as f:
        f.write(str({'sat_tle_sources': ['https://p/1.txt', 'https://q/2.txt']}))
    ok('读设置里的数据源（保序）',
       sp.load_tle_sources() == ['https://p/1.txt', 'https://q/2.txt'])
    with open(_tmp_settings, 'w', encoding='utf-8') as f:
        f.write(str({'m_call': 'BI8SQL'}))
    ok('设置里没有该键 → 默认', sp.load_tle_sources() == list(sp.DEFAULT_TLE_SOURCES))
    with open(_tmp_settings, 'w', encoding='utf-8') as f:
        f.write('不是合法 dict {')
    ok('设置损坏 → 默认（不抛异常）',
       sp.load_tle_sources() == list(sp.DEFAULT_TLE_SOURCES))
finally:
    sp.SETTINGS_PATH = _old_path
    sp.TLE_SOURCES_PATH = _old_src

print()
print('=' * 72)
print('2. merge_tle_texts —— 靠前的数据源优先')
print('=' * 72)
merged = sp.merge_tle_texts(S1_OLD, S1_NEW, S2)
recs = list(sp.iter_tle_records(merged))
ok('三个源（编号 1 重复）合并为 2 条', len(recs) == 2, str(len(recs)))
d = {r[0]: r for r in recs}
ok('编号 1 取靠前源的旧历元（优先级生效）',
   '24001.50000000' in d['1'][2], d['1'][2])
ok('编号 2 正常并入', '2' in d)
merged2 = sp.merge_tle_texts(S1_NEW, S1_OLD)
ok('交换顺序后编号 1 取新历元',
   '26268.50000000' in list(sp.iter_tle_records(merged2))[0][2])
ok('空文本安全', sp.merge_tle_texts('', None) == '')
ok('_merge_tle_texts 兼容旧接口',
   sp._merge_tle_texts([S1_OLD, S2]) == sp.merge_tle_texts(S1_OLD, S2))

print()
print('=' * 72)
print('3. fetch_amateur_tle —— 多源合并 + 旧缓存按编号保留（mock 联网）')
print('=' * 72)


class _FakeResp(object):
    def __init__(self, body):
        self._body = body.encode('utf-8')
        self.headers = {'Content-Length': str(len(self._body))}

    def read(self, n=-1):
        if n is None or n < 0:
            out, self._body = self._body, b''
            return out
        out, self._body = self._body[:n], self._body[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener(object):
    """按 URL 返回预置内容；未登记的 URL 抛异常（模拟该源不可用）。"""

    def __init__(self, table):
        self.table = table
        self.requested = []

    def urlopen(self, req, timeout=None):
        url = req.full_url if hasattr(req, 'full_url') else req
        self.requested.append(url)
        if url not in self.table:
            raise OSError('模拟网络错误：%s' % url)
        return _FakeResp(self.table[url])


_cache = os.path.join(_tmpdir, 'amateur.tle')
# 旧缓存里已有 编号1(旧) / 编号2 —— 其中编号 2 本次两个源都没下到，必须保留
with open(_cache, 'w', encoding='utf-8') as f:
    f.write(S1_OLD + S2)

_src_a = 'https://src-a/all.txt'
_src_b = 'https://src-b/all.txt'
_fake = _FakeOpener({_src_a: S1_NEW + S3,          # 源 A：编号 1(新) + 编号 3
                     _src_b: S1_OLD + S2})         # 源 B：编号 1(旧) + 编号 2
_real_opener = sp.urllib.request.urlopen
sp.urllib.request.urlopen = _fake.urlopen
try:
    progress_msgs = []
    pcts = []
    text = sp.fetch_amateur_tle(
        cache_path=_cache, force=True, sources=[_src_a, _src_b],
        progress=progress_msgs.append, progress_pct=pcts.append)
finally:
    sp.urllib.request.urlopen = _real_opener

recs = {r[0]: r for r in sp.iter_tle_records(text)}
ok('两个源都按顺序被请求', _fake.requested == [_src_a, _src_b], str(_fake.requested))
ok('结果含 3 颗（1/2/3）', set(recs) == {'1', '2', '3'}, str(sorted(recs)))
ok('编号 1 取靠前源 A 的新历元', '26268.50000000' in recs['1'][2])
ok('编号 2（本次没下到）来自旧缓存 → 被保留', '2' in recs)
ok('编号 3（新增）已并入', '3' in recs)
_cache_ids = {r[0] for r in sp.iter_tle_records(
    open(_cache, encoding='utf-8').read())}
ok('缓存文件已写入合并结果', _cache_ids == {'1', '2', '3'}, str(sorted(_cache_ids)))
ok('进度回调覆盖 0..100', bool(pcts) and pcts[0] == 0 and pcts[-1] == 100,
   str(pcts[:3]) + '…' + str(pcts[-2:]))
ok('进度文本有内容', any('数据源' in m or '合并' in m for m in progress_msgs))

# 全部源都失败 → 抛出且不清空旧缓存
before = open(_cache, encoding='utf-8').read()
_fake2 = _FakeOpener({})
sp.urllib.request.urlopen = _fake2.urlopen
try:
    try:
        sp.fetch_amateur_tle(cache_path=_cache, force=True,
                             sources=['https://down/1.txt', 'https://down/2.txt'])
        raised = False
    except Exception as e:
        raised = '全部星历数据源都下载失败' in str(e)
finally:
    sp.urllib.request.urlopen = _real_opener
ok('全部源失败时抛错', raised)
ok('失败时不动旧缓存', open(_cache, encoding='utf-8').read() == before)

# 部分源失败 → 用成功的那个，不报错
_fake3 = _FakeOpener({_src_b: S3})
sp.urllib.request.urlopen = _fake3.urlopen
try:
    text2 = sp.fetch_amateur_tle(cache_path=_cache, force=True,
                                 sources=['https://bad/x.txt', _src_b])
finally:
    sp.urllib.request.urlopen = _real_opener
ok('部分源失败仍能出结果', set(r[0] for r in sp.iter_tle_records(text2)) >= {'3'})

print()
print('=' * 72)
print('4. merge_update_satellites —— 按编号增量更新')
print('=' * 72)
existing = sp.parse_tle_text(S1_OLD + S2)
incoming = sp.parse_tle_text(S1_NEW + S3)
merged_sats, n_upd, n_add = sp.merge_update_satellites(existing, incoming)
ok('顺序：原有在前，新增追加', [n for n, _ in merged_sats] == ['SAT-1', 'SAT-2', 'SAT-3'],
   str([n for n, _ in merged_sats]))
ok('更新 1 颗 / 新增 1 颗', (n_upd, n_add) == (1, 1), '%s/%s' % (n_upd, n_add))
ok('同编号被替换为新数据',
   '26268.50000000' in merged_sats[0][1].line1, merged_sats[0][1].line1)
ok('旧的、文件中没有的编号被保留（SAT-2）', 'SAT-2' in [n for n, _ in merged_sats])
ok('sat_key 用 NORAD 编号', sp.sat_key(existing[0][1]) == ('num', '1'))
ok('空输入安全',
   sp.merge_update_satellites(None, None) == ([], 0, 0))

print()
print('=' * 72)
print('5. TLE 文本序列化往返')
print('=' * 72)
sats = sp.parse_tle_text(S1_NEW + S2 + S3)
text = sp.satellites_to_tle_text(sats)
back = sp.parse_tle_text(text)
ok('往返后数量一致', len(back) == 3, str(len(back)))
ok('往返后名称一致', [n for n, _ in back] == [n for n, _ in sats])
ok('往返后 line1 一致',
   [s.line1 for _, s in back] == [s.line1 for _, s in sats])
ok('Satrec 保留原始两行', all(s.line1.startswith('1 ') and s.line2.startswith('2 ')
                          for _, s in sats))
_out = os.path.join(_tmpdir, 'out.tle')
ok('write_tle_cache 写入成功',
   sp.write_tle_cache(sats, _out) > 0
   and len(sp.parse_tle_text(open(_out, encoding='utf-8').read())) == 3)
ok('空列表不写（返回 0）', sp.write_tle_cache([], _out) == 0)

print()
print('=' * 72)
print('6. 自选卫星上限 = 250')
print('=' * 72)
ok('MAX_SELECTED_SATELLITES == 250', sp.MAX_SELECTED_SATELLITES == 250,
   str(sp.MAX_SELECTED_SATELLITES))
big = {'S%04d' % i for i in range(400)}
keep, over = sp.clamp_selected_count(big)
ok('400 颗裁到 250', len(keep) == 250 and over == 150, '%d/%d' % (len(keep), over))
ok('裁剪取排序后前 250', keep == set(sorted(big)[:250]))

print()
print('=' * 72)
failed = [r for r in RESULT if r[0] == 'FAIL']
print('总计 %d 项，失败 %d 项' % (len(RESULT), len(failed)))
for r in failed:
    print('  FAIL:', r[1], r[2])
print('RESULT:', 'ALL PASS' if not failed else 'HAS FAILURES')
sys.exit(1 if failed else 0)
