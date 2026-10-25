# -*- coding: utf-8 -*-
"""check_update 重试逻辑冒烟：不联网验证「重试次数上限 / 退避 / 不可重试立即放弃」。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from f_hamlog import check_update as cu

calls = []
cu.time.sleep = lambda d: calls.append(('sleep', round(d, 2)))   # 不真的等


def patch(fn):
    calls.clear()
    cu.urllib.request.urlopen = fn


# A. 网络层一直失败 → 1 次首发 + 5 次重试，退避 0.5/1/2/4/5
def fail_net(req, timeout=None):
    calls.append(('open', req.full_url))
    raise cu.urllib.error.URLError('connection refused')

patch(fail_net)
text = cu.main()
opens = [c for c in calls if c[0] == 'open']
sleeps = [c[1] for c in calls if c[0] == 'sleep']
print('A 网络错误: 请求=%d 退避=%s 返回=%r' % (len(opens), sleeps, text))
assert len(opens) == 6, '应为 1 次首发 + 5 次重试'
assert sleeps == [0.5, 1.0, 2.0, 4.0, 5.0], '退避序列不对'
assert text == 'e', '全失败应返回 e'


# B. 404 属于「再试也一样」→ 只请求 1 次
def fail_404(req, timeout=None):
    calls.append(('open', req.full_url))
    raise cu.urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)

patch(fail_404)
text = cu.main()
opens = [c for c in calls if c[0] == 'open']
print('B 404: 请求=%d 返回=%r' % (len(opens), text))
assert len(opens) == 1 and text == 'e'


# C. 503 可重试 → 重试到上限
def fail_503(req, timeout=None):
    calls.append(('open', req.full_url))
    raise cu.urllib.error.HTTPError(req.full_url, 503, 'Service Unavailable', {}, None)

patch(fail_503)
cu.main()
opens = [c for c in calls if c[0] == 'open']
print('C 503: 请求=%d' % len(opens))
assert len(opens) == 6


# D. 前 2 次抖动、第 3 次成功 → 立刻返回，不再重试
class FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'2.7.0 https://example/x.exe\n'


state = {'n': 0}


def flaky(req, timeout=None):
    calls.append(('open', req.full_url))
    state['n'] += 1
    if state['n'] < 3:
        raise cu.urllib.error.URLError('temporary failure')
    return FakeResp()

patch(flaky)
text = cu.main()
opens = [c for c in calls if c[0] == 'open']
print('D 抖动后成功: 请求=%d 返回=%r' % (len(opens), text))
assert len(opens) == 3


# E. 远端版本比本地新 → 返回 (版本, 地址)
class NewResp(FakeResp):
    def read(self):
        return '2.9.0 https://example/setup.exe\n'.encode('utf-8')

patch(lambda req, timeout=None: (calls.append(('open', req.full_url)), NewResp())[1])
info = cu.check()
print('E 有新版本: status=%r version=%r url=%r' % (info['status'], info['version'], info['url']))
assert info['status'] == 'new' and info['version'] == '2.9.0'
assert info['url'] == 'https://example/setup.exe'


# F. 远端版本比本地旧 → 视为已是最新，别把用户往回拽
class OldResp(FakeResp):
    def read(self):
        return b'2.6.0 https://example/setup.exe\n'

patch(lambda req, timeout=None: (calls.append(('open', req.full_url)), OldResp())[1])
assert cu.check()['status'] == 'latest'
print('F 远端更旧: status=latest')


# G. 预览版：一个请求都不发，且永不自我更新
calls.clear()
saved = cu.__version__
cu.__version__ = '日常开发Preview UTC-20261024-2111 2.8.0'
patch(lambda req, timeout=None: (_ for _ in ()).throw(AssertionError('预览版不该联网')))
print('G 预览版: main=%r check=%r 请求=%d' % (cu.main(), cu.check()['status'], len(calls)))
assert cu.main() == 'p' and cu.check()['status'] == 'preview' and not calls
cu.__version__ = saved

print('OK 全部通过')
