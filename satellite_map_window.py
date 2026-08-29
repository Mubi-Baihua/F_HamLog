# -*- coding: utf-8 -*-
"""
satellite_map_window.py —— 卫星地图窗口（PySide6，纯 QPainter 绘制，无额外依赖）

由「卫星过境预测」窗口或「通联预测」窗口的「地图」按钮打开。
显示：
  - 全球等距圆柱投影地图（海洋 + 陆地 + 经纬网格，陆地数据来自
    file/world_land.json，Natural Earth 110m 低精度多边形，已随项目打包）；
  - 「所有已选择的卫星」（与来源窗口的 范围 / 自选卫星 实时同步）的地面轨迹，
    每颗一色；轨迹为 **从当前时刻起、向后延伸「轨迹时长」小时** 的未来星下点
    连线（已处理 ±180° 换日线断裂）；
  - 各卫星当前位置（每秒实时刷新星下点）与覆盖区（footprint）圆圈；
  - 本台站位置（来自观测站设置；通联预测时还显示对方台站 B）。

在来源窗口表格里点选某颗卫星，该星会成为「聚焦卫星」：轨迹加粗、显示覆盖区，
信息栏给出其实时经纬度与仰角。轨迹上「本台站可见」（仰角 ≥ 最低仰角）的区段
会用实线加粗标出，其余为半透明细线；通联预测（对方台站 B 存在）时，对方台站
可见区段同样用卫星颜色加粗、但以虚线区分，便于一眼分辨两站各自能看到的弧段。

「轨迹时长」与来源窗口的「预测时长」(sat_dur) 是两个独立的量：预测时长决定
过境 / 通联的搜索跨度（最长 240 小时），轨迹时长只影响地图上画多长一段星下点
连线（最长 24 小时，再长就会画出十几圈、糊成一片）。轨迹时长单独保存在
sat_map_hours，关窗后仍然记住；「卫星过境预测」与「通联预测」各自打开的地图
共用这一个值，任意一边调整都会实时同步到另一边。
"""

import json
import math
import datetime
import os
import sys

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QFrame, QSizePolicy, QDialog,
    QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView,
    QAbstractItemView, QPlainTextEdit, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QPixmap, QFont,
)

import satellite_pred as sp
# 复用卫星过境预测窗口的设置读写（单向依赖：satellite_window 只在函数内部
# 延迟 import 本模块，因此这里的顶层 import 不会造成循环导入）
from satellite_window import _load_settings, _save_settings

WORLD_LAND_PATH = sp.app_path('file/world_land.json')

# 防止窗口在 open_map() 返回后被 Python 回收
_open_windows = []

_LAND_CACHE = None

_EARTH_R_KM = 6371.0

# 地图同时显示的卫星数量上限（可在界面「最多显示的卫星」中调整）
DEFAULT_MAX_SHOW = 30
MAX_SHOW_LIMIT = 200

# 轨迹采样密度：约每分钟一个点，并钳制在 [120, 720]。
# 固定点数不可行——LEO 卫星一圈约 90 分钟，24 小时有 ~16 圈；若总点数固定为 180，
# 每圈只剩 11 个点，折线会明显失真、多圈之间也看不出西向漂移。
TRACK_MIN_SAMPLES = 120
TRACK_MAX_SAMPLES = 720


def _track_samples(hours):
    return max(TRACK_MIN_SAMPLES, min(TRACK_MAX_SAMPLES, int(hours * 60)))

# 轨迹重算间隔（秒）。轨迹起点是「当前时刻」，需随时间推进定期重算。
TRACK_REFRESH_SEC = 60

# ---------------------------------------------------------------------------
#  轨迹时长（小时）
#  与「预测时长」(sat_dur, 最长 240 小时) 分开记录：预测时长决定过境/通联的
#  搜索跨度，可以很长；地图轨迹只是可视化，超过一天就会画出十几圈、糊成一片，
#  因此单独用 sat_map_hours 保存，并限制在 24 小时以内。
#  该值由「卫星过境预测」与「通联预测」打开的地图窗口共用：任一处修改都会
#  立即同步到另一处，并落盘供下次打开时恢复。
# ---------------------------------------------------------------------------
MIN_TRACK_HOURS = 1
MAX_TRACK_HOURS = 24
DEFAULT_TRACK_HOURS = 3
TRACK_HOURS_KEY = 'sat_map_hours'


def clamp_track_hours(h):
    try:
        h = int(round(float(h)))
    except (TypeError, ValueError):
        return DEFAULT_TRACK_HOURS
    return max(MIN_TRACK_HOURS, min(MAX_TRACK_HOURS, h))


def load_track_hours():
    """读取上次使用的轨迹时长（越界或缺失时回落到默认值）。"""
    try:
        return clamp_track_hours(
            _load_settings().get(TRACK_HOURS_KEY, DEFAULT_TRACK_HOURS))
    except Exception:
        return DEFAULT_TRACK_HOURS


def save_track_hours(h):
    """把轨迹时长写入 file/m_xml.txt，供下次打开地图时恢复。"""
    try:
        s = _load_settings()
        s[TRACK_HOURS_KEY] = clamp_track_hours(h)
        _save_settings(s)
    except Exception:
        pass


def _broadcast_track_hours(h, exclude=None):
    """把轨迹时长同步给其他已打开的地图窗口。

    「卫星过境预测」与「通联预测」可以各开一个地图窗口，两边应当始终一致。
    """
    for w in list(_open_windows):
        if w is exclude:
            continue
        try:
            w.set_track_hours(h)
        except Exception:
            pass


def _broadcast_min_elev(origin, a, b):
    """把最低仰角（本台 a / 对方 b）同步给其他已打开的地图窗口。

    仅更新其他地图窗口的显示与控件，**不**触发它们的来源窗口回调，避免因
    两处来源窗口各自持久化而互相反复写入。发起修改的那一侧由自己的来源窗口
    负责落盘（与轨迹时长的广播策略一致）。

    对方台站阈值 b 只在「发起修改的窗口本身有对方台站」时才广播——卫星过境
    预测没有对方台，其 _min_elev_b 仅是本台阈值的回退值，不应覆盖通联预测
    地图里真正生效的对方阈值。
    """
    push_b = bool(getattr(origin, '_station_b_valid', lambda: False)())
    for w in list(_open_windows):
        if w is origin:
            continue
        try:
            w.set_min_elev(a)
            if push_b:
                w.set_min_elev_b(b)
        except Exception:
            pass

# 多星配色（依显示顺序循环取用）
_PALETTE = [
    (214, 48, 48), (30, 110, 200), (36, 150, 80), (205, 120, 20),
    (140, 60, 180), (0, 148, 158), (192, 60, 130), (108, 122, 40),
    (60, 90, 190), (200, 84, 56), (20, 140, 132), (150, 100, 200),
    (170, 90, 30), (70, 130, 60), (120, 70, 140), (40, 120, 170),
]


def _color_for(index):
    r, g, b = _PALETTE[index % len(_PALETTE)]
    return QColor(r, g, b)


MAP_MARKERS_KEY = 'sat_map_markers'
MAP_TWILIGHT_KEY = 'sat_map_show_twilight'
DEFAULT_TWILIGHT_VISIBLE = True
MARKERS_PATH = sp.app_path('file/sat_map_markers.txt')


def _marker_color(index):
    return _color_for(index)


def _normalize_marker(marker, index=0):
    if not isinstance(marker, dict):
        return {'name': f'标记点 {index + 1}', 'lat': 0.0, 'lon': 0.0, 'color': _marker_color(index).name()}
    try:
        lat = float(marker.get('lat', 0.0) or 0.0)
        lon = float(marker.get('lon', 0.0) or 0.0)
    except Exception:
        lat, lon = 0.0, 0.0
    name = str(marker.get('name') or f'标记点 {index + 1}')
    color = str(marker.get('color') or '').strip()
    if not color:
        color = _marker_color(index).name()
    try:
        QColor(color)
    except Exception:
        color = _marker_color(index).name()
    return {'name': name, 'lat': lat, 'lon': lon, 'color': color}


def load_map_markers():
    """读取地图标记点列表（独立文件 file/sat_map_markers.txt）。"""
    try:
        if not os.path.exists(MARKERS_PATH):
            return []
        with open(MARKERS_PATH, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
        out = []
        for idx, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if '=' not in s:
                continue
            key, rest = s.split('=', 1)
            key = key.strip()
            if not key:
                continue
            parts = [p.strip() for p in rest.split(',')]
            if len(parts) < 2:
                continue
            try:
                lat = float(parts[0])
                lon = float(parts[1])
            except ValueError:
                continue
            color = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else _marker_color(len(out)).name()
            out.append({'name': key, 'lat': lat, 'lon': lon, 'color': color})
        return out
    except Exception:
        return []


def save_map_markers(markers):
    """保存地图标记点列表到独立的文本文件，不写入 m_xml.txt。"""
    try:
        items = []
        for idx, m in enumerate(markers or []):
            items.append(_normalize_marker(m, idx))
        os.makedirs(os.path.dirname(MARKERS_PATH) or '.', exist_ok=True)
        with open(MARKERS_PATH, 'w', encoding='utf-8') as f:
            f.write('# 地图标记点（格式：名称=纬度,经度,颜色）\n')
            for item in items:
                color = item['color']
                if not color:
                    color = _marker_color(len(items)).name()
                f.write(f"{item['name']}={item['lat']},{item['lon']},{color}\n")
        return items
    except Exception:
        return []


def open_map_markers_text():
    """用记事本编辑地图标记点 TXT。"""
    return sp.open_text_config(
        MARKERS_PATH,
        '# 地图标记点表\n# 格式：名称=纬度,经度,颜色\n'
        '# 例如：北京=39.9042,116.4074,#ff6600')


def _solar_declination_and_subsolar_lon(now_utc):
    """返回太阳赤纬与地理子太阳点经度，用于计算晨昏线。

    经度通过 黄道视黄经 → 赤道坐标赤经 → 格林尼治恒星时(GMST) 路径
    求得，避免直接把黄经当作地理经度导致东西翻转约 180° 的错误。
    """
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=datetime.timezone.utc)

    # Julian Date (JD)
    jd = (now_utc - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds() / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0          # J2000 起算的儒略世纪数

    # 太阳几何平黄经 (°)
    L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360.0
    # 太阳平近点角 (°)
    M = 357.52911 + T * (35999.05029 - T * 0.0001537)
    M_r = math.radians(M)
    # 地球轨道偏心率
    e = 0.016708634 - T * (0.000042037 + T * 0.0000001267)
    # 中心差方程 (°)
    C = (math.sin(M_r) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + math.sin(2 * M_r) * (0.019993 - 0.000101 * T)
         + math.sin(3 * M_r) * 0.000289)
    # 太阳真黄经 (°)
    sun_true_long = L0 + C
    # 近日点黄经 (°)
    omega = 125.04 - 1934.136 * T
    # 视黄经 (°) —— 章动与光行差修正
    lam = sun_true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    lam_r = math.radians(lam)

    # 黄赤交角 (°)
    eps0 = 23.439291 - 0.0130042 * T
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))   # 章动修正
    eps_r = math.radians(eps)

    # 赤纬 (°)
    decl = math.degrees(math.asin(math.sin(eps_r) * math.sin(lam_r)))

    # 赤经 (°) —— 从黄道坐标转赤道坐标
    y = math.sin(lam_r) * math.cos(eps_r)
    x = math.cos(lam_r)
    ra_deg = math.degrees(math.atan2(y, x)) % 360.0

    # 格林尼治平恒星时 GMST (°)
    gmst = (280.46061837
            + 360.98564736629 * (jd - 2451545.0)
            + 0.000387933 * T * T
            - T * T * T / 38710000.0) % 360.0

    # 地理子太阳点经度 (°, -180~180)
    # 当地恒星时 = GMST + 经度(东正)，令时角 H = 本地恒星时 - RA = 0 得
    # 子太阳点经度 = RA - GMST（东正）。注意符号，写反会导致晨昏线东西翻转。
    sun_lon = (ra_deg - gmst) % 360.0
    if sun_lon > 180.0:
        sun_lon -= 360.0

    return float(decl), float(sun_lon)


def compute_twilight_points(now_utc):
    """按当前日期与时刻计算晨昏线（太阳高度 0°）经纬度点列。"""
    decl, sun_lon = _solar_declination_and_subsolar_lon(now_utc)
    dec_r = math.radians(decl)
    pts = []
    for lon_deg in range(-180, 181):
        h = math.radians(lon_deg - sun_lon)
        denom = math.cos(dec_r) * math.cos(h)
        if abs(denom) < 1e-12:
            lat = 0.0 if abs(math.sin(dec_r)) < 1e-12 else math.copysign(90.0, math.sin(dec_r))
        else:
            tan_phi = -math.cos(h) / math.tan(dec_r)
            lat = math.degrees(math.atan(tan_phi))
        pts.append((float(lon_deg), float(lat)))
    return pts


def _load_land():
    """读取并缓存 Natural Earth 110m 陆地多边形。

    返回 list[ polygon ]；polygon = [ ring, ring, ... ]；ring = [ [lon, lat], ... ]。
    文件缺失或损坏时返回空列表（地图仍可显示海洋与网格）。
    """
    global _LAND_CACHE
    if _LAND_CACHE is not None:
        return _LAND_CACHE
    polys = []
    try:
        with open(WORLD_LAND_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for feat in data.get('features', []):
            g = feat.get('geometry') or {}
            t = g.get('type')
            coords = g.get('coordinates')
            if not coords:
                continue
            if t == 'Polygon':
                polys.append(coords)
            elif t == 'MultiPolygon':
                for poly in coords:
                    polys.append(poly)
    except Exception:
        polys = []
    _LAND_CACHE = polys
    return polys


def _ring_path(ring, W, H):
    """把一个 [lon, lat] 环转换为 QPainterPath（等距圆柱投影，直接线性映射）。

    **不要对陆地多边形做经度 unwrap（±360 平移）**：Natural Earth 数据已把所有
    多边形裁剪到 [-180, 180]，并且专为等距圆柱投影准备。南极洲的外环刻意包含
    一段「180° → -180°」的接缝（沿 lat = -90 的地图底边横跨闭合），unwrap 会把
    它误判为跨换日线，导致该环后半段被整体平移 +360° 推出画布右侧——表现为
    南极洲缺失 / 错位。直接按原始经度绘制才是正确做法。
    """
    path = QPainterPath()
    first = True
    for lon, lat in ring:
        x = (lon + 180) / 360.0 * W
        y = (90 - lat) / 180.0 * H
        if first:
            path.moveTo(x, y)
            first = False
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def _split_dateline(points):
    """把地面轨迹按 ±180° 换日线切成若干段连续折线。

    卫星地面轨迹会反复跨越换日线。在等距圆柱投影上必须在边界处**断开**、
    并从另一侧边界续画；若像早期实现那样对经度做累加式 ±360 平移，第一次
    跨线之后所有点会持续偏移，第二圈及以后的轨迹会被整体推出画布之外
    （表现为「只看得到一圈」或「两圈重合」）。

    参数 points: [(lon, lat, ...), ...]（允许带额外字段，只用前两项）
    返回 list[ list[(lon, lat)] ]，每段内部经度连续、均落在 [-180, 180]。
    """
    segs = []
    cur = []
    for pt in points:
        lon, lat = float(pt[0]), float(pt[1])
        if cur:
            plon, plat = cur[-1]
            d = lon - plon
            if abs(d) > 180.0:
                # 在边界处按纬度线性插值，得到两侧的接点
                if d > 180.0:        # 实际是向西跨越 -180°
                    e_out, e_in = -180.0, 180.0
                    denom = d - 360.0
                    t = (-180.0 - plon) / denom if denom else 0.0
                else:                # d < -180，向东跨越 +180°
                    e_out, e_in = 180.0, -180.0
                    denom = d + 360.0
                    t = (180.0 - plon) / denom if denom else 0.0
                t = max(0.0, min(1.0, t))
                lat_e = plat + t * (lat - plat)
                cur.append((e_out, lat_e))
                segs.append(cur)
                cur = [(e_in, lat_e)]
        cur.append((lon, lat))
    if len(cur) >= 2:
        segs.append(cur)
    return segs


def _footprint_radius_deg(alt_km):
    """卫星 0° 仰角覆盖区的地心半角（度）。"""
    if alt_km <= 0:
        return 0.0
    ratio = _EARTH_R_KM / (_EARTH_R_KM + alt_km)
    ratio = max(-1.0, min(1.0, ratio))
    return math.degrees(math.acos(ratio))


def _footprint_paths(lon, lat, ang, W, H, n=360):
    """计算 0° 仰角覆盖区（球面小圆）在等距圆柱投影上的填充多边形。

    返回 list[QPainterPath]，直接用于填充/描边。同时正确处理三类情况：

    1. 极地经度方向拉伸：用真实球面小圆边界，经度方向的角半径自动随
       ``1/cos(lat)`` 变宽——旧实现把覆盖区画成统一角半径的椭圆，在极地
       经度方向会被严重低估（甚至应收敛成绕极点的整圈，却画成一条窄带）。
    2. 覆盖区跨越极点（北极/南极）：对含极点的圆改用「按经度解边界纬度」
       生成单值边界曲线，再封成「极点帽」——而不是用方位角采样（越极点的
       边界点会被折叠到对面纬度，导致星下点正上方到极点的窄条漏填，
       且被画布顶/底边截断成残缺弧形）。
    3. 覆盖区跨越 ±180° 换日线：用 ``_split_dateline`` 断开续画。

    参数 lon/lat 为星下点经纬度（度），ang 为地心半角（度）。
    """
    if ang <= 0:
        return []
    lat_r = math.radians(lat)
    ang_r = math.radians(ang)
    sin_lat = math.sin(lat_r)
    cos_lat = math.cos(lat_r)
    cos_ang = math.cos(ang_r)
    sin_ang = math.sin(ang_r)
    north = (lat + ang) >= 90.0 - 1e-9
    south = (lat - ang) <= -90.0 + 1e-9
    if north or south:
        # 含极点：按经度解「单值边界纬度」——该经度处覆盖区的极侧边界。
        # 给定经度 lon_p，边界纬度满足
        #   cos(ang) = sin(lat_s)·sin(lat) + cos(lat_s)·cos(lat)·cos(Δlon)
        # 解 A·sin(lat)+B·cos(lat)=C 得两解 a1,a2（相差 180°）。规范到 [-90,90]
        # 后：含北极取北半球（≥0）的有效解、含南极取南半球（≤0）的有效解，封顶
        # /底即正确包含「星下点 → 极点」整条窄带。
        #
        # 关键：dlon **不**归一化到 [-180,180]。否则 lon_p=±180 会被折成不同值
        # （dlon=±180 vs 0），两端 lat_b 不连续、帽子封口错位（旧实现把整个画布
        # 填掉）。直接取 dlon = lon_p - lon（可能 ±360），cos 的周期性保证两端连续。
        m = 360
        boundary = []
        for i in range(m + 1):
            lon_p = -180.0 + 360.0 * i / m
            dlon = math.radians(lon_p - lon)
            A = sin_lat
            B = cos_lat * math.cos(dlon)
            C = cos_ang
            R2 = A * A + B * B
            if R2 < 1e-12:
                lat_b = 90.0 if north else -90.0
            else:
                R = math.sqrt(R2)
                ratio = max(-1.0, min(1.0, C / R))
                phi = math.atan2(B, A)
                a1 = math.degrees(math.asin(ratio) - phi)
                a2 = math.degrees(math.pi - math.asin(ratio) - phi)
                def _n90(v):
                    while v > 90.0: v -= 180.0
                    while v < -90.0: v += 180.0
                    return v
                c1, c2 = _n90(a1), _n90(a2)
                if north:
                    cands = [v for v in (c1, c2) if v >= 0.0]
                    lat_b = max(cands) if cands else max(c1, c2)
                else:
                    cands = [v for v in (c1, c2) if v <= 0.0]
                    lat_b = min(cands) if cands else min(c1, c2)
            boundary.append((lon_p, lat_b))
        proj = [((lo + 180.0) / 360.0 * W, (90.0 - la) / 180.0 * H)
                for (lo, la) in boundary]
        path = QPainterPath()
        if north:
            path.moveTo(0.0, 0.0)
            path.lineTo(W, 0.0)
            for (x, y) in reversed(proj):
                path.lineTo(x, y)
        else:
            for (x, y) in proj:
                path.lineTo(x, y)
            path.lineTo(W, H)
            path.lineTo(0.0, H)
        path.closeSubpath()
        return [path]
    # 不含极点：方位角采样球面小圆边界，**不**把经度归一化到 [-180,180]，保持投影连续。
    # 覆盖区跨越 ±180° 时，边界曲线在投影中可能超出画布右/左边缘，而等距圆柱投影中
    # ±180° 是同一经线，故绘制「自身 + 平移 ±W 的两个副本」，让跨 ±180° 的部分从
    # 另一侧补现。旧实现用 _split_dateline 把闭合小圆边界当开放曲线切开，跨 ±180°
    # 的覆盖区被错误合并成横贯画布的长弧，closeSubpath 用直线连左右两侧，导致「部分
    # 位于左右两边」的覆盖区残缺——现用不归一化 + 平移副本彻底解决。
    raw = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        s = sin_lat * cos_ang + cos_lat * sin_ang * math.cos(th)
        s = max(-1.0, min(1.0, s))
        plat = math.asin(s)
        dlon = math.atan2(math.sin(th) * sin_ang * cos_lat,
                          cos_ang - sin_lat * math.sin(plat))
        raw.append((lon + math.degrees(dlon), math.degrees(plat)))
    path = QPainterPath()
    first = True
    for (lo, la) in raw:
        x = (lo + 180.0) / 360.0 * W
        y = (90.0 - la) / 180.0 * H
        if first:
            path.moveTo(x, y)
            first = False
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return [path, path.translated(-W, 0.0), path.translated(W, 0.0)]


class TrackWorker(QThread):
    """后台批量计算多颗卫星的地面轨迹（矢量化，避免阻塞界面）。

    发出 done(dict)：{卫星名: [(lat, lon, alt_km, elev_deg 或 None), ...]}
    """

    done = Signal(object)

    def __init__(self, items, start_utc, hours, observer, observer_b=None,
                 samples=None):
        super().__init__()
        self._items = list(items)
        self._start = start_utc
        self._hours = float(hours)
        self._observer = observer
        self._observer_b = observer_b
        self._samples = int(samples) if samples else _track_samples(hours)

    def run(self):
        out = {}
        for name, sat in self._items:
            if self.isInterruptionRequested():
                return
            try:
                out[name] = sp.ground_track(
                    sat, self._start, self._hours, self._samples,
                    self._observer, self._observer_b)
            except Exception:
                out[name] = []
        if not self.isInterruptionRequested():
            self.done.emit(out)


class MapCanvas(QWidget):
    """地图画布：静态底图（海洋+陆地+网格）只在尺寸变化时重绘并缓存为 QPixmap；
    动态层（各卫星地面轨迹、当前位置、覆盖区、台站、图例）每次 paintEvent 叠加。

    entries: [ {'name', 'color', 'track', 'current', 'footprint', 'focus'} , ... ]
        track    : [(lon, lat, alt_km, elev_deg 或 None), ...]（注意是 lon 在前）
        current  : (lon, lat, alt_km, elev_deg 或 None) 或 None
        footprint: (lon, lat, ang_radius_deg) 或 None
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base = None
        self._bg = QColor(207, 232, 245)    # 海洋
        self._land = QColor(232, 236, 214)  # 陆地
        self._grid = QColor(150, 165, 180)  # 经纬网格
        self._coast = QColor(110, 125, 140)  # 海岸线

        self.entries = []
        self.stations = []     # [(lat, lon, label, (r,g,b)), ...]
        self.markers = load_map_markers()
        self.twilight_points = compute_twilight_points(datetime.datetime.now(datetime.timezone.utc))
        self.home_known = False
        self.b_known = False
        self.min_elev = 0.0
        self.min_elev_b = 0.0
        self.show_track = True
        self.show_footprint = True
        self.show_labels = True
        self.show_twilight = bool(_load_settings().get(MAP_TWILIGHT_KEY, DEFAULT_TWILIGHT_VISIBLE))
        self._hot = []          # 可点击命中目标：[(name, x, y, radius), ...]
        self.on_pick = None     # 点击命中卫星时的回调 (name) -> None
        self.setMinimumSize(380, 220)
        self.setMouseTracking(True)

    # ---- 坐标换算 ----
    def _map_rect(self):
        """地图铺满整个画布（窗口）。

        等距圆柱投影下世界本应为 2:1（经度 360° : 纬度 180°）；地图窗口默认尺寸
        1192×600 ≈ 2:1，因此铺满后地图比例正常、几乎不变形。所有经纬度→像素的
        投影都基于整块画布，不再保留 letterbox 留边。
        """
        W, H = self.width(), self.height()
        return 0.0, 0.0, float(W), float(H)

    def _xy(self, lon, lat):
        x0, y0, mapW, mapH = self._map_rect()
        return (x0 + (lon + 180) / 360.0 * mapW,
                y0 + (90 - lat) / 180.0 * mapH)

    # ---- 静态底图 ----
    def _render_base(self):
        x0, y0, mapW, mapH = self._map_rect()
        pw = max(1, int(round(mapW)))
        ph = max(1, int(round(mapH)))
        pix = QPixmap(pw, ph)
        pix.fill(self._bg)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = pw, ph

        # 经纬网格（每 30°）
        p.setPen(QPen(self._grid, 1))
        for lon in range(-180, 181, 30):
            x = (lon + 180) / 360.0 * W
            p.drawLine(x, 0, x, H)
        for lat in range(-90, 91, 30):
            y = (90 - lat) / 180.0 * H
            p.drawLine(0, y, W, y)
        # 赤道 / 本初子午线加粗
        p.setPen(QPen(QColor(120, 140, 160), 1.3))
        p.drawLine(0, H / 2, W, H / 2)
        p.drawLine(W / 2, 0, W / 2, H)

        # 陆地（含湖泊孔洞，使用奇偶填充规则）
        path = QPainterPath()
        for poly in _load_land():
            for ring in poly:
                if len(ring) < 3:
                    continue
                path.addPath(_ring_path(ring, W, H))
        path.setFillRule(Qt.OddEvenFill)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self._land))
        p.drawPath(path)
        p.setPen(QPen(self._coast, 0.8))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()
        self._base = pix

    # ---- 动态层 ----
    def _poly_path(self, seg):
        """把一段经度连续的 [(lon, lat), ...] 折线转成 QPainterPath。"""
        path = QPainterPath()
        for i, (lon, lat) in enumerate(seg):
            x, y = self._xy(lon, lat)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        return path

    def _visible_runs(self, track, elev_idx, min_elev):
        """把轨迹切成若干「连续可见」（指定仰角列 ≥ 最低仰角）的子段。

        elev_idx：轨迹点元组里仰角所在下标（3=本台，4=对方台）。
        """
        runs = []
        cur = []
        for s in track:
            elev = s[elev_idx]
            if elev is not None and elev >= min_elev:
                cur.append(s)
            else:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = []
        if len(cur) >= 2:
            runs.append(cur)
        return runs

    def _draw_track(self, p, entry):
        """画一颗卫星的地面轨迹：整条半透明细线 + 可见区段用卫星色加粗。

        轨迹跨越 ±180° 时在边界断开、从另一侧续画（见 _split_dateline），
        因此多圈轨迹能各自完整显示，且相邻圈会呈现自然的西向漂移。

        - 整条轨迹：半透明细线；
        - 本台站可见区段（仰角 ≥ 最低仰角 A）：实线加粗，卫星颜色；
        - 对方台站可见区段（仰角 ≥ 最低仰角 B）：虚线加粗，卫星颜色，
          与「本台」区分（仅通联预测有对方台站时绘制）。
        """
        track = entry['track']
        if len(track) < 2:
            return
        col = entry['color']
        focus = entry['focus']
        base_w = 2.2 if focus else 1.4
        alpha = 150 if focus else 90

        # 整条轨迹（半透明细线）
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), alpha), base_w))
        for seg in _split_dateline(track):
            p.drawPath(self._poly_path(seg))

        # 本台站可见区段（仰角 ≥ 最低仰角 A）：实线加粗
        if self.home_known:
            p.setPen(QPen(col, base_w + 1.4))
            for run in self._visible_runs(track, 3, self.min_elev):
                for seg in _split_dateline(run):
                    p.drawPath(self._poly_path(seg))

        # 对方台站可见区段（仰角 ≥ 最低仰角 B）：虚线加粗，卫星颜色
        if self.b_known:
            pen = QPen(col, base_w + 1.4)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            for run in self._visible_runs(track, 4, self.min_elev_b):
                for seg in _split_dateline(run):
                    p.drawPath(self._poly_path(seg))

        # 轨迹终点（时长末尾）画一个空心小圈，标明轨迹方向的尽头
        xe, ye = self._xy(track[-1][0], track[-1][1])
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 200), 1.2))
        p.drawEllipse(QPointF(xe, ye), 3.0, 3.0)

    def _draw_footprint(self, p, entry):
        """画覆盖区（0° 仰角 footprint）。

        用球面小圆边界投影成多边形绘制，正确处理极地经度拉伸、跨越极点
        （北极/南极用极点帽封口）与跨越 ±180° 换日线——而不是旧实现里
        统一角半径的椭圆（在极地会把本应绕极点的宽覆盖区画成一条窄带）。
        """
        lon, lat, ang = entry['footprint']
        if ang <= 0:
            return
        col = entry['color']
        focus = entry['focus']
        x0, y0, mapW, mapH = self._map_rect()
        paths = _footprint_paths(lon, lat, ang, mapW, mapH)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(),
                             200 if focus else 110), 1.2))
        p.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(),
                                 42 if focus else 20)))
        for path in paths:
            pp = QPainterPath(path)
            pp.translate(x0, y0)        # 把覆盖区从地图矩形局部坐标平移到画布位置
            p.drawPath(pp)

    def _draw_current(self, p, entry):
        lon, lat, alt, elev_a, elev_b = entry['current']
        col = entry['color']
        focus = entry['focus']
        x, y = self._xy(lon, lat)
        r = 6.0 if focus else 4.5
        p.setBrush(QBrush(col))
        p.setPen(QPen(Qt.white, 1.6 if focus else 1.2))
        p.drawEllipse(QPointF(x, y), r, r)
        if focus:
            # 聚焦卫星加一圈描边，便于在多星中一眼找到
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(col, 1.4))
            p.drawEllipse(QPointF(x, y), r + 3.5, r + 3.5)
        if self.show_labels:
            p.setPen(QPen(QColor(20, 20, 20), 1))
            f = p.font()
            f.setBold(bool(focus))
            p.setFont(f)
            p.drawText(QPointF(x + r + 4, y - 5), entry['name'].strip())
            f.setBold(False)
            p.setFont(f)

    def _draw_twilight(self, p):
        if not self.twilight_points:
            return
        pen = QPen(QColor(130, 123, 110, 200), 1.4)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for seg in _split_dateline(self.twilight_points):
            p.drawPath(self._poly_path(seg))

    def _draw_night_shade(self, p):
        if not self.twilight_points:
            return
        pts = self.twilight_points
        # 夜区所在半球：赤纬 ≥ 0 时太阳偏向北半球，夜区在南；否则在北。
        decl, _ = _solar_declination_and_subsolar_lon(
            datetime.datetime.now(datetime.timezone.utc))
        night_is_south = decl >= 0.0

        # 平滑夜区多边形：沿晨昏线（1° 间隔，连续单值）闭合到极边，
        # 用抗锯齿填充，边缘自然平滑（替代原先 6° 网格的锯齿）。
        poly = [(lon, lat) for lon, lat in pts]
        if night_is_south:
            poly.append((180.0, -90.0))
            poly.append((-180.0, -90.0))
        else:
            poly.append((180.0, 90.0))
            poly.append((-180.0, 90.0))
        night_path = QPainterPath()
        for i, (lon, lat) in enumerate(poly):
            x, y = self._xy(lon, lat)
            if i == 0:
                night_path.moveTo(x, y)
            else:
                night_path.lineTo(x, y)
        night_path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(27, 32, 48, 88)))
        p.drawPath(night_path)

        # 羽化晨昏线边缘：沿界线多遍半透明描边，向昼侧做出柔和过渡，
        # 避免夜区与昼区之间出现生硬分界。
        term_path = QPainterPath()
        for i, (lon, lat) in enumerate(pts):
            x, y = self._xy(lon, lat)
            if i == 0:
                term_path.moveTo(x, y)
            else:
                term_path.lineTo(x, y)
        for width, alpha in ((7.0, 20), (4.5, 28), (2.0, 38)):
            pen = QPen(QColor(27, 32, 48, alpha))
            pen.setWidthF(width)
            pen.setStyle(Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(term_path)

    def _draw_markers(self, p):
        for idx, m in enumerate(self.markers):
            try:
                lat = float(m.get('lat', 0.0) or 0.0)
                lon = float(m.get('lon', 0.0) or 0.0)
                color = QColor(str(m.get('color') or _marker_color(idx).name()))
            except Exception:
                continue
            x, y = self._xy(lon, lat)
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(x, y), 5.5, 5.5)
            p.setPen(QPen(QColor(30, 30, 30), 1))
            p.drawText(QPointF(x + 10, y - 6), str(m.get('name', f'标记点 {idx + 1}')))

    def _draw_station(self, p, st):
        lat, lon, label, rgb = st
        x, y = self._xy(lon, lat)
        color = QColor(*rgb)
        p.setPen(QPen(Qt.black, 1))
        p.setBrush(QBrush(color))
        p.drawRect(QRectF(x - 6, y - 6, 12, 12))
        p.setPen(QPen(Qt.black, 1))
        p.drawText(QPointF(x + 9, y + 4), label)

    def _draw_legend(self, p):
        """左下角图例：色块 + 卫星名（最多 14 行，超出显示省略计数）。"""
        if not self.entries:
            return
        rows = self.entries[:14]
        extra = len(self.entries) - len(rows)
        line_h = 15
        box_h = line_h * (len(rows) + (1 if extra > 0 else 0)) + 10
        box_w = 148
        rx, ry, mapW, mapH = self._map_rect()
        x0 = rx + 8
        y0 = ry + mapH - box_h - 8
        if y0 < 4:
            return
        p.setPen(QPen(QColor(120, 130, 140), 1))
        p.setBrush(QBrush(QColor(255, 255, 255, 205)))
        p.drawRect(QRectF(x0, y0, box_w, box_h))
        f = QFont(p.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        y = y0 + 6
        for e in rows:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(e['color']))
            p.drawRect(QRectF(x0 + 6, y + 3, 10, 7))
            p.setPen(QPen(QColor(30, 30, 30), 1))
            name = e['name'].strip()
            if len(name) > 16:
                name = name[:15] + '…'
            p.drawText(QPointF(x0 + 21, y + 10),
                       ('● ' if e['focus'] else '') + name)
            y += line_h
        if extra > 0:
            p.setPen(QPen(QColor(110, 110, 110), 1))
            p.drawText(QPointF(x0 + 21, y + 10), '… 其余 %d 颗' % extra)

    def paintEvent(self, event):
        self._hot = []
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        rx, ry, mapW, mapH = self._map_rect()
        # 底图按整块画布尺寸缓存；画布先整体填海洋色（地图铺满窗口，无留边）
        if (self._base is None or self._base.width() != int(round(mapW))
                or self._base.height() != int(round(mapH))):
            self._render_base()
        p.fillRect(0, 0, W, H, self._bg)
        if self._base is not None:
            p.drawPixmap(int(round(rx)), int(round(ry)), self._base)

        if self.show_track:
            for e in self.entries:
                if not e['focus'] and e['track']:
                    self._draw_track(p, e)
            for e in self.entries:          # 聚焦卫星画在最上层
                if e['focus'] and e['track']:
                    self._draw_track(p, e)
        if self.show_twilight:
            self._draw_night_shade(p)
            self._draw_twilight(p)
        if self.show_footprint:
            for e in self.entries:
                if e['footprint']:
                    fx, fy = self._xy(e['footprint'][0], e['footprint'][1])
                    self._hot.append((e['name'], fx, fy,
                                      max(10.0, e['footprint'][2] / 180.0 * mapH)))
                    self._draw_footprint(p, e)
        self._draw_markers(p)
        for st in self.stations:
            self._draw_station(p, st)
        for e in self.entries:
            if not e['focus'] and e['current']:
                self._draw_current(p, e)
        for e in self.entries:
            if e['focus'] and e['current']:
                self._draw_current(p, e)
        self._draw_legend(p)
        p.end()

    # ---- 点击聚焦 ----
    def _pick_hit(self, x, y):
        """返回点击位置命中的卫星名（优先当前位置圆点，其次轨迹点，再覆盖区中心）。
        无命中返回 None。多目标时取几何距离最近且在各自阈值内的那颗。"""
        best = None
        best_d = None
        for e in self.entries:
            if e['current']:
                cx, cy = self._xy(e['current'][0], e['current'][1])
                d = (x - cx) ** 2 + (y - cy) ** 2
                if d <= 100 and (best_d is None or d < best_d):   # 当前位置圆点 ~10px
                    best_d = d
                    best = e['name']
            for s in e['track']:
                tx, ty = self._xy(s[0], s[1])
                d = (x - tx) ** 2 + (y - ty) ** 2
                if d <= 36 and (best_d is None or d < best_d):    # 轨迹点 ~6px
                    best_d = d
                    best = e['name']
        for name, hx, hy, rad in self._hot:
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= rad * rad and (best_d is None or d < best_d):
                best_d = d
                best = name
        return best

    def mousePressEvent(self, event):
        if self.on_pick is None:
            return
        name = self._pick_hit(event.position().x(), event.position().y())
        if name:
            self.on_pick(name)

    def mouseMoveEvent(self, event):
        if self.on_pick is None:
            return
        if self._pick_hit(event.position().x(), event.position().y()) is not None:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)


class MaidenheadImportDialog(QDialog):
    """从梅登黑格网格坐标批量导入标记点。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('从梅登黑格坐标导入')
        self.resize(440, 340)
        self.result_rows = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            '每行一个梅登黑格坐标（4 / 6 / 8 位均可，大小写不限），如：\n'
            '  PM84\n  EM12ab\n'
            '也可写「名称 坐标」（空格分隔），如：\n'
            '  北京 PM84'))

        self._edit = QPlainTextEdit()
        font = self._edit.font()
        font.setFamily('Consolas' if sys.platform == 'win32' else 'monospace')
        self._edit.setFont(font)
        layout.addWidget(self._edit, 1)

        btn_row = QHBoxLayout()
        import_btn = QPushButton('导入')
        cancel_btn = QPushButton('取消')
        import_btn.clicked.connect(self._do_import)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(import_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _do_import(self):
        rows = []
        errors = []
        for raw in self._edit.toPlainText().strip().splitlines():
            line = raw.strip()
            if not line:
                continue
            name, grid = self._split_line(line)
            try:
                lat, lon = sp.maidenhead_to_latlon(grid)
            except ValueError as e:
                errors.append(f'{grid}: {e}')
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                errors.append(f'{grid}: 坐标超出地球范围（经纬度无效）')
                continue
            rows.append((name or grid, lat, lon, ''))
        if errors:
            QMessageBox.warning(self, '部分坐标无效',
                                '以下行无法解析，已跳过：\n' + '\n'.join(errors))
        if not rows:
            return
        self.result_rows = rows
        self.accept()

    @staticmethod
    def _split_line(line):
        """解析一行：支持 名称=网格 或 名称 网格（网格取末段），以及纯网格。"""
        if '=' in line:
            a, b = line.split('=', 1)
            return a.strip(), b.strip()
        parts = line.split()
        if len(parts) >= 2:
            return ' '.join(parts[:-1]), parts[-1]
        return '', parts[0] if parts else ''


class MarkerManageDialog(QDialog):
    """管理地图标记点（名称 / 纬度 / 经度 / 颜色）。

    配置文件统一使用记事本编辑。
    """

    def __init__(self, parent, markers=None):
        super().__init__(parent)
        self.setWindowTitle('标记点管理')
        self.resize(640, 480)
        self._rows = []
        self._syncing_coordinates = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            '每行一条记录。点击单元格可直接编辑；用“添加”新增，“删除选中”移除整行；'
            '完成后点“保存”写回文件。'))

        # 表格（与 TQSL 映射 / 转发器设置一致：纵向填满窗口）
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['名称', '网格', '纬度', '经度', '颜色'])
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.cellChanged.connect(self._sync_coordinates)
        layout.addWidget(self.table, 1)

        # 按钮行（与 TQSL / 转发器一致的表格 + 按钮布局）
        btn_row = QHBoxLayout()
        add_btn = QPushButton('添加')
        del_btn = QPushButton('删除选中')
        edit_btn = QPushButton('使用记事本编辑')
        save_btn = QPushButton('保存')
        close_btn = QPushButton('关闭')
        add_btn.clicked.connect(self._add_row)
        del_btn.clicked.connect(self._del_row)
        edit_btn.clicked.connect(self._open_text)
        save_btn.clicked.connect(self._save_and_close)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load(markers or load_map_markers())

    def _open_text(self):
        open_map_markers_text()
        self.reject()

    def _sync_coordinates(self, row, column):
        """标记点编辑完成后自动在网格与十进制坐标之间同步。"""
        if self._syncing_coordinates or row < 0:
            return
        try:
            self._syncing_coordinates = True
            if column == 1:
                grid_item = self.table.item(row, 1)
                lat, lon = sp.maidenhead_to_latlon(grid_item.text().strip())
                self.table.setItem(row, 1, QTableWidgetItem(
                    sp.latlon_to_maidenhead(lat, lon)))
                self.table.setItem(row, 2, QTableWidgetItem(f'{lat:.5f}'))
                self.table.setItem(row, 3, QTableWidgetItem(f'{lon:.5f}'))
            elif column in (2, 3):
                lat_item = self.table.item(row, 2)
                lon_item = self.table.item(row, 3)
                lat = float(lat_item.text())
                lon = float(lon_item.text())
                self.table.setItem(row, 1, QTableWidgetItem(
                    sp.latlon_to_maidenhead(lat, lon)))
        except (AttributeError, TypeError, ValueError):
            pass
        finally:
            self._syncing_coordinates = False

    def _import_from_maidenhead(self):
        """批量读取网格并追加为标记点。"""
        dlg = MaidenheadImportDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rows.extend(
                (name, grid, lat, lon, color)
                for name, lat, lon, color in dlg.result_rows
                for grid in [sp.latlon_to_maidenhead(lat, lon)])
            self._render()

    def _grid_to_coord(self):
        """按观测站设置的交互方式，把选中行网格转换为经纬度。"""
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows:
            return
        for row in rows:
            grid_item = self.table.item(row, 1)
            grid = grid_item.text().strip() if grid_item else ''
            if not grid:
                continue
            try:
                lat, lon = sp.maidenhead_to_latlon(grid)
            except ValueError as e:
                QMessageBox.warning(self, '网格无效', str(e))
                continue
            self.table.setItem(row, 1, QTableWidgetItem(
                sp.latlon_to_maidenhead(lat, lon)))
            self.table.setItem(row, 2, QTableWidgetItem(f'{lat:.5f}'))
            self.table.setItem(row, 3, QTableWidgetItem(f'{lon:.5f}'))

    # ---- 原有表格操作 ----

    def _load(self, markers):
        self._rows = []
        for idx, m in enumerate(markers):
            mm = _normalize_marker(m, idx)
            try:
                grid = sp.latlon_to_maidenhead(mm['lat'], mm['lon'])
            except Exception:
                grid = ''
            self._rows.append((mm['name'], grid, mm['lat'], mm['lon'], mm['color']))
        self._render()

    def _render(self):
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            name, grid, lat, lon, color = row
            self.table.setItem(i, 0, QTableWidgetItem(str(name)))
            self.table.setItem(i, 1, QTableWidgetItem(str(grid)))
            self.table.setItem(i, 2, QTableWidgetItem(f'{lat}'))
            self.table.setItem(i, 3, QTableWidgetItem(f'{lon}'))
            self.table.setItem(i, 4, QTableWidgetItem(str(color)))

    def _add_row(self):
        self._rows.append((f'标记点 {len(self._rows) + 1}', '', 0.0, 0.0, ''))
        self._render()

    def _del_row(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._render()

    def _save_and_close(self):
        self._rows = []
        for row in range(self.table.rowCount()):
            values = []
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                values.append(item.text().strip() if item else '')
            self._rows.append(tuple(values))
        items = []
        for row in self._rows:
            name, grid, lat, lon, color = row
            try:
                lat_v = float(lat)
                lon_v = float(lon)
            except (TypeError, ValueError):
                continue
            color_v = str(color or '').strip() or _marker_color(len(items)).name()
            items.append({'name': str(name).strip() or f'标记点 {len(items) + 1}',
                          'lat': lat_v, 'lon': lon_v, 'color': color_v})
        save_map_markers(items)
        self.accept()


class MapWindow(QMainWindow):

    ALL_ITEM = '全部已选卫星'

    def __init__(self, parent, sats, home=None, station_b=None, selected_name=None,
                 source=None, min_elev=0.0, min_elev_b=None,
                 on_min_elev_change=None):
        super().__init__(parent)
        self.setWindowTitle('卫星地图')
        self.resize(1192, 600)
        self._sats = dict(sats)                 # name -> Satrec（来源窗口的「已选卫星」）
        self._sats_order = [n for (n, _) in sats]
        self._home = home                       # (lat, lon, alt) 或 None
        self._station_b = station_b             # (lat, lon, alt) 或 None
        self._focus = selected_name             # 聚焦卫星（来源表格选中行）
        self._source = source
        self._min_elev = float(min_elev or 0.0)
        # 对方台站最低仰角；未显式给出时回退到本台阈值（无对方台时本就不绘制对方段）
        self._min_elev_b = float(min_elev_b) if min_elev_b is not None else self._min_elev
        self._on_min_elev_change = on_min_elev_change
        # 轨迹时长：恢复上次使用的值（与「预测时长」分开保存，见 TRACK_HOURS_KEY）
        self._track_hours = float(load_track_hours())
        self._tracks = {}                       # name -> [(lat, lon, alt, elev), ...]
        self._track_key = None                  # 上次算轨迹时的 (卫星集合, 时长, 台站)
        self._last_track_time = None
        self._track_dirty = True
        self._worker = None
        self._closing = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ---------- 控制条 ----------
        ctl = QHBoxLayout()
        ctl.addWidget(QLabel('显示:'))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(190)
        self._combo.setToolTip(
            '「全部已选卫星」= 来源窗口（卫星过境 / 通联预测）当前选中范围内的所有卫星；\n'
            '也可只看其中某一颗（选中即成为聚焦卫星，整条加粗并显示覆盖区）。\n'
            '来源窗口修改自选卫星后，这里会实时同步；直接在地图上点击卫星也可聚焦。')
        ctl.addWidget(self._combo)

        ctl.addWidget(QLabel('轨迹时长(小时):'))
        self._hours = QSpinBox()
        self._hours.setRange(MIN_TRACK_HOURS, MAX_TRACK_HOURS)
        self._hours.setValue(int(self._track_hours))
        self._hours.setToolTip(
            '地面轨迹的时间跨度：从「当前时刻」起，向后延伸这么多小时（最长 %d 小时）。\n'
            '与「预测时长」相互独立；此处的设置会被记住，下次打开地图时自动恢复，\n'
            '并与另一个来源窗口（卫星过境 / 通联预测）打开的地图保持一致。'
            % MAX_TRACK_HOURS)
        self._hours.valueChanged.connect(self._on_hours)
        ctl.addWidget(self._hours)

        ctl.addWidget(QLabel('最多显示的卫星:'))
        self._max_spin = QSpinBox()
        self._max_spin.setRange(1, MAX_SHOW_LIMIT)
        self._max_spin.setValue(DEFAULT_MAX_SHOW)
        self._max_spin.setToolTip(
            '同时在地图上显示的卫星数量上限（按名称顺序取前 N 颗）。\n'
            '已选卫星过多时地图会很拥挤，可调小；需要全看时调大。')
        self._max_spin.valueChanged.connect(self._on_max_changed)
        ctl.addWidget(self._max_spin)

        # 最低仰角（本台 / 对方）——地图内直接调整，实时改变可见区段高亮，
        # 并同步回来源窗口（卫星过境 / 通联预测）与另一个已打开的地图窗口。
        ctl.addWidget(QLabel('最低仰角(本台):'))
        self._el_a_spin = QSpinBox()
        self._el_a_spin.setRange(0, 90)
        self._el_a_spin.setSuffix(' °')
        self._el_a_spin.setValue(int(round(self._min_elev)))
        self._el_a_spin.setToolTip(
            '本站（台站 A）最低可用仰角：低于该仰角的弧段不计入「可见区段」'
            '（地图上实线加粗的部分）。与来源窗口共享同一设置。')
        self._el_a_spin.valueChanged.connect(self._on_el_a)
        ctl.addWidget(self._el_a_spin)

        self._el_b_label = QLabel('对方最低仰角:')
        ctl.addWidget(self._el_b_label)
        self._el_b_spin = QSpinBox()
        self._el_b_spin.setRange(0, 90)
        self._el_b_spin.setSuffix(' °')
        self._el_b_spin.setValue(int(round(self._min_elev_b)))
        self._el_b_spin.setToolTip(
            '对方台站 B 最低可用仰角：低于该仰角的弧段不计入「对方可见区段」'
            '（地图上虚线加粗的部分）。仅在通联预测（存在对方台站）时可用。')
        self._el_b_spin.valueChanged.connect(self._on_el_b)
        ctl.addWidget(self._el_b_spin)
        self._el_b_label.setVisible(self._station_b_valid())
        self._el_b_spin.setVisible(self._station_b_valid())

        self._chk_track = QCheckBox('地面轨迹')
        self._chk_track.setChecked(True)
        self._chk_track.toggled.connect(self._on_chk_track)
        ctl.addWidget(self._chk_track)

        self._chk_foot = QCheckBox('覆盖区')
        self._chk_foot.setChecked(True)
        self._chk_foot.setToolTip(
            '显示卫星 0° 仰角覆盖范围。多星同显时只画聚焦卫星（及 5 颗以内时的全部卫星），避免遮挡。')
        self._chk_foot.toggled.connect(self._on_chk_foot)
        ctl.addWidget(self._chk_foot)

        self._chk_label = QCheckBox('名称')
        self._chk_label.setChecked(True)
        self._chk_label.toggled.connect(self._on_chk_label)
        ctl.addWidget(self._chk_label)

        self._chk_twilight = QCheckBox('晨昏线')
        self._chk_twilight.setChecked(bool(_load_settings().get(MAP_TWILIGHT_KEY, DEFAULT_TWILIGHT_VISIBLE)))
        self._chk_twilight.toggled.connect(self._on_chk_twilight)
        ctl.addWidget(self._chk_twilight)

        self._marker_mgr_btn = QPushButton('标记点管理')
        self._marker_mgr_btn.setToolTip(
            '使用记事本编辑地图标记点（名称/网格/纬度/经度/颜色）file/sat_map_markers.txt')
        self._marker_mgr_btn.clicked.connect(self._open_marker_manager)
        ctl.addWidget(self._marker_mgr_btn)

        ctl.addStretch(1)
        layout.addLayout(ctl)

        # 统一窗口最小宽度：以「含对方最低仰角」的完整控制条为准测量一次。
        # 卫星过境（无对方台站）会隐藏该组控件，若不约束最小宽度，其地图窗口会比
        # 通联预测（含该组）窄约 180px，导致两处打开的地图宽度不一致。设统一最小宽度后，
        # 两种来源打开的地图窗口宽度保持一致（卫星过境那组虽隐藏，但窗口不会因此变窄）。
        self._el_b_label.setVisible(True)
        self._el_b_spin.setVisible(True)
        _uniform_min_w = self.centralWidget().minimumSizeHint().width()
        self.setMinimumWidth(_uniform_min_w)
        self._el_b_label.setVisible(self._station_b_valid())
        self._el_b_spin.setVisible(self._station_b_valid())

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # ---------- 信息条 ----------
        self._info = QLabel('准备中…')
        self._info.setStyleSheet('color: gray;')
        # 关键：允许自动换行。否则 QLabel 默认不换行，其 minimumSizeHint 宽度
        # 等于整段状态文字「单行」所需宽度，会把窗口最小宽度顶到上千像素，
        # 导致 resize(960,600) 被最小约束覆盖、窗口被异常撑宽。
        self._info.setWordWrap(True)
        self._info.setMinimumWidth(0)
        layout.addWidget(self._info)

        # ---------- 画布 ----------
        self.canvas = MapCanvas()
        self.canvas.min_elev = self._min_elev
        self.canvas.min_elev_b = self._min_elev_b
        self.canvas.on_pick = self.set_satellite   # 地图内点击卫星即聚焦
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.canvas, 1)

        self._rebuild_combo()
        self._combo.currentIndexChanged.connect(self._on_combo)

        # ---------- 实时刷新 ----------
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def showEvent(self, event):
        """首次显示时把窗口高度锁定为画布 2:1 所需值。

        等距圆柱投影的世界地图本应为宽:高 = 2:1；地图窗口默认宽度固定（1192），
        但控制条+信息条会挤掉一部分高度，使画布变成 1174×512（约 2.29:1）。
        若让地图直接铺满该画布会被横向拉伸约 15%。因此在首次显示时按「画布宽度/2」
        反推所需窗口高度并锁定最小高度，使地图铺满窗口的同时保持正确比例。
        """
        super().showEvent(event)
        if getattr(self, '_aspect_fixed', False):
            return
        self._aspect_fixed = True
        cw = self.canvas.width()
        if cw <= 0:
            return
        ch = int(round(cw / 2.0))
        cur = self.canvas.height()
        if ch != cur:
            self.resize(self.width(), self.height() + (ch - cur))
        self.setMinimumHeight(self.height())   # 锁定最小高度，避免被缩小到低于 2:1 而变形

    # ---- 对外同步接口（由卫星过境 / 通联预测窗口调用） ----
    def set_sats(self, sats):
        """更新「已选卫星」列表（来源窗口刷新 TLE / 修改自选卫星时调用）。"""
        self._sats = dict(sats)
        self._sats_order = [n for (n, _) in sats]
        if self._focus not in self._sats:
            self._focus = None
        # 丢弃已不在列表中的卫星轨迹，避免同名卫星再次出现时短暂显示旧轨迹
        self._tracks = {n: t for n, t in self._tracks.items() if n in self._sats}
        self._rebuild_combo()
        self._track_dirty = True
        self._tick()

    def set_satellite(self, name):
        """设置聚焦卫星（来源窗口表格选中行变化时调用）。

        若当前正在「只看某一颗」，则同步切换为该颗；否则仅高亮，不改变显示范围。
        """
        if not name:
            return
        name = name.strip()  # TLE 名称行定宽填充可能带尾随空格，统一去除再匹配
        if name not in self._sats:
            return
        self._focus = name
        # 注意：下拉框第 0 项文本带「(N)」计数后缀，判断是否「全部」只能看索引
        if self._combo.currentIndex() > 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentText(name)
            self._combo.blockSignals(False)
            self._track_dirty = True
        self._tick()

    def set_stations(self, home=None, station_b=None):
        if home is not None:
            self._home = home
        if station_b is not None:
            self._station_b = station_b
        self._el_b_label.setVisible(self._station_b_valid())
        self._el_b_spin.setVisible(self._station_b_valid())
        self._track_dirty = True    # 可见区段依赖本台站位置
        self._tick()

    def set_min_elev(self, deg):
        if deg is None:
            return
        self._min_elev = float(deg)
        self.canvas.min_elev = self._min_elev
        self._el_a_spin.blockSignals(True)
        self._el_a_spin.setValue(int(round(self._min_elev)))
        self._el_a_spin.blockSignals(False)
        self.canvas.update()

    def set_min_elev_b(self, deg):
        """设置对方台站 B 的最低仰角（仅通联预测有对方台时使用）。"""
        if deg is None:
            return
        if not self._station_b_valid():
            return
        self._min_elev_b = float(deg)
        self.canvas.min_elev_b = self._min_elev_b
        self._el_b_spin.blockSignals(True)
        self._el_b_spin.setValue(int(round(self._min_elev_b)))
        self._el_b_spin.blockSignals(False)
        self.canvas.update()

    def _on_el_a(self, v):
        a = float(v)
        if a == self._min_elev:
            return
        self._min_elev = a
        self.canvas.min_elev = a
        self.canvas.update()
        _broadcast_min_elev(self, a, self._min_elev_b)
        if self._on_min_elev_change:
            self._on_min_elev_change(a, self._min_elev_b)

    def _on_el_b(self, v):
        b = float(v)
        if b == self._min_elev_b:
            return
        self._min_elev_b = b
        self.canvas.min_elev_b = b
        self.canvas.update()
        _broadcast_min_elev(self, self._min_elev, b)
        if self._on_min_elev_change:
            self._on_min_elev_change(self._min_elev, b)

    def set_track_hours(self, hours, persist=False):
        """设置轨迹时长（供其他地图窗口 / 来源窗口同步调用）。

        persist=False 时只更新界面与轨迹，不再重复落盘，避免广播时反复写文件。
        """
        h = float(clamp_track_hours(hours))
        if h == self._track_hours:
            return
        self._track_hours = h
        self._hours.blockSignals(True)
        self._hours.setValue(int(h))
        self._hours.blockSignals(False)
        self._track_dirty = True
        if persist:
            save_track_hours(h)
        self._tick()

    def track_hours(self):
        return self._track_hours

    # ---- 内部 ----
    def _rebuild_combo(self):
        cur = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem('%s (%d)' % (self.ALL_ITEM, len(self._sats_order)))
        self._combo.setItemData(0, self.ALL_ITEM)
        for n in self._sats_order:
            self._combo.addItem(n)
        # 尽量保持原选择
        if cur and cur != '' and cur in self._sats_order:
            self._combo.setCurrentText(cur)
        else:
            self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def _combo_mode(self):
        """返回 (是否全部, 单颗卫星名或 None)。"""
        idx = self._combo.currentIndex()
        if idx <= 0:
            return True, None
        name = self._combo.currentText()
        return False, (name if name in self._sats else None)

    def _display_names(self):
        """当前应显示的卫星名列表（受「最多显示的卫星」限制）。"""
        all_mode, one = self._combo_mode()
        if not all_mode:
            return ([one] if one else []), 0
        names = list(self._sats_order)
        cap = self._max_spin.value()
        hidden = max(0, len(names) - cap)
        shown = names[:cap]
        # 聚焦卫星即使排在上限之外，也保证可见
        if self._focus and self._focus in self._sats and self._focus not in shown:
            if shown:
                shown[-1] = self._focus
            else:
                shown = [self._focus]
        return shown, hidden

    def _on_combo(self, _idx):
        # 下拉框选中某一颗卫星时，让它成为「聚焦卫星」（整条加粗 + 覆盖区 + 图例●）；
        # 选回「全部已选卫星」则保留 self._focus（来源窗口选中的那颗仍高亮），不清空。
        all_mode, one = self._combo_mode()
        if not all_mode and one:
            self._focus = one
        self._track_dirty = True
        self._tick()

    def _on_hours(self, v):
        h = float(clamp_track_hours(v))
        if h != float(v):                      # 越界输入，回写钳制后的值
            self._hours.blockSignals(True)
            self._hours.setValue(int(h))
            self._hours.blockSignals(False)
        if h == self._track_hours:
            return
        self._track_hours = h
        self._track_dirty = True
        save_track_hours(h)                    # 记住，下次打开地图时恢复
        _broadcast_track_hours(h, exclude=self)  # 同步给另一个来源窗口的地图
        self._tick()

    def _on_max_changed(self, _v):
        self._track_dirty = True
        self._tick()

    def _on_chk_track(self, checked):
        self.canvas.show_track = checked
        self.canvas.update()

    def _on_chk_foot(self, checked):
        self.canvas.show_footprint = checked
        self.canvas.update()

    def _on_chk_label(self, checked):
        self.canvas.show_labels = checked
        self.canvas.update()

    def _on_chk_twilight(self, checked):
        self.canvas.show_twilight = bool(checked)
        try:
            s = _load_settings()
            s[MAP_TWILIGHT_KEY] = bool(checked)
            _save_settings(s)
        except Exception:
            pass
        self.canvas.update()

    def _open_marker_manager(self):
        dlg = MarkerManageDialog(self, self.canvas.markers)
        if dlg.exec() == QDialog.Accepted:
            self.canvas.markers = load_map_markers()
            self.canvas.update()

    def _home_valid(self):
        return (self._home is not None
                and not (self._home[0] == 0.0 and self._home[1] == 0.0))

    def _station_b_valid(self):
        return (self._station_b is not None
                and not (self._station_b[0] == 0.0 and self._station_b[1] == 0.0))

    def _observer(self):
        return self._home if self._home_valid() else None

    # ---- 轨迹（后台线程批量计算） ----
    def _start_track_calc(self, now, names):
        if self._worker is not None and self._worker.isRunning():
            self._track_dirty = True     # 上一批还没算完，下个 tick 再试
            return
        items = [(n, self._sats[n]) for n in names if n in self._sats]
        if not items:
            self._tracks = {}
            self._track_dirty = False
            self._last_track_time = now
            return
        worker = TrackWorker(items, now, self._track_hours, self._observer(),
                              self._station_b if self._station_b_valid() else None)
        self._worker = worker

        def on_done(res):
            if self._closing:
                return
            self._tracks = res
            self._last_track_time = now
            if getattr(self, '_worker', None) is worker:
                self._worker = None
            self._refresh_entries(datetime.datetime.now(datetime.timezone.utc))
            self.canvas.update()

        worker.done.connect(on_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._track_dirty = False

    def _need_track_recalc(self, now, names):
        if self._track_dirty:
            return True
        key = (tuple(names), self._track_hours, self._observer(),
               (self._station_b if self._station_b_valid() else None))
        if key != self._track_key:
            return True
        if self._last_track_time is None:
            return True
        return (now - self._last_track_time).total_seconds() >= TRACK_REFRESH_SEC

    # ---- 每帧数据组装 ----
    def _refresh_entries(self, now):
        names, _hidden = self._display_names()
        obs = self._observer()
        entries = []
        for i, name in enumerate(names):
            sat = self._sats.get(name)
            if sat is None:
                continue
            focus = (name == self._focus)
            color = _color_for(i)
            # 轨迹（后台算好的，存为 (lat, lon, alt, elev_a, elev_b)；
            # 画布用 (lon, lat, alt, elev_a, elev_b)）
            raw = self._tracks.get(name) or []
            track = [(s[1], s[0], s[2], s[3], s[4]) for s in raw]
            # 当前位置（每帧实时算，保证「实时更新」）
            cur = None
            foot = None
            try:
                lat, lon, alt = sp.subpoint(sat, now)
                elev_a = None
                elev_b = None
                if obs is not None:
                    try:
                        elev_a = sp.observe(sat, now, obs)['elevation']
                    except Exception:
                        elev_a = None
                obs_b = self._station_b if self._station_b_valid() else None
                if obs_b is not None:
                    try:
                        elev_b = sp.observe(sat, now, obs_b)['elevation']
                    except Exception:
                        elev_b = None
                cur = (lon, lat, alt, elev_a, elev_b)
                # 每颗显示中的卫星都画覆盖区（聚焦卫星在 _draw_footprint 里
                # 用更高的不透明度强调）；不再按「≤5 颗才显示」隐藏，否则卫星
                # 较多且未选中任何一颗时整张图都没有覆盖区。
                if alt > 0:
                    foot = (lon, lat, _footprint_radius_deg(alt))
            except Exception:
                cur = None
            entries.append({
                'name': name, 'color': color, 'track': track,
                'current': cur, 'footprint': foot, 'focus': focus,
            })
        self.canvas.entries = entries
        self.canvas.home_known = obs is not None
        self.canvas.b_known = self._station_b_valid()

        stations = []
        if self._home_valid():
            stations.append((self._home[0], self._home[1], '本台', (200, 30, 30)))
        if (self._station_b is not None
                and not (self._station_b[0] == 0.0 and self._station_b[1] == 0.0)):
            stations.append((self._station_b[0], self._station_b[1], '对方台', (30, 90, 200)))
        self.canvas.stations = stations

    def _update_info(self, now, hidden):
        parts = ['UTC ' + now.strftime('%Y-%m-%d %H:%M:%S')]
        shown = len(self.canvas.entries)
        total = len(self._sats_order)
        end = now + datetime.timedelta(hours=self._track_hours)
        parts.append('轨迹 %s → %s (%.0f h)' % (
            now.strftime('%H:%M'), end.strftime('%H:%M'), self._track_hours))
        if hidden > 0:
            parts.append('显示 %d/%d 颗（还有 %d 颗未显示，可调大「最多显示的卫星」）'
                         % (shown, total, hidden))
        else:
            parts.append('显示 %d/%d 颗' % (shown, total))

        cur_entry = None
        for e in self.canvas.entries:
            if e['focus']:
                cur_entry = e
                break
        if cur_entry is not None and cur_entry['current'] is not None:
            lon, lat, alt, elev_a, elev_b = cur_entry['current']
            s = '%s: 纬 %.2f° 经 %.2f° 高 %.0f km' % (
                cur_entry['name'].strip(), lat, lon, alt)
            if elev_a is not None:
                s += '，本台仰角 %.1f°（%s）' % (
                    elev_a, '可见' if elev_a >= self._min_elev else '不可见')
            if elev_b is not None:
                s += '，对方仰角 %.1f°（%s）' % (
                    elev_b, '可见' if elev_b >= self._min_elev_b else '不可见')
            parts.append(s)
        elif not self._sats_order:
            parts.append('未选择卫星（请在来源窗口刷新 TLE 或选择卫星）')
        self._info.setText('  |  '.join(parts))

    def _tick(self):
        if self._closing:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        names, hidden = self._display_names()
        if self._need_track_recalc(now, names):
            self._track_key = (tuple(names), self._track_hours, self._observer())
            self._start_track_calc(now, names)
        self.canvas.twilight_points = compute_twilight_points(now)
        self._refresh_entries(now)
        self._update_info(now, hidden)
        self.canvas.update()

    def closeEvent(self, event):
        self._closing = True
        self._timer.stop()
        w = self._worker
        if w is not None and w.isRunning():
            w.requestInterruption()
            w.wait(3000)
        self._worker = None
        if self._source is not None:
            if getattr(self._source, '_map_window', None) is self:
                self._source._map_window = None
        if self in _open_windows:
            _open_windows.remove(self)
        QMainWindow.closeEvent(self, event)


def open_map(parent, sats, home=None, station_b=None, selected_name=None,
             source=None, min_elev=0.0, min_elev_b=None,
             on_min_elev_change=None):
    """打开卫星地图窗口。

    sats: [(name, Satrec), ...] —— 来源窗口当前「已选择的卫星」（范围/自选卫星生效后的列表）
    home / station_b: (lat, lon, alt) 或 None
    selected_name: 初始聚焦的卫星名（来源表格选中行）
    source: 来源窗口（卫星过境 / 通联预测），用于关闭时清理引用
    min_elev: 本台（台站 A）判定「可见」的最低仰角（度），用于轨迹可见区段高亮
    min_elev_b: 对方台（台站 B）最低仰角（度）；通联预测时给出，用于高亮对方可见区段
    on_min_elev_change: 可选回调 (a, b)；地图内调整最低仰角时调用，用于把修改
                         同步回来源窗口（更新其控件 / 重新预测 / 落盘）

    窗口为**独立普通窗口**（不设为来源窗口的子窗口），因此在任务栏有独立按钮、
    可独立最小化；关闭时仍通过 source 清理引用。
    轨迹时长不由调用方指定：自动恢复上次使用的值（sat_map_hours），并与其他
    已打开的地图窗口保持一致。
    """
    # 不把来源窗口作为父对象——否则会成为其拥有的子窗口，Windows 下不显示任务栏
    # 按钮、且会随父窗口一起最小化。这里让它像普通顶层窗口一样独立存在。
    win = MapWindow(None, sats, home=home, station_b=station_b,
                    selected_name=selected_name, source=source,
                    min_elev=min_elev, min_elev_b=min_elev_b,
                    on_min_elev_change=on_min_elev_change)
    _open_windows.append(win)
    win.show()
    return win


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    sats = sp.load_amateur_satellites()
    sel = sats[0][0] if sats else None
    open_map(None, sats, home=(39.9, 116.4, 50.0), selected_name=sel, min_elev=10.0)
    app.exec()
