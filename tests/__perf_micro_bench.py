# -*- coding: utf-8 -*-
"""微基准：大项目各处的真实成本（深拷贝 / 浅拷贝 / JSON / 排序 / 读取）。

用法：python __perf_micro_bench.py [N]
"""
import copy
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from f_hamlog import data_factory as fhlgen   # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
recs = fhlgen.generate_records(N)
print('N = %d，单条字段数 = %d' % (N, len(recs[0])))


def timeit(label, fn, rounds=3):
    fn()  # 预热
    t = time.perf_counter()
    for _ in range(rounds):
        out = fn()
    dt = (time.perf_counter() - t) / rounds
    print('%-30s %.4f s' % (label, dt))
    return out


timeit('copy.deepcopy(file)', lambda: copy.deepcopy(recs))
timeit('[dict(r) for r in file]', lambda: [dict(r) for r in recs])
timeit('[r.copy() for r in file]', lambda: [r.copy() for r in recs])
timeit('list(file) 浅拷贝', lambda: list(recs))
s = timeit('json.dumps(file)', lambda: json.dumps(recs, ensure_ascii=False, default=str))
print('   JSON 体积 = %.1f MB' % (len(s.encode('utf-8')) / 1048576))
timeit('json.loads', lambda: json.loads(s))
timeit('sorted(range,key=date/time)', lambda: sorted(
    range(len(recs)),
    key=lambda i: (recs[i].get('date', ''), recs[i].get('time', ''))))
print('总字符数 = %d' % sum(len(str(v)) for r in recs for v in r.values()))
