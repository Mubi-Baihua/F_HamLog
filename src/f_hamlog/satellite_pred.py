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
    4. 从「星历数据源」（file/tle_sources.txt 里配置的地址，默认 Celestrak
       全部活动卫星）下载全部卫星 TLE 并本地缓存。

依赖：第三方库 skyfield + numpy（pip install skyfield numpy）。
  时标使用 skyfield 内置数据（builtin=True），无需联网即可运行；
  若希望使用更高精度的 IERS 地球定向数据，可在联网环境下让 skyfield
  自行下载并缓存（不影响本模块接口）。

注意：过境检测直接由 skyfield 的 `EarthSatellite.find_events` 完成，
它精确求解仰角穿越最小可见阈值的 AOS/MAX/LOS 时刻，过境时长 =
LOS 时刻 − AOS 时刻（秒级精度），不再依赖粗扫描步长近似。
"""

import csv
import os
import subprocess
import re
import sys
import time
import unicodedata
import urllib.error
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

from .paths import app_path  # 数据路径解析统一由 paths 模块负责


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
#  自选卫星数量上限
# ---------------------------------------------------------------------------

# 一次预测允许勾选的最大卫星数。超过这个量级，过境表会变得无法阅读，
# 且 find_events 逐星扫描的耗时会长到让界面失去响应，因此在选星入口就拦住。
MAX_SELECTED_SATELLITES = 250


def clamp_selected_count(n, limit=MAX_SELECTED_SATELLITES):
    """裁掉超量选择：返回 (保留集合, 被裁掉的数量)。

    set 本身无序，这里按「名称排序」取前 limit 个，保证同样的输入集合
    每次裁剪结果一致（避免用户重开对话框时看到的选择莫名变化）。
    """
    if n is None:
        return set(), 0
    items = sorted(n)
    if len(items) <= limit:
        return set(items), 0
    return set(items[:limit]), len(items) - limit


# ---------------------------------------------------------------------------
#  卫星列表的「按编号增量更新」
# ---------------------------------------------------------------------------

def sat_key(satrec, name=''):
    """取一颗卫星的唯一标识（NORAD 编号）。

    编号取不到时（极少数手工数据）退回用名称，保证「同一颗卫星」判定不会
    退化为「全都算新的」。返回 (类型, 值) 元组，避免编号与名称撞车。
    """
    num = getattr(satrec, 'satnum', None)
    if num is None or num == '':
        return ('name', name)
    return ('num', norad_key(str(num)))


def norad_key(field):
    """把 TLE 第 1 行 3–7 列（NORAD 编号）规整为稳定 key。

    不同数据源的补位方式不同：Celestrak 用 0 补足 5 位（`1 00694U`），
    有的数据源用空格补位（`1   694U`）。两者必须视为同一颗卫星，故统一
    去掉前导 0；启用 Alpha-5 编码（首字符为字母）时保持原样并大写。

    同样先做 NFKC 兼容折叠，使中文输入法「全角」下打出的 ６１７８１ 等价于 61781。
    """
    text = unicodedata.normalize('NFKC', (field or '').strip())
    if not text:
        return ''
    if text.isdigit():
        return text.lstrip('0') or '0'
    return text.upper()


def merge_update_satellites(existing, incoming):
    """按 NORAD 编号把 incoming 增量并入 existing，返回 (合并后列表, 更新数, 新增数)。

    规则（下载与导入共用同一套语义）：
      - incoming 里出现的编号：用新数据**替换** existing 中的同编号条目（更新）；
      - incoming 里没有的编号：existing 中的条目**原样保留**（绝不删除）；
      - existing 里没有的编号：按 incoming 的顺序追加（新增）。
    合并后保持 existing 的原有顺序，新增项依次排在末尾。
    """
    out = list(existing or [])
    index = {}
    for i, (name, sat) in enumerate(out):
        index.setdefault(sat_key(sat, name), i)
    updated = added = 0
    for name, sat in (incoming or []):
        key = sat_key(sat, name)
        if key in index:
            out[index[key]] = (name, sat)
            updated += 1
        else:
            index[key] = len(out)
            out.append((name, sat))
            added += 1
    return out, updated, added


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

    另外保存原始的两行 TLE（line1 / line2）：skyfield 的 EarthSatellite 不保留
    原始文本，而「把当前卫星列表写回星历缓存 / 导出 TLE」需要它。
    """

    def __init__(self, earth_sat, name='', line1='', line2=''):
        self._earth_sat = earth_sat
        self.name = (name.strip() if name else '') or (earth_sat.name or '')
        try:
            self.satnum = earth_sat.model.satnum
        except Exception:
            self.satnum = self.name
        self.line1 = (line1 or '').strip()
        self.line2 = (line2 or '').strip()


def twoline2rv(line1, line2, name='', opsmode='i'):
    """根据两行 TLE 文本构造卫星对象。返回 Satrec 包装对象。

    底层使用 skyfield 的 EarthSatellite（SGP4 标准实现 + 地球模型）。
    """
    if not _HAVE_SKYFIELD:
        raise RuntimeError(
            "缺少第三方库 skyfield，请先安装：pip install skyfield numpy")
    earth_sat = EarthSatellite(line1, line2, name)
    return Satrec(earth_sat, name, line1=line1, line2=line2)


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

CELESTRAK_ALL_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
# 保留旧常量名，兼容外部调用方；实际请求使用全部活动卫星数据。
CELESTRAK_AMATEUR_URL = CELESTRAK_ALL_URL
# 语义更明确的别名：内置 Celestrak「全部活动卫星」入口。
CELESTRAK_ACTIVE_URL = CELESTRAK_ALL_URL

# ---------------------------------------------------------------------------
#  星历数据源（独立窗口 + 独立配置文件）
# ---------------------------------------------------------------------------
# 数据源是一个**有序**的 URL 列表：下载时按顺序依次读取，越靠前优先级越高；
# 若多个来源里出现同一颗卫星（按 NORAD 编号判定），以靠前的来源为准。
# 默认只用内置的 Celestrak（全量活动卫星），用户可在「星历数据源」窗口里
# 添加自定义地址并调整顺序。
# 内置默认数据源（有序，越靠前优先级越高；多个源出现同一颗卫星时以靠前的为准）。
# celestrak 的 FORMAT=csv（OMM 风格）由 iter_tle_records 重建为 TLE 两行，照常可用。
DEFAULT_TLE_SOURCES = (
    "https://live.ariss.org/iss.txt",
    "https://r4uab.ru/satonline.txt",
    "https://amsat.org/tle/current/nasabare.txt",
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv",
    "https://db.satnogs.org/api/tle/?format=3le",
)

# 数据源保存在**独立文件** file/tle_sources.txt 中（每行一个地址），
# 不再写进设置文件 m_xml.txt；窗口见 tle_source_window.py。
TLE_SOURCES_PATH = app_path('file/tle_sources.txt')
# 数据源文件不存在时，兼容读取一次早期版本写在 m_xml.txt 里的旧键。
LEGACY_TLE_SOURCES_KEY = 'sat_tle_sources'
# 保留旧常量名，兼容外部调用方
TLE_SOURCES_KEY = LEGACY_TLE_SOURCES_KEY

SETTINGS_PATH = app_path('file/m_xml.txt')

# 数据源文件首部的注释（每次保存都会重写，保证用户手动打开也能看懂）
TLE_SOURCES_HEADER = (
    '# F HamLog 星历(TLE) 数据源列表',
    '# 每行一个地址，下载时按列表顺序依次读取；',
    '# 同一颗卫星（按 NORAD 编号）以靠前的数据源为准，本文件可在',
    '# 「设置 → 星历数据源」窗口中启用/禁用、增删与排序，也可直接编辑。',
    '# 在某个地址前加一个 # 即为「禁用」（不参与下载，例如 # https://x/a.txt）；',
    '# 其余以 # 开头的行仍按注释处理。',
    '# 内置默认（Celestrak 全部活动卫星）：%s' % CELESTRAK_ACTIVE_URL,
    '',
)

# 单次「测延迟」的默认超时（秒）。打开数据源设置页时会自动逐个探测。
TLE_PROBE_TIMEOUT = 5.0


def _parse_source_line(line):
    """把数据源文件里的一行解析为 (url, enabled)；不是数据源时返回 None。

    - ``https://a/x.txt``            → (.., True)   启用
    - ``https://a/x.txt # 备注``     → (.., True)   启用（行内备注忽略）
    - ``# https://a/x.txt``          → (.., False)  禁用（地址前加 # 即禁用）
    - 其它以 # 开头的行 / 空行       → None         注释，忽略
    """
    text = (line or '').strip()
    if not text:
        return None
    disabled = False
    if text.startswith('#'):
        disabled = True
        # 只吃掉一个 '#'：'## ...' 仍是普通注释，不会被误认成禁用项
        text = text[1:].strip()
        if not text:
            return None
    head = text.split('#', 1)[0].strip()      # 去掉行内备注
    if head and is_valid_tle_source(head):
        return head, not disabled
    return None


def parse_tle_source_entries(text):
    """解析数据源文件内容，返回按顺序去重的 ``[(url, enabled)]``。

    同一地址只保留首次出现的启用状态（先到先得），与下载时的优先级语义一致。
    """
    entries = []
    seen = set()
    for line in (text or '').splitlines():
        parsed = _parse_source_line(line)
        if parsed is None:
            continue
        url, enabled = parsed
        if url in seen:
            continue
        seen.add(url)
        entries.append((url, enabled))
    return entries


def normalize_tle_sources(raw):
    """把任意来源的「数据源」取值规整为有序 URL 列表。

    - None / 空 / 非法值 → 返回内置默认（保证永远至少有一个源）；
    - 字符串按单个地址处理（兼容旧配置）；
    - 逐项去首尾空白，忽略空行与 # 注释行，按原顺序去重（保留第一个）。
    """
    if raw is None:
        return list(DEFAULT_TLE_SOURCES)
    if isinstance(raw, str):
        raw = [raw]
    urls = []
    try:
        items = list(raw)
    except TypeError:
        return list(DEFAULT_TLE_SOURCES)
    for item in items:
        url = str(item).strip()
        if not url or url.startswith('#'):
            continue
        if url not in urls:
            urls.append(url)
    return urls or list(DEFAULT_TLE_SOURCES)


def is_valid_tle_source(url):
    """判断一个地址是否像可用的星历数据源地址。

    只做基本校验（非空、无空白字符、带 http/https/ftp/file 协议头），
    不做联网探测——下载时若连不上会自然计入「下载失败」。
    """
    text = (url or '').strip()
    if not text or any(ch.isspace() for ch in text):
        return False
    if '://' not in text:
        return False
    return text.split('://', 1)[0].lower() in ('http', 'https', 'ftp', 'file')


def parse_tle_sources_text(text):
    """解析数据源文件内容，返回**启用**的地址列表（按原顺序去重）。

    禁用项（地址前加了 #）与注释行都不会返回——下载时只走启用的源。
    需要「启用状态」本身时用 parse_tle_source_entries。
    """
    return [url for url, enabled in parse_tle_source_entries(text) if enabled]


def load_tle_source_entries(path=None):
    """读独立数据源文件，返回 ``[(url, enabled)]``。

    文件不存在/不可读时返回 None（与「文件存在但没有数据行」区分开，
    后者返回空列表），便于 load_tle_sources 决定是否回退到旧设置键。
    """
    path = path or TLE_SOURCES_PATH
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return parse_tle_source_entries(f.read())
    except Exception:
        return None


def drop_legacy_tle_sources():
    """把早期版本写在设置文件 m_xml.txt 里的数据源键删掉（一次性迁移清理）。

    数据源改由独立文件承载后，两份配置并存容易出现「改了不生效」的困惑，
    因此在保存独立文件时顺手清掉旧键。找不到键/设置文件不可读时静默跳过。
    """
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            settings = eval(f.read())
    except Exception:
        return False
    if not isinstance(settings, dict) or LEGACY_TLE_SOURCES_KEY not in settings:
        return False
    settings.pop(LEGACY_TLE_SOURCES_KEY, None)
    try:
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            f.write(str(settings))
    except Exception as e:
        print('[卫星星历] 警告：清理旧数据源设置失败：%s' % e)
        return False
    return True


def save_tle_source_entries(entries, path=None):
    """把 ``[(url, enabled)]`` 写入独立文件，返回实际写入的列表。

    规整规则：去空、按原顺序去重（先到先得）、只看地址不看启用状态；
    禁用项写成 ``# 地址``（照旧可手工编辑）。**文件里始终至少有一个启用的源**：
    一条地址都没有时回落到内置默认，全部被禁用时把第一条重新启用。
    保存后顺带清理设置文件里的旧键。
    """
    path = path or TLE_SOURCES_PATH
    cleaned = []
    seen = set()
    for item in (entries or []):
        if isinstance(item, (tuple, list)) and len(item) == 2:
            url, enabled = item
        else:
            url, enabled = item, True
        url = str(url or '').strip()
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append((url, bool(enabled)))
    if not cleaned:
        cleaned = [(u, True) for u in DEFAULT_TLE_SOURCES]
    if not any(enabled for _, enabled in cleaned):
        cleaned[0] = (cleaned[0][0], True)
    lines = [('%s %s' % ('#', url)) if not enabled else url
             for url, enabled in cleaned]
    text = '\n'.join(list(TLE_SOURCES_HEADER) + lines) + '\n'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    drop_legacy_tle_sources()
    return cleaned


def save_tle_sources(urls, path=None):
    """兼容旧调用：把一批地址**全部按启用**写入，返回启用的地址列表。"""
    if isinstance(urls, str):
        urls = [urls]
    entries = save_tle_source_entries([(u, True) for u in (urls or [])], path)
    return [url for url, enabled in entries if enabled]


def load_tle_sources():
    """读取**启用**的星历数据源列表（按优先级排序）。

    依次尝试：① 独立文件 file/tle_sources.txt；② 早期版本写在设置文件
    m_xml.txt 里的旧键 sat_tle_sources（兼容读取，保存时会被清理）；③ 内置默认。
    独立文件里被禁用的项（地址前加 #）不会返回；文件里列了地址但**全部被禁用**
    时返回空列表——调用方据此提示「所有数据源都已禁用」，而不是悄悄把内置默认
    源又打开。每次调用都重新读取，便于用户改完立即生效。
    """
    entries = load_tle_source_entries()
    if entries:
        return [url for url, enabled in entries if enabled]
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            settings = eval(f.read())
    except Exception:
        return list(DEFAULT_TLE_SOURCES)
    if not isinstance(settings, dict):
        return list(DEFAULT_TLE_SOURCES)
    return normalize_tle_sources(settings.get(LEGACY_TLE_SOURCES_KEY))


# 本地 TLE 缓存路径（虽然文件名沿用历史名称，但内容包含全部卫星）。
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


class TleFetchCanceled(Exception):
    """用户主动取消星历下载时抛出（非错误）。"""
    pass


def _download_url(url, timeout, pct_cb, cancel):
    """分块下载单个 URL 并返回解码后的文本（便于上报进度 / 响应取消）。

    pct_cb(pct)：本地字节进度回调。服务器返回 Content-Length 时回调 0..100 的
    实际百分比；否则先回调 -1（表示“不确定进度”，界面转忙碌动画），结束回调 100。
    """
    req = urllib.request.Request(
        url, headers={'User-Agent': 'F-HamLog/2.0 satellite prediction'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = resp.headers.get('Content-Length')
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = None
        # 确定有总大小则走百分比进度，否则走“忙碌”不确定进度
        pct_cb(0 if total else -1)
        chunks = []
        downloaded = 0
        while True:
            # 每读一块就检查一次取消请求，确保响应及时
            if cancel is not None and cancel():
                raise TleFetchCanceled('用户取消了星历下载')
            chunk = resp.read(16384)
            if not chunk:
                break
            chunks.append(chunk)
            if total:
                downloaded += len(chunk)
                pct_cb(min(100, int(downloaded / total * 100)))
        pct_cb(100)
        return b''.join(chunks).decode('utf-8', errors='replace')


def _probe_error_text(err):
    """把探测异常压成一句简短说明（显示在数据源列表右侧）。"""
    if isinstance(err, urllib.error.HTTPError):
        return 'HTTP %s' % err.code
    reason = getattr(err, 'reason', None)
    if isinstance(err, TimeoutError) or isinstance(reason, TimeoutError):
        return '超时'
    text = str(reason or err).strip()
    if not text:
        return '连接失败'
    return (text[:38] + '…') if len(text) > 39 else text


def probe_tle_source(url, timeout=TLE_PROBE_TIMEOUT):
    """测一个数据源的响应延迟，返回 ``(ok, ms, err)``。

    只把响应体的开头一小块读出来就断开：选源时关心的是「连得上、多久出首包」，
    没必要把整个星历文件拉下来（几万行）。任何异常都收敛成
    ``(False, ms, 简短说明)``，**不向外抛**，方便界面后台线程直接调用。

    打开「星历数据源」窗口时会自动逐个调用它，用户也可以在窗口里改完地址后
    自动重测——没有「手动测试」这一步。
    """
    text = (url or '').strip()
    if not is_valid_tle_source(text):
        return False, 0, '地址格式不正确'
    start = time.perf_counter()
    try:
        if text.lower().startswith('file:'):
            with urllib.request.urlopen(text, timeout=timeout) as resp:
                resp.read(1024)
        else:
            req = urllib.request.Request(
                text, headers={'User-Agent': 'F-HamLog/2.0 satellite prediction'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read(4096)
    except Exception as e:
        return False, int((time.perf_counter() - start) * 1000), _probe_error_text(e)
    return True, int((time.perf_counter() - start) * 1000), ''


def fetch_amateur_tle(cache_path=TLE_CACHE, force=False, timeout=20,
                      progress=None, progress_pct=None, cancel=None,
                      sources=None):
    """按「设置」里的星历数据源列表下载全部卫星 TLE 并缓存到本地文件。

    sources：**有序**的数据源 URL 列表（越靠前优先级越高）；缺省时从独立数据源
    文件 file/tle_sources.txt 读取（未配置则为内置 Celestrak）。多个源里出现同一颗
    卫星时，按 NORAD 编号判定，以靠前的源为准。

    写入缓存前还会与**已有缓存**按编号合并：只更新下载到的卫星，缓存里已有但
    本次没下到的卫星继续保留（不会因为某个源临时缺数据就丢掉卫星）。

    返回合并后的 TLE 文本。若 force=False 且缓存存在则直接读缓存。

    所有数据源一视同仁：**只下载该网址返回的内容**，不按地址做任何特殊处理
    （没有特殊提示，也没有按分类组拆分的回退下载）。某个源连不上或返回空内容
    就记为该源失败，其余源继续。

    进度反馈（均为可选回调）：
      - progress(msg)：文本状态提示（沿用旧接口）。
      - progress_pct(pct)：整数 0..100 的下载百分比；传入 -1 表示“不确定进度”
        （服务器未返回 Content-Length，进度条显示为忙碌动画）。
      - cancel：返回 True 表示用户已取消；分块下载时每读一块就检查一次，
        一旦取消立即抛出 TleFetchCanceled（调用方据此判定为“用户取消”而非错误）。
    """
    if (not force) and os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()

    def report(message):
        if progress is not None:
            progress(message)

    def report_pct(pct):
        if progress_pct is not None:
            progress_pct(pct)

    if sources is not None:
        urls = normalize_tle_sources(sources)
    else:
        entries = load_tle_source_entries()
        if entries:
            urls = [url for url, enabled in entries if enabled]
            if not urls:
                # 文件里列了地址但全被禁用：明确报错，不要悄悄启用内置默认源
                raise RuntimeError(
                    '所有星历数据源都已禁用，请在「设置 → 星历数据源」中'
                    '至少启用一个数据源。')
        else:
            urls = load_tle_sources()      # 无独立文件 → 旧设置键 / 内置默认
    n_src = len(urls)
    texts = []
    failed = []

    for index, url in enumerate(urls):
        def slot_pct(pct, _i=index, _n=n_src):
            # 把单个源内部的进度映射为「所有数据源的整体进度」
            f = pct / 100.0 if pct >= 0 else 0.0
            report_pct(int((_i + f) / _n * 100))

        try:
            report('正在下载数据源 %d/%d：%s' % (index + 1, n_src, url))
            text = _download_url(url, timeout, slot_pct, cancel)
        except TleFetchCanceled:
            raise  # 用户取消：直接冒泡，不计入失败
        except Exception as e:
            failed.append((url, str(e)))
            continue
        if text and text.strip():
            texts.append(text)

    if not texts:
        detail = '；'.join('%s（%s）' % (u, e) for u, e in failed) if failed else ''
        raise RuntimeError('全部星历数据源都下载失败。' + detail)
    if failed:
        print('[卫星星历] 以下数据源下载失败：%s'
              % '；'.join('%s（%s）' % (u, e) for u, e in failed))

    report('正在合并 %d 个数据源…' % len(texts))
    data = merge_tle_texts(*texts)   # 靠前的数据源优先

    # 与已有缓存按编号合并：只按卫星编号更新，旧缓存里多出来的卫星继续保留
    old_text = ''
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                old_text = f.read()
        except Exception as e:
            print('[卫星星历] 警告：读取旧星历缓存失败，跳过保留旧数据：%s' % e)
    if old_text.strip():
        n_downloaded = sum(1 for _ in iter_tle_records(data))
        data = merge_tle_texts(data, old_text)
        n_kept = sum(1 for _ in iter_tle_records(data)) - n_downloaded
        if n_kept > 0:
            print('[卫星星历] 保留 %d 颗本次数据源未包含的卫星（按编号增量更新）。'
                  % n_kept)

    if not data.strip():
        raise RuntimeError('星历数据源返回了空的卫星 TLE 数据。')
    report('正在写入星历缓存…')
    os.makedirs(os.path.dirname(cache_path) or '.', exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(data)
    return data


# ---------------------------------------------------------------------------
#  OMM/Celestrak CSV → 重建 TLE 两行
# ---------------------------------------------------------------------------

def _tle_checksum(line68):
    """TLE 校验和（第 69 列）：数字求和、'-' 记 1、其余记 0，对 10 取模。"""
    total = 0
    for ch in line68:
        if '0' <= ch <= '9':
            total += ord(ch) - 48
        elif ch == '-':
            total += 1
    return str(total % 10)


def _tle_exp_field(value):
    """数值 → 行 1 的 8 字符指数场 ±NNNNN±N（表示 0.NNNNN×10^±N）。

    用于 BSTAR / 平均运动二阶导场；0 写作 `` 00000+0``（与 Celestrak 一致）。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v == 0:
        return ' 00000+0'
    sign = '-' if v < 0 else ' '
    v = abs(v)
    exp = 0
    while v >= 1.0:
        v /= 10.0
        exp += 1
    while v < 0.1:
        v *= 10.0
        exp -= 1
    digits = int(round(v * 1e5))        # v ∈ [0.1, 1) → 5 位尾数
    if digits >= 100000:                # 0.99999… 四舍五入进位
        digits = 10000
        exp += 1
    return '%s%05d%s%d' % (sign, digits, '+' if exp >= 0 else '-', abs(exp))


def _tle_ndot_field(value):
    """平均运动一阶导 → 行 1 的 10 字符场 ±.NNNNNNNN（正号用空格）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v == 0:
        v = 0.0                         # 归一 -0.0，避免输出 '-.00000000'
    return ('% .8f' % v).replace('0.', '.', 1)


def _tle_epoch_field(epoch_text):
    """CSV 的 EPOCH（ISO 8601，可带 Z 后缀）→ 行 1 历元场 YYDDD.DDDDDDDD。"""
    dt = datetime.fromisoformat(str(epoch_text).strip())
    frac = (dt.hour * 3600 + dt.minute * 60 + dt.second
            + dt.microsecond / 1e6) / 86400.0
    frac8 = int(round(frac * 1e8))
    if frac8 >= 100000000:              # 一天进位（理论上到不了），钳住
        frac8 = 99999999
    return '%02d%03d.%08d' % (dt.year % 100, dt.timetuple().tm_yday, frac8)


def _csv_tle_colmap(header_line):
    """识别「星历 CSV」表头（Celestrak OMM 风格），返回 {列名大写: 下标}。

    必须同时具备 NORAD_CAT_ID / EPOCH / MEAN_MOTION / ECCENTRICITY /
    INCLINATION 五列才认定是星历 CSV（避免把碰巧含逗号的 TLE 名称行
    误判成表头）；否则返回 None，交回普通 TLE 解析。
    """
    s = (header_line or '').lstrip('\ufeff').strip()
    if not s or ',' not in s:
        return None
    try:
        cols = [c.strip().upper() for c in next(csv.reader([s]))]
    except (StopIteration, csv.Error):
        return None
    for required in ('NORAD_CAT_ID', 'EPOCH', 'MEAN_MOTION',
                     'ECCENTRICITY', 'INCLINATION'):
        if required not in cols:
            return None
    return {c: i for i, c in enumerate(cols)}


def _csv_cell(row, idx, default=''):
    """取 CSV 行的第 idx 列并去首尾空白；越界/缺列给 default。"""
    if idx is None or not (0 <= idx < len(row)):
        return default
    return (row[idx] or '').strip()


def _csv_num(row, idx, default=0.0):
    """取 CSV 行第 idx 列的浮点值；空/非法给 default。"""
    s = _csv_cell(row, idx)
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _iter_csv_tle_records(lines, colmap):
    """把 OMM/星历 CSV 的数据行**重建**为 TLE 两行并逐条产出。

    Celestrak 的 FORMAT=csv 返回的是分散的轨道根数（没有现成的 TLE 行）。
    实测其 CSV 各列就是 TLE 场的完整精度展开（一阶导/二阶导/BSTAR 与
    TLE 场同值同义，并非再除 2/除 6 的「物理量」），因此逐场照抄格式化
    即可高保真拼回 line1/line2（含校验和）：

      - EPOCH（ISO 8601）→ YYDDD.DDDDDDDD；
      - BSTAR / 一阶导 → 5 位尾数指数场 / ±.NNNNNNNN 场；
      - 偏心率 → 8 位小数展开后截前 7 位（与官方 TLE 一致）；
      - 倾角/升交点/幅角/平近点角 4 位小数、平均运动 8 位小数，直抄。
    个别行字段不合法时跳过该行，不影响其它行。
    """
    i_name = colmap.get('OBJECT_NAME')
    i_id = colmap.get('OBJECT_ID')
    i_epoch = colmap['EPOCH']
    i_mm = colmap['MEAN_MOTION']
    i_ecc = colmap['ECCENTRICITY']
    i_inc = colmap['INCLINATION']
    i_raan = colmap.get('RA_OF_ASC_NODE')
    i_argp = colmap.get('ARG_OF_PERICENTER')
    i_ma = colmap.get('MEAN_ANOMALY')
    i_norad = colmap['NORAD_CAT_ID']
    i_elset = colmap.get('ELEMENT_SET_NO')
    i_rev = colmap.get('REV_AT_EPOCH')
    i_bstar = colmap.get('BSTAR')
    i_ndot = colmap.get('MEAN_MOTION_DOT')
    i_nddot = colmap.get('MEAN_MOTION_DDOT')
    i_eph = colmap.get('EPHEMERIS_TYPE')
    i_cls = colmap.get('CLASSIFICATION_TYPE')
    need = max(i_epoch, i_mm, i_ecc, i_inc, i_norad)

    reader = csv.reader(lines)
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error:
            continue                    # 单行畸形：跳过继续
        if not row or len(row) <= need:
            continue
        # 卫星编号（TLE 场 5 位、补前导 0）
        try:
            satnum = '%05d' % int(float(_csv_cell(row, i_norad) or ''))
        except (TypeError, ValueError):
            continue
        if int(satnum) <= 0:
            continue
        # 历元（ISO 8601 → YYDDD.DDDDDDDD）
        try:
            epoch = _tle_epoch_field(_csv_cell(row, i_epoch))
        except ValueError:
            continue

        ecc = max(0.0, min(_csv_num(row, i_ecc), 0.9999999))
        ecc7 = ('%.8f' % ecc).replace('0.', '', 1)[:7]
        line2 = ('2 %s %8.4f %8.4f %s %8.4f %8.4f %11.8f%s'
                 % (satnum,
                    _csv_num(row, i_inc), _csv_num(row, i_raan),
                    ecc7,
                    _csv_num(row, i_argp), _csv_num(row, i_ma),
                    _csv_num(row, i_mm), '%5s' % _csv_cell(row, i_rev)))
        line2 += _tle_checksum(line2)

        # 国际代号：OBJECT_ID「YYYY-NNNPP」→ TLE 场「YYNNNPP  」（右对齐 8 位）
        raw_id = _csv_cell(row, i_id)
        if '-' in raw_id:
            head, _, tail = raw_id.partition('-')
            intl = (head[2:] + tail) if (len(head) == 4 and head.isdigit()) \
                else raw_id
        else:
            intl = raw_id
        intl = intl.ljust(8)[:8]
        line1 = ('1 ' + satnum + (_csv_cell(row, i_cls, 'U') or 'U')[:1]
                 + ' ' + intl + ' ' + epoch + ' '
                 + _tle_ndot_field(_csv_num(row, i_ndot)) + ' '
                 + _tle_exp_field(_csv_num(row, i_nddot)) + ' '
                 + _tle_exp_field(_csv_num(row, i_bstar)) + ' '
                 + (_csv_cell(row, i_eph, '0') or '0')[:1]
                 + ' ' + '%4s' % _csv_cell(row, i_elset))
        line1 += _tle_checksum(line1)

        name = _csv_cell(row, i_name) or _csv_cell(row, i_id) or satnum
        yield norad_key(satnum) or ('name:' + name), name, line1, line2


def iter_tle_records(text):
    """逐条产出 TLE 记录：(norad 编号, 名称, line1, line2)。

    兼容三种排版：①「名称行 + line1 + line2」（3LE）；② 只有 line1 + line2
    （2LE，此时用编号当名称）；③ Celestrak OMM 风格 CSV（首行为表头，数据行
    的轨道根数会**重建**成 TLE 两行，见 _iter_csv_tle_records）。
    无法识别的行直接跳过。
    编号已按 norad_key 规整（去掉前导 0），不同数据源的补位差异不会造成重复。
    """
    lines = [ln.strip('\r') for ln in (text or '').splitlines() if ln.strip()]
    if lines:
        colmap = _csv_tle_colmap(lines[0])
        if colmap is not None:
            yield from _iter_csv_tle_records(lines[1:], colmap)
            return
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].startswith('1 ') and i + 1 < n and lines[i + 1].startswith('2 '):
            name = lines[i][2:7].strip()
            l1, l2 = lines[i], lines[i + 1]
            i += 2
        elif (not lines[i].startswith('1 ') and i + 2 < n and
              lines[i + 1].startswith('1 ') and lines[i + 2].startswith('2 ')):
            name = lines[i].strip()
            l1, l2 = lines[i + 1], lines[i + 2]
            i += 3
        else:
            i += 1
            continue
        yield (norad_key(l1[2:7]) or ('name:' + name)), name, l1, l2


def merge_tle_texts(*texts):
    """按 NORAD 编号合并多段 TLE 文本：**靠前的文本优先**，同一编号只保留第一次出现。

    用于两类场景：
      - 多数据源合并：列表顺序即优先级，靠前的源覆盖靠后的源；
      - 下载结果与本地缓存合并：新数据优先，缓存里多出来的旧卫星被保留下来。
    """
    records = []
    seen = set()
    for text in texts:
        for norad_id, name, line1, line2 in iter_tle_records(text):
            if norad_id in seen:
                continue
            seen.add(norad_id)
            records.extend((name, line1, line2))
    return '\n'.join(records) + ('\n' if records else '')


def _merge_tle_texts(texts):
    """兼容旧接口：等价于 merge_tle_texts(*texts)。"""
    return merge_tle_texts(*texts)


def satellites_to_tle_text(sats):
    """把 [(name, Satrec), ...] 还原为「名称 + 两行」的 TLE 文本。"""
    blocks = []
    for name, sat in (sats or []):
        line1 = getattr(sat, 'line1', '')
        line2 = getattr(sat, 'line2', '')
        if not (line1 and line2):
            continue
        blocks.append('%s\n%s\n%s' % (name, line1, line2))
    return '\n'.join(blocks) + ('\n' if blocks else '')


def write_tle_cache(sats, cache_path=TLE_CACHE):
    """把当前卫星列表写回本地星历缓存（供「导入星历」后持久化）。

    内容为空时不写，避免把已有缓存清空。返回写入的字符数（0 = 未写入）。
    """
    text = satellites_to_tle_text(sats)
    if not text.strip():
        return 0
    os.makedirs(os.path.dirname(cache_path) or '.', exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return len(text)


def parse_tle_text(text):
    """把 Celestrak 格式 TLE 文本（每行 名称/Line1/Line2 为一组）解析为
    [(name, Satrec), ...]。

    逐条解析，单条数据非法（校验和/格式问题）时跳过该条而非整体失败。
    """
    sats = []
    for norad_id, name, l1, l2 in iter_tle_records(text):
        try:
            satrec = twoline2rv(l1, l2, name=name)
            sats.append((name, satrec))
        except Exception:
            continue
    return sats


def load_amateur_satellites(cache_path=TLE_CACHE, force=False):
    """下载/读取全部活动卫星 TLE 并返回 [(name, Satrec), ...]。"""
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


def open_text_config(path, header):
    """统一配置文件说明后用系统记事本打开。"""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    try:
        old = _read_text(path) if os.path.exists(path) else ''
        data_lines = [line.strip() for line in old.splitlines()
                      if line.strip() and not line.lstrip().startswith('#')]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(header.rstrip() + '\n')
            if data_lines:
                f.write('\n'.join(data_lines) + '\n')
    except OSError:
        pass
    try:
        subprocess.Popen(['notepad.exe', os.path.abspath(path)])
    except OSError:
        return False
    return True


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


def tqsl_sat_name(name, path=TQSL_DICT_PATH, number=None):
    """把卫星显示名转换为 TQSL/LoTW 认可的名称；无映射时返回原名。

    映射表以 NORAD 编号为键（见 :func:`migrate_legacy_sat_data`）。
    ``number`` 缺省时按 ``name`` 现查出编号再查表，因此旧调用点无需改动；
    显式传入编号可省掉一次名称→编号解析（批量场景更快）。
    """
    table = load_tqsl_dict(path)
    key = lookup_table_key(table, name, number)
    if key is None:
        return name
    return table[key]


def has_tqsl_mapping(name, path=TQSL_DICT_PATH, number=None):
    """判断该卫星是否存在 TQSL/LoTW 映射（存在返回 True，否则 False）。"""
    return lookup_table_key(load_tqsl_dict(path), name, number) is not None


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


def normalize_sat_name(name):
    """卫星名归一化：忽略大小写、空格、短横线、下划线、括号等一切非字母数字字符。

    用于「宽松比较」——同一颗卫星在不同来源里写法可能不同，例如
    ``AO-91`` / ``AO 91`` / ``AO_91`` / ``ao91`` 归一化后均为 ``AO91``；
    TLE 名称行还有定宽填充导致的尾随空格，也应视为同一颗星。

    只保留字母数字（其余字符一律丢弃），因此 ``SAUDISAT 1C (SO-50)``
    归一化后为 ``SAUDISAT1CSO50``，用 ``so50`` 也能搜到。

    额外做一次 NFKC 兼容折叠（``unicodedata.normalize``）：把**全角**字符折成半角，
    例如 ``ＡＳＲＴＵ－１`` → ``ASRTU-1``。中文输入法切到「全角」时打出来的字母/数字
    看起来和半角几乎一样，但 ``str.isalnum()`` 对全角字母/数字同样返回 True，
    于是它们能通过下面的过滤、却永远匹配不上半角名称，表现为
    「明明输入了 ASRTU-1 却搜不到」。按半角/全角折叠后这类输入即可正常工作。
    """
    text = unicodedata.normalize('NFKC', name or '')
    return ''.join(ch for ch in text.upper() if ch.isalnum())


def sat_name_match(name, keywords):
    """归一化后的宽松匹配：name 同时包含 keywords 中每一个关键词才命中。

    keywords 为空/全空表示不过滤（全部命中）。关键词本身也应先经
    :func:`normalize_sat_name` 处理，使输入与卫星名的写法差异被抹平。
    """
    if not keywords:
        return True
    norm = normalize_sat_name(name)
    return all(k in norm for k in keywords if k)


def parse_sat_keywords(text):
    """把搜索框文本拆成归一化关键词列表（按空白分隔，多词之间为「与」关系）。

    例如 ``'so 50'`` → ``['SO', '50']``，``'ao-91'`` → ``['AO91']``。
    """
    return [k for k in (normalize_sat_name(t) for t in (text or '').split())
            if k]


def sat_number_match(number, keywords):
    """按卫星编号（NORAD ID）宽松匹配：编号里包含任一关键词即命中。

    与 :func:`sat_name_match` 的「与」关系不同，编号是一串数字、没有「词」的概念，
    多个关键词之间取「或」——输入 ``61 781`` 同样能命中 ``61781``。

    归一化沿用 :func:`norad_key`：去掉前导 0（``061781`` → ``61781``），从而兼容
    不同数据源的补位写法；关键词也先过一遍，使输入写法差异被抹平。

    用途：TLE 名称行里的卫星名往往不含编号（如 ``ASRTU-1 (RS64S/BJ2CR)`` 对应编号
    ``61781``），只按名称搜是搜不到编号的，需配合「使用卫星编号搜索」开关。
    """
    if not keywords:
        return True
    num = norad_key(str(number if number is not None else ''))
    if not num:
        return False
    return any(norad_key(k) in num for k in keywords if k)


def satellite_number_map(sats):
    """由 ``[(name, Satrec), ...]`` 构建「卫星名 → NORAD 编号」映射，供按编号搜索。

    取不到编号时（极少见的手工数据）回退为空串，该星即不参与编号匹配，
    与 :func:`sat_key` 的兜底思路一致——但这里宁可「搜不到」也不拿名称冒充编号，
    避免按编号搜索时出现莫名其妙的命中。
    """
    out = {}
    for name, sat in (sats or []):
        num = getattr(sat, 'satnum', '')
        out[name] = '' if num is None else num
    return out


# ---------------------------------------------------------------------------
#  数据一律以「卫星编号」为键：编号 ⇄ 名称的解析与展示
# ---------------------------------------------------------------------------
#
# 背景：卫星名会随数据源变动。同一颗星在不同星历里可能叫
# ``ASRTU-1 (AO-123)`` 或 ``ASRTU-1 (RS64S/BJ2CR)``，而 NORAD 编号恒定。
# 因此凡是需要长期保存、要跨越星历更新的数据（自选卫星列表 sat_sats、
# 转发器表 sat_radio_dict.txt、TQSL 映射表 tqsl_dict.txt）一律以编号为键，
# 只在**显示/编辑**时按「当前星历」把编号还原成卫星名。
#
# 例外：取不到编号的条目（卫星已退役、名称对不上、用户自定义名称）一律
# **原样保留**，既不丢弃也不冒充编号；显示时原样呈现。

_sat_index_cache = {'key': None, 'by_name': {}, 'by_num': {}}


def sat_name_aliases(name):
    """产出一颗卫星名在星历里的各种写法（均归一化），供名称 → 编号解析。

    用户和旧数据里写的往往是短名，而 TLE 名称行写的是长名，必须都能对上：
      ``SAUDISAT-1C (SO-50)`` → ``SAUDISAT1CSO50``（全名）、``SO50``（括号内短名）、
      ``SAUDISAT1C``（去掉括号部分）；``ISS (ZARYA)`` → 另有 ``ZARYA`` / ``ISS``。
    返回按优先级排序的别名列表（全名在前），空名返回空列表。
    """
    text = (name or '').strip()
    if not text:
        return []
    aliases = [normalize_sat_name(text)]
    for inner in re.findall(r'\(([^)]*)\)', text):
        aliases.append(normalize_sat_name(inner))
    first = re.search(r'\(', text)
    if first:
        aliases.append(normalize_sat_name(text[:first.start()]))
    out, seen = [], set()
    for a in aliases:
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def load_sat_index(cache_path=None, force=False):
    """构建当前星历的「归一化名称 → 编号」「编号 → 原始名称」两份索引。

    只解析 TLE 文本本身（不构造 Satrec、不跑 SGP4），几万条也是毫秒级；
    结果按缓存文件的 mtime 自动失效，星历刷新后下次调用即得新索引。
    文件缺失或解析异常时返回两张空表——调用方据此退回「原样处理」，
    绝不抛异常（迁移与展示链路都要求静默）。
    """
    path = cache_path or TLE_CACHE
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return {}, {}
    key = (path, stamp)
    if not force and _sat_index_cache.get('key') == key:
        return _sat_index_cache['by_name'], _sat_index_cache['by_num']
    by_name, by_num = {}, {}
    try:
        for norad_id, name, _l1, _l2 in iter_tle_records(_read_text(path)):
            num = norad_key(norad_id)
            if not num:
                continue
            for alias in sat_name_aliases(name):
                by_name.setdefault(alias, num)
            by_num.setdefault(num, (name or '').strip() or num)
    except Exception:
        return {}, {}
    _sat_index_cache['key'] = key
    _sat_index_cache['by_name'] = by_name
    _sat_index_cache['by_num'] = by_num
    return by_name, by_num


def sat_number_of(key, cache_path=None):
    """把「卫星名或编号」解析为归一化编号；解析不出来时返回空串。

    已是编号（纯数字，或当前星历里存在的 Alpha-5 编号）时直接规整采用；
    否则按归一化名称查一次当前星历。查不到返回 ``''``——调用方应**保持原值**
    而不是清空，避免把对不上的历史数据丢掉。
    """
    text = str(key if key is not None else '').strip()
    if not text:
        return ''
    num = norad_key(text)
    by_name, by_num = load_sat_index(cache_path)
    if num and (num in by_num or num.isdigit()):
        return num
    return by_name.get(normalize_sat_name(text), '')


def sat_display_name(key, cache_path=None):
    """把内部保存的「编号」还原为「当前星历里的卫星名」；查不到时原样返回。

    也接受直接写的卫星名（尚未迁移的旧数据）：先按名查出编号，再统一显示成
    当前星历里的规范名称，避免同一颗星在界面上出现两种写法。
    星历里没有该编号（卫星已退役 / 尚未收录、或用户自定义名称）时原样返回，
    保证界面上永远看得到一个标识，而不是空白。
    """
    text = str(key if key is not None else '').strip()
    if not text:
        return ''
    by_name, by_num = load_sat_index(cache_path)
    num = norad_key(text)
    if num not in by_num:
        num = by_name.get(normalize_sat_name(text), '')
    return by_num.get(num) or text


def normalize_sat_keys(items):
    """把一串「卫星名 / 编号」规整为去重后的编号列表（保持首次出现顺序）。

    用于读取旧数据时即时升级：拿到 ``['ASRTU-1 (RS64S/BJ2CR)', '61781']``
    这类混合列表，统一折成编号并去重。解析不出编号的条目原样保留。
    """
    out, seen = [], set()
    for item in (items or []):
        text = str(item if item is not None else '').strip()
        if not text:
            continue
        num = sat_number_of(text) or text
        if num in seen:
            continue
        seen.add(num)
        out.append(num)
    return out


def lookup_table_key(table, name, number=None):
    """在一张「以卫星编号为键」的表里找到该卫星对应的键；找不到返回 None。

    先按编号命中（表已迁移后的标准形态）；再按原始名称、最后按归一化名称
    兜底，兼容尚未迁移成编号的旧表（旧表的键就是卫星显示名）。
    """
    if not table:
        return None
    num = (norad_key(str(number)) if number not in (None, '')
           else sat_number_of(name))
    if num and num in table:
        return num
    text = (name or '').strip()
    if not text:
        return None
    if text in table:
        return text
    target = normalize_sat_name(text)
    if target:
        for k in table:
            if normalize_sat_name(k) == target:
                return k
    return None


def lookup_transponder(bands, name, number=None):
    """按卫星在转发器表中查找条目（表以 NORAD 编号为键）。

    先按编号精确命中——编号跨数据源稳定，星历换源改名也不会失效；再按名称
    逐级兜底，兼容尚未迁移成编号的旧表：
      1. 原始 TLE 名；
      2. TQSL/LoTW 映射后的名称（tqsl_sat_name）；
      3. 名称中括号内的短名（如 ``(SO-50)``）；
      4. 括号内短名再做 TQSL 映射；
      5. 以上各项的大小写不敏感匹配；
      6. 归一化匹配（忽略空格/短横线/下划线，与搜索框逻辑一致），
         例如表中键写作 ``AO-91`` 而 TLE 名为 ``AO 91`` 也能命中；
      7. 编号的归一化匹配（表里的键写成 ``0061781`` / 全角数字等也命中）。
    ``number`` 缺省时按 ``name`` 现查出编号。全部未命中返回 None。
    """
    if not name and number in (None, ''):
        return None
    key = (norad_key(str(number)) if number not in (None, '')
           else sat_number_of(name))
    if key and key in bands:
        return bands[key]
    cands = [name, tqsl_sat_name(name)]
    m = re.search(r'\(([^)]+)\)', name or '')
    if m:
        inner = m.group(1).strip()
        cands.append(inner)
        cands.append(tqsl_sat_name(inner))
    for c in cands:
        c = (c or '').strip()
        if c in bands:
            return bands[c]
    # 大小写不敏感兜底
    up = {k.upper(): bands[k] for k in bands}
    for c in cands:
        c = (c or '').strip().upper()
        if c in up:
            return up[c]
    # 归一化兜底：忽略空格/短横线等差异（与搜索框的匹配逻辑保持一致）
    norm = {normalize_sat_name(k): bands[k] for k in bands}
    for c in cands:
        v = norm.get(normalize_sat_name(c))
        if v is not None:
            return v
    # 编号兜底：表里的键写成 0061781 / 全角数字等非规范写法时同样命中
    if key:
        for k in bands:
            if norad_key(k) == key:
                return bands[k]
    return None


# ---------------------------------------------------------------------------
#  旧版数据升级：卫星名 → 卫星编号
# ---------------------------------------------------------------------------

# 设置文件里需要升级为编号的自选卫星键（sat_mu_sats 是更早版本的键名）
_SELECTED_KEYS = ('sat_sats', 'sat_mu_sats')


def _migrate_settings_sats():
    """把设置文件 m_xml.txt 里的自选卫星列表由「名称」改写为「编号」。"""
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            settings = eval(f.read())
    except Exception:
        return 0
    if not isinstance(settings, dict):
        return 0
    changed = 0
    for name in _SELECTED_KEYS:
        raw = settings.get(name)
        if not isinstance(raw, list):
            continue
        new = sorted(set(normalize_sat_keys(raw)))
        if new != raw:
            settings[name] = new
            changed += 1
    if not changed:
        return 0
    try:
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            f.write(str(settings))
    except Exception:
        return 0
    return changed


# 旧版注释里的字段说明 → 迁移时顺带更正，避免「文件里的说明」与「实际键」
# 不一致（否则用户手打开文件会以为要填卫星名）。
_LEGACY_HEADER_FIXES = (
    ('格式：卫星名=', '格式：卫星编号(NORAD ID)='),
    ('格式：卫星显示名=', '格式：卫星编号(NORAD ID)='),
    ('格式：显示名=', '格式：卫星编号(NORAD ID)='),
)


def _migrate_dict_file(path):
    """把「键=值」文本文件的键由卫星名改写为编号；逐条失败即原样跳过。

    注释行与空行原样保留（只把其中「格式：卫星名=…」这类字段说明改成编号口径）；
    同一颗卫星出现多行时按读取语义**合并为一行（后者覆盖前者）**——旧表里常用
    「短名 + 长名」两行指向同一颗星，换成编号后就变成重复键了。
    整份文件没有任何改动时不写回，避免无谓地动用户的文件。
    """
    try:
        if not os.path.exists(path):
            return 0
        lines = _read_text(path).splitlines()
    except Exception:
        return 0
    out, changed, header_fixed = [], 0, 0
    seen = {}          # 新键 → out 中的下标（用于合并重复键）
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            fixed = stripped
            for old, new in _LEGACY_HEADER_FIXES:
                if old in fixed:
                    fixed = fixed.replace(old, new)
            if fixed != stripped:
                header_fixed += 1
            out.append(fixed)
            continue
        if not stripped or '=' not in stripped:
            out.append(line.rstrip('\r'))
            continue
        key, rest = stripped.split('=', 1)
        old = key.strip()
        new = sat_number_of(old) or old      # 解析不出编号 → 保持原键
        if new != old:
            changed += 1
        item = '%s=%s' % (new, rest.strip())
        if new in seen:
            out[seen[new]] = item            # 重复键：后者覆盖前者（与读取语义一致）
            continue
        seen[new] = len(out)
        out.append(item)
    if not (changed or header_fixed):
        return 0
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(out) + '\n')
    except Exception:
        return 0
    return changed


def migrate_legacy_sat_data(cache_path=None):
    """把旧版以「卫星名」为键的数据统一升级为「NORAD 编号」。

    覆盖三类数据：
      - 设置文件 file/m_xml.txt 的自选卫星 ``sat_sats`` / ``sat_mu_sats``；
      - file/sat_radio_dict.txt（卫星转发器表，快速记录预填频率用）；
      - file/tqsl_dict.txt（TQSL / LoTW 卫星名称映射表）。

    逐条解析：能查到编号就改写为编号；查不到（卫星已退役、名称对不上、
    用户自定义名称）就**原样跳过**，绝不丢数据。整个过程幂等、静默——
    不弹窗、不打断、不打印，任何异常都被吞掉。启动时调用一次即可。

    返回各来源的改写条数统计（供测试断言；正常运行时不使用）。
    """
    report = {'settings': 0, 'radio': 0, 'tqsl': 0}
    by_name, _ = load_sat_index(cache_path)
    if not by_name:
        return report      # 没有可用星历 → 无从升级，一切原样保留
    report['settings'] = _migrate_settings_sats()
    report['radio'] = _migrate_dict_file(SAT_RADIO_DICT_PATH)
    report['tqsl'] = _migrate_dict_file(TQSL_DICT_PATH)
    return report


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
