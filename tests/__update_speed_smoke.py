# -*- coding: utf-8 -*-
"""下载速度显示冒烟：format_size / format_speed / Speedometer（纯标准库，不用 Qt）。

用法：python tests/__update_speed_smoke.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from f_hamlog import check_update as cu        # noqa: E402

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


class Clock:
    """可控时钟：Speedometer 的 clock 参数就是给它塞进来的。"""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- 单位换算
ok('A1 字节', cu.format_size(512) == '512 B', cu.format_size(512))
ok('A2 KB', cu.format_size(1536) == '2 KB', cu.format_size(1536))
ok('A3 MB', cu.format_size(12345678) == '11.8 MB', cu.format_size(12345678))
ok('A4 GB', cu.format_size(3 << 30) == '3.00 GB', cu.format_size(3 << 30))
ok('A5 None 当 0', cu.format_size(None) == '0 B', cu.format_size(None))
ok('A6 速度带 /s', cu.format_speed(2 << 20) == '2.0 MB/s', cu.format_speed(2 << 20))
ok('A7 慢速走 KB', cu.format_speed(28 * 1024) == '28 KB/s', cu.format_speed(28 * 1024))

# ---------------------------------------------------------------- 剩余时间
ok('A8 秒级', cu.format_eta(42) == '00:42', cu.format_eta(42))
ok('A9 四舍五入', cu.format_eta(83.4) == '01:23', cu.format_eta(83.4))
ok('A10 零', cu.format_eta(0) == '00:00', cu.format_eta(0))
ok('A11 带小时', cu.format_eta(3723) == '01:02:03', cu.format_eta(3723))
ok('A12 取不到返回空串', cu.format_eta(None) == '' and cu.format_eta(-5) == '',
   repr(cu.format_eta(None)))
ok('A13 超长兜底', cu.format_eta(10 ** 9) == '99:59:59', cu.format_eta(10 ** 9))

# ---------------------------------------------------------------- 速度估算
clock = Clock()
sp = cu.Speedometer(window=1.0, clock=clock)
ok('B1 单样本速度为 0', sp.update(0) == 0.0, sp.update(0))

# 每 0.1 秒 200 KB → 约 2.0 MB/s
for i in range(1, 11):
    clock.t = i * 0.1
    v = sp.update(i * 204800)
expect = 2048000
ok('B2 匀速估算准确', abs(v - expect) < expect * 0.02, '%.0f 字节/秒（期望 %d）' % (v, expect))
ok('B3 显示为 2.0 MB/s', cu.format_speed(v) == '2.0 MB/s', cu.format_speed(v))

# 停顿：done 不再增长 → 窗口滑过后速度掉到 0
clock.t = 3.0
v = sp.update(10 * 204800)
ok('B4 停顿时速度归零', v == 0.0, '%.0f' % v)

# 重下一段（字节退回）→ 清窗，不出负数
clock.t = 3.1
v = sp.update(3 * 102400)
ok('B5 字节回退不为负', v == 0.0, '%.0f' % v)
clock.t = 4.1
v = sp.update(7 * 102400)
ok('B6 回退后重新起算', abs(v - 409600) < 409600 * 0.02, '%.0f 字节/秒' % v)

# 窗口只留最近 1 秒：早期高速不该拖着现在的速度
clock = Clock()
sp = cu.Speedometer(window=1.0, clock=clock)
for i in range(1, 11):
    clock.t = i * 0.1
    sp.update(i * 1048576)          # 前 1 秒 10 MB/s
for i in range(1, 11):              # 后 1 秒 1 MB/s
    clock.t = 1.0 + i * 0.1
    v = sp.update(10 * 1048576 + i * 104857)
ok('B7 窗口滑过后只反映当前速度', abs(v - 1048570) < 1048570 * 0.05, '%.0f 字节/秒' % v)

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
