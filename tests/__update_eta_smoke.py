# -*- coding: utf-8 -*-
"""剩余时间估算冒烟：EtaEstimator 不该给出大幅跳变的「剩余时间」。

背景：进度回调约 10 Hz，短窗速度前后两帧差一倍很常见；直接拿
``(总长 - 已下载) / 短窗速度`` 算剩余时间，会来回跳几十秒。

用法：python tests/__update_eta_smoke.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from f_hamlog import check_update as cu       # noqa: E402

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))
    print('%s  %s  %s' % ('PASS' if cond else 'FAIL', name, extra))


class Clock:
    """可控时钟：模拟 10 Hz 的进度回调。"""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


TICK = 0.1
TOTAL = 20 << 20            # 20 MB


def simulate(rates, total=TOTAL, tick=TICK):
    """按每帧增量喂数据，返回 (平滑后的 eta 列表, 朴素 eta 列表)。"""
    clock = Clock()
    est = cu.EtaEstimator(clock=clock)
    smooth, naive = [], []
    done = 0
    prev_done, prev_t = 0, 0.0
    for n in rates:
        clock.t += tick
        done = min(total, done + n)
        v = est.update(done, total)
        if v is not None:
            smooth.append(v)
        # 朴素做法：用这一帧的瞬时速度
        dt = clock.t - prev_t
        inst = (done - prev_done) / dt if dt > 0 else 0
        naive.append((total - done) / inst if inst > 0 else 0.0)
        prev_done, prev_t = done, clock.t
        if done >= total:
            break
    return smooth, naive


def jumps(seq):
    """相邻两帧的最大跳变（绝对值，秒）。"""
    return max((abs(b - a) for a, b in zip(seq, seq[1:])), default=0.0)


def rises(seq):
    """相邻两帧里「往上跳」的最大幅度（秒）。"""
    return max((b - a for a, b in zip(seq, seq[1:])), default=0.0)


# ---------------------------------------------------------------- A. 预热
clock = Clock()
est = cu.EtaEstimator(clock=clock)
ok('A1 预热期不报剩余时间', est.update(1 << 20, TOTAL) is None)
clock.t += 0.3
ok('A2 不到 warmup 仍不报', est.update(2 << 20, TOTAL) is None)
clock.t += 1.0
v = est.update(3 << 20, TOTAL)
ok('A3 warmup 后给出估算', isinstance(v, float) and v > 0, '%r' % v)
ok('A4 总长未知返回 None', cu.EtaEstimator(clock=clock).update(1 << 20, 0) is None)

# ---------------------------------------------------------------- B. 匀速
rates = [200 << 10] * 200      # 每帧 200 KB @0.1s → 2 MB/s，20 MB 约 10 秒
smooth, naive = simulate(rates)
ok('B1 匀速下估算准确', abs(smooth[len(smooth) // 2] - (TOTAL - (len(smooth) // 2 + 1) * (200 << 10)) / (2 << 20)) < 1.5,
   '中位估算 %.1f 秒' % smooth[len(smooth) // 2])
ok('B2 匀速下单调下降', rises(smooth) <= 0.0, '最大上跳 %.2f 秒' % rises(smooth))
ok('B3 匀速下无明显跳变', jumps(smooth) <= 1.5, '最大跳变 %.2f 秒' % jumps(smooth))
ok('B4 结尾剩余时间趋近 0', smooth[-1] < 3.0, '%.2f 秒' % smooth[-1])

# ---------------------------------------------------------------- C. 抖动（本机的真实情况）
# 快慢交替：一帧 400 KB、一帧 60 KB，平均仍约 2.3 MB/s，但瞬时速度差 6 倍。
rates = ([400 << 10, 60 << 10] * 100)
smooth, naive = simulate(rates)
ok('C1 抖动下剩余时间不上跳', rises(smooth) <= 0.0, '最大上跳 %.2f 秒' % rises(smooth))
ok('C2 抖动下最大跳变 ≤ 3 秒', jumps(smooth) <= 3.0, '平滑 %.2f 秒 / 朴素 %.1f 秒'
   % (jumps(smooth), jumps(naive)))
ok('C3 明显优于朴素算法', jumps(naive) > jumps(smooth) * 3,
   '朴素 %.1f 秒 vs 平滑 %.2f 秒' % (jumps(naive), jumps(smooth)))
ok('C4 抖动下仍在倒数', smooth[-1] < smooth[0] / 3, '%.1f → %.1f 秒' % (smooth[0], smooth[-1]))

# ---------------------------------------------------------------- D. 真的变慢了
# 60 MB 起步 3 MB/s（剩约 20 秒），4 秒后掉到 0.6 MB/s：剩余时间该往上走，但要慢慢走。
rates = [300 << 10] * 40 + [60 << 10] * 120
smooth, _ = simulate(rates, total=60 << 20)
after = smooth[45:]                     # 掉速后一段
ok('D1 持续掉速后上调估算', max(after) > smooth[35] + 2.0,
   '掉速前 %.1f 秒 → 掉速后最高 %.1f 秒' % (smooth[35], max(after)))
ok('D2 上调也不是一帧跳上去', jumps(smooth) <= max(3.0, smooth[0] * 0.05),
   '最大跳变 %.2f 秒' % jumps(smooth))

# ---------------------------------------------------------------- E. 分段重下（done 变小）
clock = Clock()
est = cu.EtaEstimator(clock=clock)
done = 0
prev = None
for _ in range(20):
    clock.t += TICK
    done += 100 << 10
    prev = est.update(done, TOTAL)
clock.t += TICK
back = est.update(done - (300 << 10), TOTAL)      # 某段重下，done 回退 300 KB
ok('E1 回退当帧保留原估算（不跳、不消失）',
   back is not None and prev is not None and abs(back - prev) < 0.01,
   '回退前 %s → 回退后 %s' % (prev, back))
vals = []
for _ in range(30):
    clock.t += TICK
    done += 100 << 10
    v = est.update(done, TOTAL)
    if v is not None:
        vals.append(v)
ok('E2 回退后仍给正数估算', bool(vals) and min(vals) > 0, '最小 %.1f 秒' % (min(vals) or -1))
ok('E3 回退后不上跳', rises(vals) <= 0.0, '最大上跳 %.2f 秒' % rises(vals))

# ---------------------------------------------------------------- F. 显示层（format_eta）
ok('F1 60 秒内显示 mm:ss', cu.format_eta(52) == '00:52', cu.format_eta(52))
ok('F2 超 1 小时显示 hh:mm:ss', cu.format_eta(3723) == '01:02:03', cu.format_eta(3723))
ok('F3 负数/None 不显示', cu.format_eta(-1) == '' and cu.format_eta(None) == '')
ok('F4 估算值可转成文案', bool(cu.format_eta(smooth[10])), cu.format_eta(smooth[10]))

# ---------------------------------------------------------------- G. 真实尺度（70 MB / 1 MB/s）
# 这一节看「准不准」，前面几节只看「稳不稳」。
BIG = 70 << 20
rnd = __import__('random').Random(11)
rates = [int((1 << 20) // 10 * (0.7 + 0.6 * rnd.random())) for _ in range(200)]   # 每帧 ~100 KB ±30%
clock = Clock()
est = cu.EtaEstimator(clock=clock)
done, prev, rows = 0, 0, []
while done < BIG:
    clock.t += TICK
    done = min(BIG, done + rates[len(rows) % len(rates)])
    v = est.update(done, BIG)
    if v is not None:
        rows.append((clock.t, v, (BIG - done) / float(1 << 20)))     # (时刻, 估算秒, 真实剩余秒)
    prev = done
ok('G1 覆盖到下载尾声', bool(rows) and done == BIG and len(rows) > 500,
   '%d 帧，最后一帧估算 %.2f 秒' % (len(rows), rows[-1][1] if rows else -1))
mid = rows[len(rows) // 2]
ok('G2 中途估算接近真实', abs(mid[1] - mid[2]) <= mid[2] * 0.25,
   '进度 %.0f 秒处：估算 %.1f 秒，真实约 %.1f 秒' % (mid[0], mid[1], mid[2]))
tail = [r for r in rows if r[2] < 5.0]
ok('G3 尾声估算不早归零', bool(tail) and max(r[1] for r in tail) >= 3.0,
   '真实剩 <5 秒时最高估算 %.1f 秒' % (max((r[1] for r in tail), default=-1)))
ok('G4 全程最大跳变 ≤ 6 秒', jumps([r[1] for r in rows]) <= 6.0,
   '最大跳变 %.2f 秒' % jumps([r[1] for r in rows]))
ok('G5 抖动导致的上调也很小', rises([r[1] for r in rows]) <= 3.0,
   '最大上跳 %.2f 秒（占全程 %.0f 秒的 %.1f%%）'
   % (rises([r[1] for r in rows]), rows[0][1] or 1,
      rises([r[1] for r in rows]) * 100.0 / (rows[0][1] or 1)))

bad = [r for r in results if r[0] == 'FAIL']
print('\n通过 %d / %d' % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
