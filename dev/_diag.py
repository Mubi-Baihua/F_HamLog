import math
import satellite_pred as sp
from sgp4.api import jday as sgp4_jday
from datetime import datetime, timezone

l1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991"
l2 = "2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000"
sat = sp.twoline2rv(l1, l2, name="ISS (ZARYA)")
observer = (30.0, 114.0, 50.0)
start = datetime(2024, 1, 16, 0, 0, 0, tzinfo=timezone.utc)

# 1) 两种 jday 基准对比
sg_int, sg_fr = sgp4_jday(2024, 1, 16, 0, 0, 0)
mine = sp.datetime_to_jd(start)
print("sgp4 jday sum :", sg_int + sg_fr)
print("mine jd       :", mine)
print("diff          :", (sg_int + sg_fr) - mine)

# 2) epoch 解读
print("jdsatepoch    :", sat.jdsatepoch)
print("epoch decoded :", sp.jd_to_datetime(sat.jdsatepoch))
print("tsince(min)@start via mine jd :", (mine - sat.jdsatepoch) * 1440)

# 3) 细扫描(5s) 找 min_elev=10 的连续段时长
min_elev = 10.0
step = 5.0
jd0 = mine
n = int(24 * 3600 / step)
segments = []
prev_up = None
seg_start = None
for i in range(n + 1):
    jd = jd0 + i * step / 86400.0
    o = sp.observe(sat, jd, observer)
    el = o['elevation'] if o else -90.0
    up = el >= min_elev
    if prev_up is None:
        prev_up = up
        seg_start = jd if up else None
        continue
    if up and not prev_up:
        seg_start = jd
    elif (not up) and prev_up and seg_start is not None:
        segments.append((seg_start, jd))
        seg_start = None
    prev_up = up
print("\n[5s 细扫描] 段数:", len(segments))
for a, b in segments[:4]:
    print("  段 dur(min)=%.2f  AOS=%s" % ((b - a) * 1440.0, sp.jd_to_datetime(a)))

# 4) 二分精化预测对比
passes = sp.predict_passes(sat, observer, start, duration_hours=24, min_elevation_deg=10)
print("\n[predict_passes] 段数:", len(passes))
for p in passes[:4]:
    print("  dur(min)=%.2f  AOS=%s maxel=%.1f" % (p['duration_sec'] / 60.0, p['aos'], p['max_elevation']))

# 5) 验证二分 AOS/LOS 时刻仰角应≈min_elev
for p in passes[:1]:
    oa = sp.observe(sat, p['aos_jd'], observer)
    ol = sp.observe(sat, p['los_jd'], observer)
    print("\nAOS 时刻仰角:", oa['elevation'] if oa else None)
    print("LOS 时刻仰角:", ol['elevation'] if ol else None)
