# -*- coding: utf-8 -*-
"""
satellite_pred.py —— 业余卫星过境预测核心模块

功能：
  1. 解析 TLE（两行根数）；
  2. 使用成熟的第三方库 `skyfield`（基于 Brandon Rhodes 的 sgp4 标准实现
     + 精确地球定向模型）推算卫星位置并完成「观测站地平几何」与「过境事件
     检测」。所有天文计算（SGP4 传播、ECI→ECEF 旋转、格林尼治恒星时、
     仰角/方位求解）都由 skyfield 完成，本模块不再手写任何坐标变换，
     从而保证过境时长、升起/落下时刻与权威结果一致；
  3. 预测未来一段时间内的可见过境（AOS / LOS / 最大仰角 / 方位 / 时长）；
  4. 从 Celestrak 下载业余卫星 TLE 并本地缓存。

依赖：第三方库 skyfield + numpy（pip install skyfield numpy）。
  时标使用 skyfield 内置数据（builtin=True），无需联网即可运行；
  若希望使用更高精度的 IERS 地球定向数据，可在联网环境下让 skyfield
  自行下载并缓存（不影响本模块接口）。

注意：过境检测直接由 skyfield 的 `EarthSatellite.find_events` 完成，
它精确求解仰角穿越最小可见阈值的 AOS/MAX/LOS 时刻，过境时长 =
LOS 时刻 − AOS 时刻（秒级精度），不再依赖粗扫描步长近似。
"""

import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

try:
    from skyfield.api import load, wgs84, EarthSatellite
    _HAVE_SKYFIELD = True
except Exception:  # pragma: no cover
    _HAVE_SKYFIELD = False


# ---------------------------------------------------------------------------
#  应用数据根目录解析（兼容开发模式 / Nuitka 打包后）
# ---------------------------------------------------------------------------

def _app_base_dir():
    """返回应用数据根目录（其下包含 file/ 子目录）。

    优先返回“确实包含 file/ 子目录”的候选目录，这样即便程序从其它目录启动，
    相对路径 file/... 仍能被正确定位。兼容两种运行方式：
      - 开发模式：本模块源码所在目录（CWD 通常也是这里）；
      - Nuitka --standalone 打包后：可执行文件所在目录（file/ 被打包到 exe 旁边）。
    """
    candidates = []
    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    for d in candidates:
        if os.path.isdir(os.path.join(d, 'file')):
            return d
    # 兜底：返回 exe 目录（即便没有 file/，路径也稳定，便于排查）
    return candidates[0] if candidates else os.getcwd()


def app_path(rel):
    """把 file/xxx 这类数据相对路径解析为基于应用根目录的绝对路径。"""
    if os.path.isabs(rel):
        return rel
    return os.path.normpath(os.path.join(_app_base_dir(), rel))


# ---------------------------------------------------------------------------
#  预测时长上限
# ---------------------------------------------------------------------------

# 过境预测的最长时间跨度（小时）。240 小时 = 10 天，已接近 TLE 的有效精度边界，
# 再长的外推误差会明显增大，因此统一在此处限制。
MAX_PREDICT_HOURS = 240
MIN_PREDICT_HOURS = 1


def clamp_predict_hours(hours, default=24.0):
    """把用户输入的预测时长钳制到 [MIN_PREDICT_HOURS, MAX_PREDICT_HOURS]。

    超过 240 小时一律按 240 小时处理；非法/空输入回退到 default。
    """
    try:
        h = float(hours)
    except (TypeError, ValueError):
        h = float(default)
    if h != h:  # NaN
        h = float(default)
    if h < MIN_PREDICT_HOURS:
        h = float(MIN_PREDICT_HOURS)
    if h > MAX_PREDICT_HOURS:
        h = float(MAX_PREDICT_HOURS)
    return h


# ---------------------------------------------------------------------------
#  时标（离线可用）
# ---------------------------------------------------------------------------

_TS = None


def _get_timescale():
    """返回（进程内缓存的）skyfield 时标对象。

    使用内置数据（builtin=True），无需联网，足以满足业余卫星过境预测
    的精度需求（秒级）。
    """
    global _TS
    if _TS is None:
        if not _HAVE_SKYFIELD:
            raise RuntimeError(
                "缺少第三方库 skyfield，请先安装：pip install skyfield numpy")
        _TS = load.timescale(builtin=True)
    return _TS


# ---------------------------------------------------------------------------
#  基础时间工具（供 Julian Date 互转，保持与上层接口兼容）
# ---------------------------------------------------------------------------

def datetime_to_jd(dt):
    """把（naive 或带 tzinfo，视为 UTC）datetime 转为 Julian Date。"""
    import calendar
    jd = calendar.timegm(dt.timetuple()) / 86400.0 + 2440587.5
    return jd


def jd_to_datetime(jd):
    """把 Julian Date 转回 UTC datetime。"""
    import calendar
    secs = (float(jd) - 2440587.5) * 86400.0
    return datetime.fromtimestamp(secs, tz=timezone.utc)


# ---------------------------------------------------------------------------
#  Satrec 包装：在 skyfield EarthSatellite 之上附加 name / satnum
# ---------------------------------------------------------------------------

class Satrec(object):
    """包装 skyfield 的 EarthSatellite，附加 name / satnum 友好属性。

    skyfield 的 EarthSatellite 已包含完整的 SGP4 传播与几何计算，本包装
    仅用于统一对外接口（predict_passes 等使用 .name / .satnum / ._earth_sat）。
    """

    def __init__(self, earth_sat, name=''):
        self._earth_sat = earth_sat
        self.name = (name.strip() if name else '') or (earth_sat.name or '')
        try:
            self.satnum = earth_sat.model.satnum
        except Exception:
            self.satnum = self.name


def twoline2rv(line1, line2, name='', opsmode='i'):
    """根据两行 TLE 文本构造卫星对象。返回 Satrec 包装对象。

    底层使用 skyfield 的 EarthSatellite（SGP4 标准实现 + 地球模型）。
    """
    if not _HAVE_SKYFIELD:
        raise RuntimeError(
            "缺少第三方库 skyfield，请先安装：pip install skyfield numpy")
    earth_sat = EarthSatellite(line1, line2, name)
    return Satrec(earth_sat, name)


# ---------------------------------------------------------------------------
#  公开接口：观测 / 过境预测
# ---------------------------------------------------------------------------

def observe(satrec, jd_utc, observer):
    """计算观测站看到的卫星地平坐标。

    observer = (lat_deg, lon_deg, alt_m)
    返回 dict: {azimuth(deg, 自正北顺时针), elevation(deg), range_km,
                above_horizon(bool)}
    """
    ts = _get_timescale()
    if isinstance(jd_utc, datetime):
        t = ts.from_datetime(jd_utc)
    else:
        t = ts.utc(jd=float(jd_utc))
    lat, lon, alt = observer
    topos = wgs84.latlon(float(lat), float(lon), float(alt))
    alt_a, az_a, dist = (satrec._earth_sat - topos).at(t).altaz()
    elev = float(alt_a.degrees)
    azim = float(az_a.degrees)
    rng = float(dist.km)
    return {
        'azimuth': azim,
        'elevation': elev,
        'range_km': rng,
        'above_horizon': elev >= 0.0,
    }


def subpoint(satrec, jd_utc):
    """计算卫星星下点（地理坐标）：返回 (lat_deg, lon_deg, alt_km)。

    底层由 skyfield 的 EarthSatellite.at(...).subpoint() 完成（WGS84 椭球），
    供地图显示卫星地面轨迹 / 当前位置使用。jd_utc 可为带 UTC 时区的 datetime，
    或 Julian Date 浮点数。
    """
    ts = _get_timescale()
    if isinstance(jd_utc, datetime):
        t = ts.from_datetime(jd_utc)
    else:
        t = ts.utc(jd=float(jd_utc))
    g = satrec._earth_sat.at(t).subpoint()
    return float(g.latitude.degrees), float(g.longitude.degrees), float(g.elevation.km)


def ground_track(satrec, start_utc, duration_hours=3.0, samples=180,
                 observer=None, observer_b=None):
    """批量计算一段时间内的星下点轨迹（矢量化：一次 skyfield 调用算完全部采样点）。

    地图需要同时画多颗卫星的轨迹，若逐点调用 subpoint() 会有成百上千次
    skyfield 调用开销；本函数用时间数组一次性传播，速度快一到两个数量级。

    参数：
        start_utc      : 轨迹起始时刻（带 UTC 时区的 datetime，或 Julian Date）
        duration_hours : 轨迹时间跨度（小时），自 start_utc 向「后」延伸
        samples        : 采样点数（含首尾），至少 2
        observer       : (lat_deg, lon_deg, alt_m) 或 None；给出时同时算出各
                         采样点对该台站（台站 A / 本台）的仰角，便于地图高亮「可见区段」
        observer_b     : (lat_deg, lon_deg, alt_m) 或 None；给出时同时算出各
                         采样点对「对方台站 B」的仰角，便于通联预测地图区分两站可见区段

    返回 list[(lat_deg, lon_deg, alt_km, elev_a_deg, elev_b_deg)]，
    其中 observer / observer_b 为 None 时对应位置恒为 None。
    """
    import numpy as np

    ts = _get_timescale()
    if isinstance(start_utc, datetime):
        t0 = ts.from_datetime(start_utc)
    else:
        t0 = ts.utc(jd=float(start_utc))
    n = max(2, int(samples))
    hours = max(0.01, float(duration_hours))
    # 以 TT 儒略日均匀采样（跨度内 TT-UTC 为常数，不影响轨迹形状）
    offsets = np.linspace(0.0, hours / 24.0, n)
    t = ts.tt_jd(t0.tt + offsets)

    sub = wgs84.subpoint(satrec._earth_sat.at(t))
    lats = np.atleast_1d(sub.latitude.degrees)
    lons = np.atleast_1d(sub.longitude.degrees)
    alts = np.atleast_1d(sub.elevation.km)

    elevs_a = None
    if observer is not None:
        olat, olon, oalt = observer
        topos = wgs84.latlon(float(olat), float(olon), float(oalt))
        alt_a, _az, _d = (satrec._earth_sat - topos).at(t).altaz()
        elevs_a = np.atleast_1d(alt_a.degrees)

    elevs_b = None
    if observer_b is not None:
        blat, blon, balt = observer_b
        topos_b = wgs84.latlon(float(blat), float(blon), float(balt))
        alt_b, _azb, _db = (satrec._earth_sat - topos_b).at(t).altaz()
        elevs_b = np.atleast_1d(alt_b.degrees)

    out = []
    for i in range(n):
        out.append((float(lats[i]), float(lons[i]), float(alts[i]),
                    (float(elevs_a[i]) if elevs_a is not None else None),
                    (float(elevs_b[i]) if elevs_b is not None else None)))
    return out


def predict_passes(satrec, observer, start_utc, duration_hours=24.0,
                   min_elevation_deg=0.0, step_sec=30):
    """预测一段时间内的可见过境。

    返回列表，每个元素为 dict：
        name, aos(datetime UTC), los(datetime UTC), max_elevation(deg),
        aos_azimuth, los_azimuth, duration_sec, max_azimuth, max_range_km,
        aos_jd, los_jd

    实现说明：
      - 传播与几何全部由 skyfield 完成；
      - 用 EarthSatellite.find_events 以 0° 地平线为基准精确求解
        AOS(0) / MAX(1) / LOS(2) 三个事件时刻（即仰角从地平线起算）；
      - 用户设定的最小仰角仅用于过滤：保留最大仰角达到该值的过境；
      - duration_sec = LOS 时刻 − AOS 时刻（秒级精度，从 0° 起算）。
    仅返回「AOS→MAX→LOS」完整的三元组（窗口边缘被截断的不完整过境不计入）。

    duration_hours 会被钳制到 MAX_PREDICT_HOURS（240 小时）以内。
    """
    ts = _get_timescale()
    if isinstance(start_utc, datetime):
        t0 = ts.from_datetime(start_utc)
    else:
        t0 = ts.utc(jd=float(start_utc))
    t1 = t0 + timedelta(hours=clamp_predict_hours(duration_hours))

    lat, lon, alt = observer
    topos = wgs84.latlon(float(lat), float(lon), float(alt))
    min_elev = max(float(min_elevation_deg), 0.0)

    # 以 0° 地平线为基准求解 AOS/LOS（仰角从地平线起算，秒级精度）；
    # 用户设定的“最小仰角”仅用于过滤（保留最大仰角达到该值的过境）。
    times, events = satrec._earth_sat.find_events(
        topos, t0, t1, altitude_degrees=0.0)

    diff = satrec._earth_sat - topos
    passes = []
    n = len(events)
    i = 0
    while i <= n - 3:
        if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
            aos_t, max_t, los_t = times[i], times[i + 1], times[i + 2]
            alt_a, az_a, _ = diff.at(aos_t).altaz()
            alt_l, az_l, _ = diff.at(los_t).altaz()
            alt_m, az_m, dist_m = diff.at(max_t).altaz()

            max_elev = float(alt_m.degrees)
            # 过滤掉最大仰角低于用户设定最小仰角的过境（AOS/LOS 仍为 0° 地平线时刻）
            if max_elev < min_elev:
                i += 3
                continue

            aos_dt = aos_t.utc_datetime()
            los_dt = los_t.utc_datetime()
            duration_sec = float(los_dt.timestamp() - aos_dt.timestamp())

            passes.append({
                'name': satrec.name or satrec.satnum,
                'satnum': satrec.satnum,
                'aos': aos_dt,
                'aos_jd': datetime_to_jd(aos_dt),
                'aos_azimuth': float(az_a.degrees),
                'los': los_dt,
                'los_jd': datetime_to_jd(los_dt),
                'los_azimuth': float(az_l.degrees),
                'max_elevation': float(alt_m.degrees),
                'max_azimuth': float(az_m.degrees),
                'max_range_km': float(dist_m.km),
                'duration_sec': duration_sec,
            })
            i += 3
        else:
            i += 1
    return passes


# ---------------------------------------------------------------------------
#  双站「通联预测」：两地同时可见同一颗卫星的时间窗口
# ---------------------------------------------------------------------------

def great_circle_km(lat1, lon1, lat2, lon2):
    """两点间大圆距离（公里），用于展示两台站的地面距离。"""
    import math
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def visibility_windows(satrec, observer, start_utc, duration_hours=24.0,
                       min_elevation_deg=0.0):
    """求一段时间内「卫星仰角 ≥ min_elevation_deg」的连续时间窗口。

    与 predict_passes 不同，本函数的 AOS/LOS 直接以用户设定的最小仰角为门限
    （而非 0° 地平线），因为「能否通联」取决于卫星是否高于该台站的可用仰角。

    返回列表，元素为 dict：
        {'start_tt': float, 'end_tt': float,   # skyfield TT 儒略日，便于求交
         'clipped_start': bool, 'clipped_end': bool}
    其中 clipped_* 表示该窗口在预测区间边界被截断（起点早于 start / 终点晚于结束）。
    """
    ts = _get_timescale()
    if isinstance(start_utc, datetime):
        t0 = ts.from_datetime(start_utc)
    else:
        t0 = ts.utc(jd=float(start_utc))
    t1 = t0 + timedelta(hours=clamp_predict_hours(duration_hours))

    lat, lon, alt = observer
    topos = wgs84.latlon(float(lat), float(lon), float(alt))
    min_elev = max(float(min_elevation_deg), 0.0)

    times, events = satrec._earth_sat.find_events(
        topos, t0, t1, altitude_degrees=min_elev)

    windows = []
    cur_start = None
    clipped_start = False
    for t, e in zip(times, events):
        if e == 0:          # rise：升过门限仰角
            cur_start = float(t.tt)
            clipped_start = False
        elif e == 2:        # set：降至门限仰角以下
            if cur_start is None:
                # 预测区间开始时卫星已在门限之上 → 起点被截断
                cur_start = float(t0.tt)
                clipped_start = True
            windows.append({
                'start_tt': cur_start,
                'end_tt': float(t.tt),
                'clipped_start': clipped_start,
                'clipped_end': False,
            })
            cur_start = None
            clipped_start = False
    if cur_start is not None:
        # 预测区间结束时卫星仍在门限之上 → 终点被截断
        windows.append({
            'start_tt': cur_start,
            'end_tt': float(t1.tt),
            'clipped_start': clipped_start,
            'clipped_end': True,
        })
    return windows


def predict_mutual_passes(satrec, observer_a, observer_b, start_utc,
                          duration_hours=24.0, min_elev_a=0.0, min_elev_b=0.0,
                          min_duration_sec=10.0, samples=48):
    """预测「两个台站可通过同一颗卫星互相通联」的时间窗口。

    通联成立的判据：同一时刻卫星对 A 站的仰角 ≥ min_elev_a，
    且对 B 站的仰角 ≥ min_elev_b（即两站的可见窗口存在交集）。

    参数：
        observer_a / observer_b : (lat_deg, lon_deg, alt_m)
        min_elev_a / min_elev_b : 各自的最低可用仰角（度）
        min_duration_sec        : 过滤掉过短的交集窗口（默认 10 秒）
        samples                 : 每个窗口内的采样点数，用于求两站最大仰角与最佳时刻

    返回列表，每个元素为 dict：
        name, satnum,
        start(datetime UTC), end(datetime UTC), duration_sec, start_jd,
        a_max_elev, b_max_elev,            # 窗口内各自的最大仰角
        a_az_start, a_az_end,              # A 站在窗口首尾的方位角
        b_az_start, b_az_end,              # B 站在窗口首尾的方位角
        best_time(datetime UTC),           # 两站仰角「较低者」最高的时刻（最佳通联时刻）
        best_min_elev,                     # 该时刻两站仰角的较低值
        a_elev_at_best, b_elev_at_best,
        clipped_start, clipped_end         # 窗口是否被预测区间边界截断
    """
    import numpy as np

    hours = clamp_predict_hours(duration_hours)
    wins_a = visibility_windows(satrec, observer_a, start_utc, hours, min_elev_a)
    if not wins_a:
        return []
    wins_b = visibility_windows(satrec, observer_b, start_utc, hours, min_elev_b)
    if not wins_b:
        return []

    ts = _get_timescale()
    topos_a = wgs84.latlon(float(observer_a[0]), float(observer_a[1]), float(observer_a[2]))
    topos_b = wgs84.latlon(float(observer_b[0]), float(observer_b[1]), float(observer_b[2]))
    diff_a = satrec._earth_sat - topos_a
    diff_b = satrec._earth_sat - topos_b

    n_samples = max(int(samples), 8)
    results = []
    i = j = 0
    while i < len(wins_a) and j < len(wins_b):
        wa, wb = wins_a[i], wins_b[j]
        s = max(wa['start_tt'], wb['start_tt'])
        e = min(wa['end_tt'], wb['end_tt'])
        dur_sec = (e - s) * 86400.0
        if dur_sec > max(float(min_duration_sec), 0.0):
            tts = np.linspace(s, e, n_samples)
            t_arr = ts.tt_jd(tts)
            alt_a, az_a, _ = diff_a.at(t_arr).altaz()
            alt_b, az_b, _ = diff_b.at(t_arr).altaz()
            ea = np.asarray(alt_a.degrees, dtype=float)
            eb = np.asarray(alt_b.degrees, dtype=float)
            both = np.minimum(ea, eb)
            k = int(np.argmax(both))

            t_start = ts.tt_jd(s)
            t_end = ts.tt_jd(e)
            start_dt = t_start.utc_datetime()
            end_dt = t_end.utc_datetime()
            best_dt = ts.tt_jd(float(tts[k])).utc_datetime()

            results.append({
                'name': satrec.name or satrec.satnum,
                'satnum': satrec.satnum,
                'start': start_dt,
                'end': end_dt,
                'start_jd': datetime_to_jd(start_dt),
                'duration_sec': float(end_dt.timestamp() - start_dt.timestamp()),
                'a_max_elev': float(ea.max()),
                'b_max_elev': float(eb.max()),
                'a_az_start': float(np.asarray(az_a.degrees, dtype=float)[0]),
                'a_az_end': float(np.asarray(az_a.degrees, dtype=float)[-1]),
                'b_az_start': float(np.asarray(az_b.degrees, dtype=float)[0]),
                'b_az_end': float(np.asarray(az_b.degrees, dtype=float)[-1]),
                'best_time': best_dt,
                'best_min_elev': float(both[k]),
                'a_elev_at_best': float(ea[k]),
                'b_elev_at_best': float(eb[k]),
                'clipped_start': bool(
                    (wa['clipped_start'] and s == wa['start_tt']) or
                    (wb['clipped_start'] and s == wb['start_tt'])),
                'clipped_end': bool(
                    (wa['clipped_end'] and e == wa['end_tt']) or
                    (wb['clipped_end'] and e == wb['end_tt'])),
            })
        # 推进结束较早的那个窗口
        if wa['end_tt'] <= wb['end_tt']:
            i += 1
        else:
            j += 1
    return results


# ---------------------------------------------------------------------------
#  TLE 下载 / 解析
# ---------------------------------------------------------------------------

CELESTRAK_AMATEUR_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle"

# 本地 TLE 缓存路径（星历数据）。解析为基于应用根目录的绝对路径，
# 以保证打包后无论从哪个目录启动都能读到打包进 exe 旁边的 file/amateur.tle。
TLE_CACHE = app_path('file/amateur.tle')

# 常见业余卫星频段/模式参考，用于“快速记录”预填频率与模式
SATE_BANDS = {
    "ISS (ZARYA)": {"uplink": "145.990", "downlink": "145.800", "mode": "FM"},
    "SO-50": {"uplink": "145.850", "downlink": "436.795", "mode": "FM"},
    "AO-91": {"uplink": "145.960", "downlink": "435.250", "mode": "FM"},
    "AO-92": {"uplink": "145.900", "downlink": "435.350", "mode": "FM"},
    "PO-101": {"uplink": "145.825", "downlink": "437.250", "mode": "FM"},
    "AO-27": {"uplink": "145.850", "downlink": "436.795", "mode": "FM"},
    "FO-29": {"uplink": "145.950", "downlink": "435.795", "mode": "SSB/CW"},
    "XW-2A": {"uplink": "145.855", "downlink": "435.115", "mode": "CW/LSB"},
    "XW-2B": {"uplink": "145.915", "downlink": "435.190", "mode": "CW/LSB"},
    "XW-2C": {"uplink": "145.960", "downlink": "435.280", "mode": "CW/LSB"},
    "XW-2D": {"uplink": "145.840", "downlink": "435.225", "mode": "CW/LSB"},
    "XW-2F": {"uplink": "145.890", "downlink": "435.065", "mode": "CW/LSB"},
    "LILACSAT-2": {"uplink": "145.900", "downlink": "437.200", "mode": "FM"},
    "CAS-4A": {"uplink": "145.870", "downlink": "435.220", "mode": "CW/LSB"},
    "CAS-4B": {"uplink": "145.815", "downlink": "435.600", "mode": "CW/LSB"},
}


def fetch_amateur_tle(cache_path=TLE_CACHE, force=False, timeout=20):
    """从 Celestrak 下载业余卫星 TLE 并缓存到本地文件。

    返回下载得到的 TLE 文本。若 force=False 且缓存存在则直接读缓存。
    下载失败且缓存存在时回退到缓存。
    """
    if (not force) and os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()
    try:
        req = urllib.request.Request(
            CELESTRAK_AMATEUR_URL,
            headers={'User-Agent': 'F-HamLog/2.0 satellite prediction'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8')
        os.makedirs(os.path.dirname(cache_path) or '.', exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(data)
        return data
    except Exception as e:
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                return f.read()
        raise RuntimeError("无法下载 TLE 且没有本地缓存：%s" % e)


def parse_tle_text(text):
    """把 Celestrak 格式 TLE 文本（每行 名称/Line1/Line2 为一组）解析为
    [(name, Satrec), ...]。
    """
    lines = [ln.rstrip('\n') for ln in text.splitlines() if ln.strip()]
    sats = []
    i = 0
    while i + 2 < len(lines) + 1 and i + 2 <= len(lines):
        if (i + 2 <= len(lines) and lines[i].startswith('1 ') and
                lines[i + 1].startswith('2 ')):
            # 没有名称行，用 satnum 作为名称
            name = lines[i][2:7].strip()
            l1, l2 = lines[i], lines[i + 1]
            i += 2
        elif (i + 1 < len(lines) and i + 2 < len(lines) and
              not lines[i].startswith('1 ') and lines[i + 1].startswith('1 ') and
              lines[i + 2].startswith('2 ')):
            name = lines[i].strip()
            l1, l2 = lines[i + 1], lines[i + 2]
            i += 3
        else:
            i += 1
            continue
        try:
            satrec = twoline2rv(l1, l2, name=name)
            sats.append((name, satrec))
        except Exception:
            continue
    return sats


def load_amateur_satellites(cache_path=TLE_CACHE, force=False):
    """下载/读取业余卫星 TLE 并返回 [(name, Satrec), ...]。"""
    text = fetch_amateur_tle(cache_path=cache_path, force=force)
    return parse_tle_text(text)


# ---------------------------------------------------------------------------
#  TQSL / LoTW 卫星名称映射
# ---------------------------------------------------------------------------

# 数据文件（tqsl_dict.txt / sat_radio_dict.txt）所在目录。
# 关键：用「应用根目录」解析（app_path），避免依赖“当前工作目录”。
# 否则当程序从其它目录启动（如打包后双击 exe、或快捷方式 Start In 不同）时，
# 相对路径 file/... 会找不到文件，导致静默回退到内置数据，表现为
# “读不到卫星转发器表 / 星历（TLE）/ 设置”。
def _resolve_data_path(rel):
    """把相对数据文件路径解析为基于应用根目录的绝对路径。"""
    return app_path(rel)


def _read_text(path):
    """以尽量宽松的编码读取文本文件，兼容 UTF-8 / 含 BOM / GBK / Latin-1。"""
    with open(path, 'rb') as f:
        raw = f.read()
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', errors='replace')


TQSL_DICT_PATH = _resolve_data_path("file/tqsl_dict.txt")


def load_tqsl_dict(path=TQSL_DICT_PATH):
    """读取「卫星显示名 -> TQSL/LoTW 认可名」映射表。

    文件为纯文本，每行 `显示名=TQSL名`；以 # 开头为注释，空行忽略。
    找不到文件时返回空 dict（回退为使用原始显示名）。
    每次调用都重新读取，便于用户随时编辑后即时生效。
    """
    d = {}
    if not os.path.exists(path):
        return d
    try:
        text = _read_text(path)
    except Exception:
        return d
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip()
        if k:
            d[k] = v
    return d


def tqsl_sat_name(name, path=TQSL_DICT_PATH):
    """把卫星显示名转换为 TQSL/LoTW 认可的名称；无映射时返回原名。"""
    return load_tqsl_dict(path).get(name.strip(), name)


def has_tqsl_mapping(name, path=TQSL_DICT_PATH):
    """判断卫星显示名是否存在 TQSL/LoTW 映射（存在返回 True，否则 False）。"""
    return name.strip() in load_tqsl_dict(path)


# ---------------------------------------------------------------------------
#  卫星转发器（transponder）数据：用于“快速记录”预填收发频率与模式
# ---------------------------------------------------------------------------

SAT_RADIO_DICT_PATH = _resolve_data_path("file/sat_radio_dict.txt")


def load_sat_radio_dict(path=SAT_RADIO_DICT_PATH):
    """读取卫星转发器数据表，用于"快速记录"预填收发频率与模式。

    文件为纯文本，每行 `卫星名=下行频率,上行频率,模式`；以 # 开头为注释，空行忽略。
    例如：
        ISS (ZARYA)=145.800,145.990,FM
        SO-50=436.795,145.850,FM
    键（卫星名）需与 TLE 中的名称一致（如 ISS (ZARYA)、SO-50、AO-91）。

    找不到文件或文件为空时返回空 dict；文件中的条目会覆盖同名条目。
    每次调用都重新读取，便于用户随时编辑后即时生效。
    """
    d = {}
    if not os.path.exists(path):
        return d
    try:
        text = _read_text(path)
    except Exception:
        return d
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        k, rest = line.split('=', 1)
        k = k.strip()
        if not k:
            continue
        parts = [x.strip() for x in rest.split(',')]
        if len(parts) < 3:
            continue
        downlink, uplink, mode = parts[0], parts[1], parts[2]
        d[k] = {
            "downlink": downlink,
            "uplink": uplink,
            "mode": mode,
        }
    return d


def lookup_transponder(bands, name):
    """按卫星名在转发器表中查找条目。

    兼容 TLE 长名与短名不一致的情况，例如业余卫星 TLE 中常写作
    ``SAUDISAT 1C (SO-50)``，而转发器表（sat_radio_dict.txt）的键是 ``SO-50``。
    依次尝试以下候选键，命中即返回：
      1. 原始 TLE 名；
      2. TQSL/LoTW 映射后的名称（tqsl_sat_name）；
      3. 名称中括号内的短名（如 ``(SO-50)``）；
      4. 括号内短名再做 TQSL 映射；
      5. 以上各项的大小写不敏感匹配。
    全部未命中返回 None。
    """
    if not name:
        return None
    cands = [name, tqsl_sat_name(name)]
    m = re.search(r'\(([^)]+)\)', name)
    if m:
        inner = m.group(1).strip()
        cands.append(inner)
        cands.append(tqsl_sat_name(inner))
    for c in cands:
        c = c.strip()
        if c in bands:
            return bands[c]
    # 大小写不敏感兜底
    up = {k.upper(): bands[k] for k in bands}
    for c in cands:
        c = c.strip().upper()
        if c in up:
            return up[c]
    return None


# ---------------------------------------------------------------------------
#  梅登黑格网格定位（Maidenhead Grid Locator）
# ---------------------------------------------------------------------------

def maidenhead_to_latlon(locator):
    """把梅登黑格网格（如 'PM84'、'PM84lx'、'FN31'）解码为该网格中心 (lat, lon)。

    支持 4/6/8 位（及更长）格式，字母大小写均可。返回 (纬度°, 经度°)。
    无效输入抛出 ValueError。
    """
    loc = locator.strip().upper()
    n = len(loc)
    if n < 4 or n % 2 != 0:
        raise ValueError("梅登黑格坐标至少需 4 位，例如 PM84")
    if not (loc[0].isalpha() and loc[1].isalpha()):
        raise ValueError("梅登黑格坐标前两位应为字母（A–R）")

    lon = -180.0
    lat = -90.0
    lon += (ord(loc[0]) - ord('A')) * 20
    lat += (ord(loc[1]) - ord('A')) * 10
    cell_lon, cell_lat = 20.0, 10.0

    for pair in range(1, n // 2):
        a, b = loc[2 * pair], loc[2 * pair + 1]
        if pair % 2 == 1:
            if not (a.isdigit() and b.isdigit()):
                raise ValueError("梅登黑格坐标的偶数位应为数字")
            lon += int(a) * (cell_lon / 10)
            lat += int(b) * (cell_lat / 10)
            cell_lon /= 10
            cell_lat /= 10
        else:
            if not (a.isalpha() and b.isalpha()):
                raise ValueError("梅登黑格坐标的子格位应为字母")
            lon += (ord(a) - ord('A')) * (cell_lon / 24)
            lat += (ord(b) - ord('A')) * (cell_lat / 24)
            cell_lon /= 24
            cell_lat /= 24

    return lat + cell_lat / 2, lon + cell_lon / 2


def latlon_to_maidenhead(lat, lon, precision=6):
    """把 (lat, lon) 编码为梅登黑格网格字符串（默认 6 位）。"""
    lon += 180.0
    lat += 90.0
    field_lon = int(lon // 20)
    field_lat = int(lat // 10)
    loc = chr(ord('A') + field_lon) + chr(ord('A') + field_lat)
    lon -= field_lon * 20
    lat -= field_lat * 10

    sq_lon = int(lon // 2)
    sq_lat = int(lat // 1)
    loc += str(sq_lon) + str(sq_lat)
    lon -= sq_lon * 2
    lat -= sq_lat * 1

    cell_lon = 2.0
    cell_lat = 1.0
    next_is_letter = True
    while len(loc) < precision:
        if next_is_letter:
            sl = int(lon // (cell_lon / 24))
            st = int(lat // (cell_lat / 24))
            loc += chr(ord('a') + sl) + chr(ord('a') + st)
            lon -= sl * (cell_lon / 24)
            lat -= st * (cell_lat / 24)
            cell_lon /= 24
            cell_lat /= 24
        else:
            el = int(lon // (cell_lon / 10))
            et = int(lat // (cell_lat / 10))
            loc += str(el) + str(et)
            lon -= el * (cell_lon / 10)
            lat -= et * (cell_lat / 10)
            cell_lon /= 10
            cell_lat /= 10
        next_is_letter = not next_is_letter
    return loc[:precision]


if __name__ == '__main__':
    # 简单自测：用 ISS TLE 验证传播与过境时长
    tle = """ISS (ZARYA)
1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991
2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000
"""
    sats = parse_tle_text(tle)
    sat = sats[0][1]
    passes = predict_passes(sat, (30.0, 114.0, 50.0),
                            datetime(2024, 1, 16, 0, 0, 0, tzinfo=timezone.utc),
                            duration_hours=24, min_elevation_deg=10)
    print("24小时内可见过境次数:", len(passes))
    for p in passes:
        print("  AOS", p['aos'], "最大仰角", round(p['max_elevation'], 1),
              "时长(秒)", int(p['duration_sec']), "约", round(p['duration_sec'] / 60.0, 1), "分钟")
