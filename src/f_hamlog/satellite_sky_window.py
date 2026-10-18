# -*- coding: utf-8 -*-
"""satellite_sky_window.py —— 卫星过境视图（极坐标天空图 / sky plot）

从「卫星过境」与「通联预测」两个窗口的结果行打开：用正北朝上、正东朝右的
极坐标圆盘显示卫星在本次可见窗口内的方位角 / 仰角轨迹。

  * 中心 = 天顶（90° 仰角），外圈 = 地平线（0°），同心圆为 30° / 60°；
  * 强调色实线 = 已经过去的部分，虚线 = 尚未到达的部分，箭头指向运动方向；
  * 空心小圆 = 太阳此刻的天空位置（判断是否处于日照 / 地影）；
  * 月牙 = 月亮此刻的天空位置（受光面朝太阳，可粗看月相朝向）；
  * 右侧读数面板 = 方位角 / 仰角 / 距离 / 高度，随时间每秒刷新。

**只画必要的素色线条**：不做阴影、光晕、渐变、圆角，可通联时段只是把线画粗。

**配色全部取自系统调色板**（QPalette）：强调色 = Highlight，文字 = WindowText，
底色 = Base，网格 / 刻度 / 太阳由这几色混合得到。因此跟随系统主题色与深浅色，
不写死任何颜色；系统换主题时窗口按 PaletteChange 自动重取。

通联预测打开时并排画两站（台站 A / 台站 B）的天空图，两站各自独立计算。
窗口按真实时间每秒刷新一次（「实时」按钮控制），拖动下方滑块可回看 / 预览
窗口内任意时刻。
"""

import datetime
import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QFont, QFontMetricsF, QPainter, QPalette,
                           QPen, QPolygonF)
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from f_hamlog import i18n, satellite_pred as sp, theme

# 本机时区（与其它卫星窗口一致：跟随系统，不做固定偏移）
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo

# 轨迹采样点数：单次过境最长 20 分钟上下，240 点 ≈ 5 秒/点，
# 曲线足够平滑，且只花一次 skyfield 矢量调用的时间。
SKY_SAMPLES = 240

# 实时刷新间隔（毫秒）
TICK_MS = 1000

# 读数面板宽度（像素）
PANEL_W = 208

# 打开中的窗口（关闭时自动移出），防止被 Python 侧回收
_OPEN = []


def _as_utc(dt):
    """把时间统一成带 UTC 时区的 datetime。

    接受 Julian Date（int / float，与预测结果里的 xxx_jd 字段一致），
    或 datetime（naive 视为 UTC）。
    """
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        return sp.jd_to_datetime(float(dt))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _duration_text(sec):
    """时长文案（与「卫星过境」窗口同一套写法，便于词表复用模板）。"""
    sec = int(round(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return '%d时%d分' % (h, m)
    if m > 0:
        return '%d分%d秒' % (m, s) if s else '%d分' % m
    return '%d秒' % s


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class SkyPlot(QWidget):
    """单个观测站的极坐标天空图。

    track : sp.sky_track() 的返回（list[dict]，含 jd / azimuth / elevation /
            range_km / alt_km），由外部一次算好；
    now   : 当前时刻的读数 dict（jd / azimuth / elevation / range_km / alt_km）；
    sun   : 太阳此刻的 (az, el)。

    圆盘里只画图，读数交给右侧面板（那边是普通控件，排版更规整）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.track = []
        self.now = None
        self.sun = None
        self.moon = None
        self.emphasis = None     # (jd0, jd1)：可通联时段，这段轨迹加粗
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._c = {}
        self._apply_palette()

    # ---- 主题配色：全部由系统调色板混合得到 ----
    def _apply_palette(self):
        pal = self.palette()
        base = pal.color(QPalette.Base)
        text = pal.color(QPalette.WindowText)
        accent = pal.color(QPalette.Highlight)
        self._c = {
            'bg': base,
            'ring': theme.blend(text, base, 0.84),       # 30° / 60° 环
            'horizon': theme.blend(text, base, 0.52),    # 地平圈
            'axis': theme.blend(text, base, 0.80),       # 十字线 / 短刻度
            'tick': theme.blend(text, base, 0.52),       # 30° 方位刻度
            'text': text,
            'label': theme.hint_color(self),
            'accent': accent,
            'sun': theme.blend(accent, text, 0.30),
            'moon': theme.blend(text, base, 0.15),
        }

    def apply_theme(self):
        self._apply_palette()
        self.update()

    # ---- 数据 ----
    def set_track(self, track):
        self.track = list(track or [])
        self.update()

    def set_now(self, jd, azimuth, elevation, range_km, alt_km):
        self.now = {
            'jd': float(jd),
            'azimuth': float(azimuth),
            'elevation': float(elevation),
            'range_km': float(range_km),
            'alt_km': float(alt_km),
        }
        self.update()

    def set_sun(self, azimuth, elevation):
        self.sun = (float(azimuth), float(elevation))
        self.update()

    def set_moon(self, azimuth, elevation):
        self.moon = (float(azimuth), float(elevation))
        self.update()

    def set_emphasis(self, jd0, jd1):
        """标出「可通联」时段：这一段轨迹画得更粗（双方都能听见的那一小段）。"""
        if jd0 is None or jd1 is None:
            self.emphasis = None
        else:
            self.emphasis = (float(min(jd0, jd1)), float(max(jd0, jd1)))
        self.update()

    # ---- 几何 ----
    def _geometry(self):
        """返回 (w, h, cx, cy, R, side)：圆盘居中，R 已留出方位字与刻度的空间。"""
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        side = min(w, h)
        pad = _clamp(side * 0.135, 22.0, 58.0)
        return w, h, w / 2.0, h / 2.0, max(10.0, side / 2.0 - pad), side

    @staticmethod
    def _point(cx, cy, R, az_deg, el_deg):
        """地平坐标 → 画布坐标：正北朝上，正东朝右。"""
        el = max(-5.0, min(90.0, float(el_deg)))
        r = R * (90.0 - el) / 90.0
        if r > R:
            r = R
        a = math.radians(float(az_deg))
        return QPointF(cx + r * math.sin(a), cy - r * math.cos(a))

    # ---- 绘制 ----
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        # 素底：直接铺系统 Base 色，不描边、不做圆角
        p.fillRect(self.rect(), self._c['bg'])

        w, h, cx, cy, R, side = self._geometry()
        if R < 14.0:
            return

        lw = max(1.0, side * 0.0022)          # 网格线宽
        cap_px = int(_clamp(side * 0.042, 9, 17))     # 方位字
        lab_px = int(_clamp(side * 0.028, 7, 13))     # 仰角刻度
        globe = QPointF(cx, cy)

        # 同心圆（地平圈加粗，30° / 60° 细环）
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._c['horizon'], max(1.4, lw * 1.6)))
        p.drawEllipse(globe, R, R)
        p.setPen(QPen(self._c['ring'], lw))
        for el in (30.0, 60.0):
            r = R * (90.0 - el) / 90.0
            p.drawEllipse(globe, r, r)

        # 十字线（虚线，比环更淡）
        pen = QPen(self._c['axis'], lw)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(cx - R, cy), QPointF(cx + R, cy))
        p.drawLine(QPointF(cx, cy - R), QPointF(cx, cy + R))
        # 天顶点
        p.setPen(Qt.NoPen)
        p.setBrush(self._c['axis'])
        p.drawEllipse(globe, max(1.6, side * 0.0035), max(1.6, side * 0.0035))

        # 方位刻度（每 30° 一小段，正东/南/西/北更长）与四个方位字
        f_cap = QFont(self.font())
        f_cap.setPixelSize(cap_px)
        f_cap.setBold(True)
        for deg in range(0, 360, 30):
            a = math.radians(deg)
            ca, sa = math.sin(a), -math.cos(a)
            long = (deg % 90 == 0)
            t0 = R + lw * 1.2
            t1 = R + (lw * 7.0 if long else lw * 4.0)
            p.setPen(QPen(self._c['tick'], max(1.0, lw * (1.2 if long else 0.9))))
            p.drawLine(QPointF(cx + ca * t0, cy + sa * t0),
                       QPointF(cx + ca * t1, cy + sa * t1))
        p.setFont(f_cap)
        p.setPen(QPen(theme.blend(self._c['text'], self._c['bg'], 0.18)))
        for deg, key in ((0, '北'), (90, '东'), (180, '南'), (270, '西')):
            a = math.radians(deg)
            dist = R + cap_px * 1.25
            pt = QPointF(cx + math.sin(a) * dist, cy - math.cos(a) * dist)
            r = cap_px * 1.05
            p.drawText(QRectF(pt.x() - r * 1.4, pt.y() - r, r * 2.8, r * 2.0),
                       Qt.AlignCenter, i18n.tr(key))

        # 仰角刻度：贴 315°（西北）方向的内侧，避开大多数过境轨迹
        f_lab = QFont(self.font())
        f_lab.setPixelSize(lab_px)
        p.setFont(f_lab)
        p.setPen(QPen(self._c['label']))
        for el in (30.0, 60.0):
            pt = self._point(cx, cy, R, 315.0, el)
            p.drawText(QRectF(pt.x() - lab_px * 2.6, pt.y() - lab_px * 0.95,
                              lab_px * 5.2, lab_px * 1.9),
                       Qt.AlignCenter, '%d°' % int(el))

        # 轨迹：已过 = 强调色实线，未到 = 虚线；
        # 可通联那一段只是把线画粗（不压暗、不发光、不加阴影）
        if self.track and self.now is not None:
            now_jd = self.now['jd']
            past, future, allp, runs = [], [], [], []
            run = []
            for s in self.track:
                if s['elevation'] < 0.0:
                    continue        # 地平线以下的采样点不画（窗口边缘的数值毛刺）
                pt = self._point(cx, cy, R, s['azimuth'], s['elevation'])
                allp.append(pt)
                if s['jd'] <= now_jd:
                    past.append(pt)
                    future = [pt]   # 未来段从当前时刻的采样点起笔，保证接续
                else:
                    future.append(pt)
                if self.emphasis and \
                        self.emphasis[0] <= s['jd'] <= self.emphasis[1]:
                    run.append(pt)
                elif run:
                    runs.append(run)
                    run = []
            if run:
                runs.append(run)

            tw = max(1.6, side * 0.0036)
            accent = self._c['accent']
            if len(future) >= 2:
                pen = QPen(accent, max(1.2, tw * 0.78),
                           Qt.CustomDashLine, Qt.RoundCap, Qt.RoundJoin)
                pen.setDashPattern([3.2, 2.6])
                p.setPen(pen)
                p.drawPolyline(QPolygonF(future))
            if len(past) >= 2:
                p.setPen(QPen(accent, tw, Qt.SolidLine,
                              Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline(QPolygonF(past))
            # 可通联段：同一支笔，只是更粗
            for seg in runs:
                if len(seg) >= 2:
                    p.setPen(QPen(accent, tw * 2.4, Qt.SolidLine,
                                  Qt.RoundCap, Qt.RoundJoin))
                    p.drawPolyline(QPolygonF(seg))
                elif seg:
                    # 窗口太短、只落进一个采样点：画一个加粗的圆点代替
                    p.setBrush(accent)
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(seg[0], tw * 1.1, tw * 1.1)
            if len(allp) >= 6:
                k = max(1, min(len(allp) - 2, int(len(allp) * 0.58)))
                self._draw_arrow(p, allp[k - 1], allp[k + 1],
                                 self._c['accent'], max(7.0, side * 0.014))

        # 太阳位置（空心圈 + 短射线，与实心的卫星标记区分）
        sun_pt = None
        if self.sun is not None and self.sun[1] >= 0.0:
            sun_pt = self._point(cx, cy, R, self.sun[0], self.sun[1])
            self._draw_sun(p, sun_pt.x(), sun_pt.y(), max(4.6, side * 0.0092))

        # 月亮位置（月牙；受光面朝太阳）
        if self.moon is not None and self.moon[1] >= 0.0:
            mn_pt = self._point(cx, cy, R, self.moon[0], self.moon[1])
            self._draw_moon(p, mn_pt.x(), mn_pt.y(),
                            max(5.6, side * 0.0118), sun_pt)

        # 卫星当前位置（地面以下时不画，读数仍给出负仰角）
        if self.now is not None and self.now['elevation'] >= 0.0:
            pt = self._point(cx, cy, R, self.now['azimuth'],
                             self.now['elevation'])
            self._draw_satellite(p, pt.x(), pt.y(), max(5.0, side * 0.0118))

    # ---- 元件 ----
    @staticmethod
    def _draw_arrow(p, a, b, color, size):
        """沿轨迹方向画一个实心三角箭头（尖端朝 b）。"""
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        ux, uy = dx / L, dy / L
        mx, my = (a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0
        tip = QPointF(mx + ux * size * 0.80, my + uy * size * 0.80)
        left = QPointF(mx - ux * size * 0.45 - uy * size * 0.62,
                       my - uy * size * 0.45 + ux * size * 0.62)
        right = QPointF(mx - ux * size * 0.45 + uy * size * 0.62,
                        my - uy * size * 0.45 - ux * size * 0.62)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([tip, left, right]))

    def _draw_satellite(self, p, x, y, s):
        """卫星标记：一个实心圆点 + 底色描边（不再打光晕）。"""
        globe = QPointF(x, y)
        p.setBrush(self._c['accent'])
        p.setPen(QPen(self._c['bg'], max(1.2, s * 0.24)))
        p.drawEllipse(globe, s, s)

    def _draw_sun(self, p, x, y, s):
        """太阳标记：一个空心小圆（与实心的卫星、月亮区分）。"""
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._c['sun'], max(1.2, s * 0.30)))
        p.drawEllipse(QPointF(x, y), s, s)

    def _draw_moon(self, p, x, y, s, sun_pt=None):
        """月亮标记：月牙。阴影圆朝「远离太阳」的一侧偏移，受光面因此朝太阳。"""
        color = self._c['moon']
        if sun_pt is not None:
            dx, dy = x - sun_pt.x(), y - sun_pt.y()
            L = math.hypot(dx, dy)
            ux, uy = (dx / L, dy / L) if L > 1e-6 else (0.72, -0.72)
        else:
            ux, uy = 0.72, -0.72
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(x, y), s, s)
        p.setBrush(self._c['bg'])
        p.drawEllipse(QPointF(x + ux * s * 0.62, y + uy * s * 0.62),
                      s * 0.94, s * 0.94)
        # 补一圈极细的轮廓，小尺寸下月牙才不至于糊掉
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, max(0.8, s * 0.14)))
        p.drawEllipse(QPointF(x, y), s * 0.94, s * 0.94)


class _Meter(QWidget):
    """极细的进度条（本次窗口已过比例），轨道与填充都取自系统调色板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_value(self, value):
        self._value = max(0.0, min(1.0, float(value)))
        self.update()

    def paintEvent(self, _event):
        pal = self.palette()
        base = pal.color(QPalette.Base)
        text = pal.color(QPalette.WindowText)
        accent = pal.color(QPalette.Highlight)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        w = float(self.width())
        h = float(self.height())
        # 方头进度条（不画圆角）
        p.setBrush(theme.blend(base, text, 0.16))
        p.drawRect(QRectF(0.0, h / 2.0 - 2.0, w, 4.0))
        if self._value > 0.0:
            p.setBrush(accent)
            p.drawRect(QRectF(0.0, h / 2.0 - 2.0,
                              max(4.0, w * self._value), 4.0))


class _Legend(QWidget):
    """面板底部的小图例：已过 / 未到 / 太阳 / 月亮（双站另有「可通联」）。
    颜色随系统调色板。"""

    KEYS = ('已过', '未到', '太阳', '月亮')
    KEY_EMPHASIS = '可通联'
    ROWS = len(KEYS)
    ROW_H = 19

    def __init__(self, parent=None, keys=None):
        super().__init__(parent)
        self.keys = tuple(keys) if keys else self.KEYS
        self.setFixedHeight(self.ROW_H * len(self.keys))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def paintEvent(self, _event):
        pal = self.palette()
        base = pal.color(QPalette.Base)
        text = pal.color(QPalette.WindowText)
        accent = pal.color(QPalette.Highlight)
        hint = theme.hint_color(self)
        sun = theme.blend(accent, text, 0.30)
        moon = theme.blend(text, base, 0.15)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        row_h = self.height() / float(len(self.keys))
        x0 = 4.0
        x1 = x0 + 26.0
        tx = x1 + 10.0
        cxm = (x0 + x1) / 2.0

        for i, key in enumerate(self.keys):
            y = row_h * (i + 0.5)
            if key == '已过':
                p.setPen(QPen(accent, 2.2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
            elif key == self.KEY_EMPHASIS:
                p.setPen(QPen(accent, 4.2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
            elif key == '未到':
                pen = QPen(accent, 1.9, Qt.CustomDashLine, Qt.RoundCap)
                pen.setDashPattern([3.0, 2.4])
                p.setPen(pen)
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
            elif key == '太阳':
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(sun, 1.3))
                p.drawEllipse(QPointF(cxm, y), 4.2, 4.2)
            else:
                # 月牙：实心圆 + 底色圆压掉一侧
                p.setPen(Qt.NoPen)
                p.setBrush(moon)
                p.drawEllipse(QPointF(cxm, y), 4.6, 4.6)
                p.setBrush(base)
                p.drawEllipse(QPointF(cxm + 2.6, y - 2.1), 4.4, 4.4)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(moon, 0.8))
                p.drawEllipse(QPointF(cxm, y), 4.2, 4.2)
            p.setPen(QPen(hint))
            fm = QFontMetricsF(f)
            p.drawText(QPointF(tx, y + fm.ascent() / 2.0 - 1.0), i18n.tr(key))


class SkyWindow(QMainWindow):
    """过境视图窗口：1 个（卫星过境）或 2 个（通联预测 A/B）天空图。

    布局：顶部「卫星名 + 状态胶囊 + 窗口时段」，中间「天空图（可两站并排）+
    右侧读数面板」，底部「实时 / 时间滑杆 / 时刻」。
    """

    def __init__(self, parent, sat_name, sat, stations, start_utc, end_utc,
                 info='', emphasis=None, auto_spans=False):
        super().__init__(parent)
        self._sat = sat
        self._sat_name = sat_name or ''
        self._info = info or ''
        self._stations = []
        for label, obs in stations:
            lat, lon, alt = obs
            self._stations.append((label, (float(lat), float(lon), float(alt))))

        self._start = _as_utc(start_utc)
        self._end = _as_utc(end_utc)
        if self._end <= self._start:
            self._end = self._start + datetime.timedelta(minutes=1)
        self._start_jd = sp.datetime_to_jd(self._start)
        self._end_jd = sp.datetime_to_jd(self._end)

        # 可通联时段（双站视图里加粗的那一段）
        self._emphasis = None
        if emphasis is not None:
            e0 = _jd_key(emphasis[0])
            e1 = _jd_key(emphasis[1])
            self._emphasis = (min(e0, e1), max(e0, e1))

        # 每个站自己的可见过境窗口：双站视图要「显示双方的全部过境」，
        # 所以按各站 AOS→LOS 取轨迹，时间轴取两者的并集；
        # 单站视图（卫星过境）不传 auto_spans，仍按传入的可见窗口。
        self._spans = [None] * len(self._stations)
        if auto_spans and self._emphasis is not None:
            mid = (self._emphasis[0] + self._emphasis[1]) / 2.0
            for idx, (_label, obs) in enumerate(self._stations):
                self._spans[idx] = _pass_span(sat, obs, mid)
            spans = [s for s in self._spans if s]
            if spans:
                self._start_jd = min(s[0] for s in spans)
                self._end_jd = max(s[1] for s in spans)
                self._start = sp.jd_to_datetime(self._start_jd)
                self._end = sp.jd_to_datetime(self._end_jd)

        self._follow = True       # 「实时」：按真实时间前进
        self._syncing = False     # 程序设置滑块时抑制 valueChanged 回调
        self._cur_jd = self._start_jd
        self._plots = []
        self._readouts = []       # 每站一组 {字段: QLabel}
        self._texts = []          # [(QLabel, 中文原文)]：切语言时统一重译
        self._hints = []          # 用 hint_css 着色的标签：换主题时重刷
        self._lines = []          # 分割线：换主题时重刷颜色
        self._panel = None
        self._legend = None
        self._state_text = ''

        self._build_ui()
        self._load_tracks()
        self._retranslate()

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        theme.watch_theme(self, self._on_theme)
        self._render_at(self._now_jd())

    # ---- 界面 ----
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 10)
        outer.setSpacing(10)

        # 顶部：卫星名 + 状态胶囊 + 时段
        head = QHBoxLayout()
        head.setSpacing(8)
        self._name_lbl = QLabel(self._sat_name)
        f = self._name_lbl.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 2.0)
        self._name_lbl.setFont(f)
        self._state_lbl = QLabel()
        self._state_lbl.setAlignment(Qt.AlignCenter)
        f2 = self._state_lbl.font()
        f2.setPointSizeF(f2.pointSizeF() - 0.5)
        self._state_lbl.setFont(f2)
        self._span_lbl = QLabel()
        self._hints.append(self._span_lbl)
        head.addWidget(self._name_lbl)
        head.addWidget(self._state_lbl)
        head.addStretch(1)
        head.addWidget(self._span_lbl)
        outer.addLayout(head)

        if self._info:
            self._note_lbl = QLabel()
            self._hints.append(self._note_lbl)
            outer.addWidget(self._note_lbl)
        else:
            self._note_lbl = QLabel()

        # 中间：天空图（1 或 2 张）+ 右侧读数面板
        body = QHBoxLayout()
        body.setSpacing(12)
        for label, _obs in self._stations:
            col = QVBoxLayout()
            col.setSpacing(4)
            if len(self._stations) > 1:
                cap = QLabel()
                cap.setAlignment(Qt.AlignHCenter)
                fc = cap.font()
                fc.setBold(True)
                cap.setFont(fc)
                self._texts.append((cap, label))
                col.addWidget(cap)
            plot = SkyPlot(self)
            col.addWidget(plot, 1)
            self._plots.append(plot)
            body.addLayout(col, 1)
        body.addWidget(self._build_panel(), 0)
        outer.addLayout(body, 1)

        # 底部：实时开关 + 时间滑杆 + 当前时刻
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self._live_btn = QPushButton()
        self._live_btn.setCheckable(True)
        self._live_btn.setChecked(True)
        self._live_btn.toggled.connect(self._on_live_toggled)
        self._texts.append((self._live_btn, '实时'))
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(20)
        self._slider.valueChanged.connect(self._on_slider)
        self._time_lbl = QLabel()
        f3 = self._time_lbl.font()
        f3.setBold(True)
        self._time_lbl.setFont(f3)
        ctrl.addWidget(self._live_btn)
        ctrl.addWidget(self._slider, 1)
        ctrl.addWidget(self._time_lbl)
        outer.addLayout(ctrl)

        if len(self._stations) > 1:
            self.resize(1120, 600)
        else:
            self.resize(820, 560)

    def _build_panel(self):
        """右侧读数面板：每站一组「标签 → 数值」，底部是图例。"""
        panel = QFrame()
        panel.setObjectName('skyPanel')
        panel.setFixedWidth(PANEL_W)
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 10, 12, 8)
        v.setSpacing(8)

        title = QLabel()
        ft = title.font()
        ft.setBold(True)
        ft.setPointSizeF(ft.pointSizeF() - 0.5)
        title.setFont(ft)
        self._texts.append((title, '过境数据'))
        v.addWidget(title)

        f_num = QFont(self.font())
        f_num.setBold(True)
        f_num.setPointSizeF(f_num.pointSizeF() + 1.0)

        for idx, (label, _obs) in enumerate(self._stations):
            if len(self._stations) > 1:
                cap = QLabel()
                cap.setWordWrap(False)
                fc = cap.font()
                fc.setBold(True)
                cap.setFont(fc)
                self._texts.append((cap, label))
                v.addWidget(cap)
            grid = QGridLayout()
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(2)
            rows = {}
            for r, key in enumerate(('方位角', '仰角', '距离', '高度')):
                k_lbl = QLabel()
                self._hints.append(k_lbl)
                self._texts.append((k_lbl, key))
                val = QLabel('—')
                val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                val.setFont(f_num)
                grid.addWidget(k_lbl, r, 0)
                grid.addWidget(val, r, 1)
                rows[key] = val
            grid.setColumnStretch(1, 1)
            v.addLayout(grid)
            self._readouts.append(rows)
            if idx < len(self._stations) - 1:
                v.addWidget(self._hline())

        v.addStretch(1)
        v.addWidget(self._hline())

        # 本次窗口进度（填充面板中段的空白，也让「过到哪儿了」一眼可见）
        cap = QLabel()
        self._hints.append(cap)
        self._texts.append((cap, '本次窗口'))
        v.addWidget(cap)
        self._meter = _Meter(panel)
        v.addWidget(self._meter)
        self._prog_lbl = QLabel()
        self._hints.append(self._prog_lbl)
        v.addWidget(self._prog_lbl)

        v.addWidget(self._hline())
        keys = list(_Legend.KEYS)
        if self._emphasis is not None:
            keys.insert(1, _Legend.KEY_EMPHASIS)
        self._legend = _Legend(panel, keys)
        v.addWidget(self._legend)

        self._panel = panel
        self._style_panel()
        return panel

    def _style_panel(self):
        """面板不描边、不铺底、不做圆角，只用细分隔线分组（换主题时重刷）。"""
        if self._panel is None:
            return
        self._panel.setStyleSheet('QFrame#skyPanel{border:0;background:transparent;}')
        color = theme.border_color(self).name()
        for line in self._lines:
            line.setStyleSheet('color:%s;background:%s;' % (color, color))

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setFixedHeight(1)
        self._lines.append(line)
        return line

    # ---- 轨迹 ----
    def _load_tracks(self):
        """一次算好每个站的方位-仰角轨迹（窗口打开时算一次即可）。

        有 span（双站视图里各站的 AOS→LOS）就按自己的窗口算，
        否则按传入的可见窗口 [start, end] 算。
        """
        for idx, plot in enumerate(self._plots):
            _label, obs = self._stations[idx]
            span = self._spans[idx] if idx < len(self._spans) else None
            try:
                if span:
                    t0 = sp.jd_to_datetime(span[0])
                    t1 = sp.jd_to_datetime(span[1])
                    track = sp.sky_track(self._sat, obs, t0, t1,
                                         samples=SKY_SAMPLES)
                else:
                    track = sp.sky_track(self._sat, obs, self._start,
                                         self._end, samples=SKY_SAMPLES)
            except Exception:
                track = []
            plot.set_track(track)
            if self._emphasis is not None:
                plot.set_emphasis(self._emphasis[0], self._emphasis[1])

        # 各站轨迹算完后，时间轴要真正包住所有采样点：jd_to_datetime 只到微秒、
        # 预测的 AOS/LOS 更精细，直接用预测值当轴首尾会差零点几秒。
        starts = [p.track[0]['jd'] for p in self._plots if p.track]
        ends = [p.track[-1]['jd'] for p in self._plots if p.track]
        if any(self._spans) and starts:
            self._start_jd = min([self._start_jd] + starts)
            self._end_jd = max([self._end_jd] + ends)
            self._start = sp.jd_to_datetime(self._start_jd)
            self._end = sp.jd_to_datetime(self._end_jd)
            self._cur_jd = min(max(self._cur_jd, self._start_jd), self._end_jd)

    # ---- 时间 ----
    def _now_jd(self):
        now = sp.datetime_to_jd(datetime.datetime.now(datetime.timezone.utc))
        return min(max(now, self._start_jd), self._end_jd)

    def _state_of_now(self):
        now = sp.datetime_to_jd(datetime.datetime.now(datetime.timezone.utc))
        if now < self._start_jd:
            return '未开始'
        if now > self._end_jd:
            return '已结束'
        return '进行中'

    def _span_text(self):
        a = self._start.astimezone(LOCAL_TZ)
        b = self._end.astimezone(LOCAL_TZ)
        if a.date() == b.date():
            txt = '%s → %s' % (a.strftime('%Y-%m-%d %H:%M:%S'),
                               b.strftime('%H:%M:%S'))
        else:
            txt = '%s → %s' % (a.strftime('%Y-%m-%d %H:%M:%S'),
                               b.strftime('%m-%d %H:%M:%S'))
        return txt + ' ｜ ' + i18n.tr('时长') + ' ' + \
            i18n.tr(_duration_text((self._end - self._start).total_seconds()))

    @staticmethod
    def _alt_at(jd, track):
        """取轨迹里离 jd 最近的采样点高度（高度变化很慢，无需插值）。

        jd 不在该站轨迹的时间范围内时返回 None（那边天空图本来就没有轨迹）。
        """
        if not track:
            return None
        if jd < track[0]['jd'] - 1e-6 or jd > track[-1]['jd'] + 1e-6:
            return None
        lo, hi = 0, len(track) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if track[mid]['jd'] < jd:
                lo = mid + 1
            else:
                hi = mid
        best = track[lo]
        if lo > 0 and abs(track[lo - 1]['jd'] - jd) < abs(best['jd'] - jd):
            best = track[lo - 1]
        return best['alt_km']

    def _sync_slider(self, jd):
        span = self._end_jd - self._start_jd
        v = 0 if span <= 0 else int(round((jd - self._start_jd) / span * 1000.0))
        v = max(0, min(1000, v))
        if self._slider.value() != v:
            self._syncing = True
            self._slider.setValue(v)
            self._syncing = False

    def _render_at(self, jd):
        """把各站天空图与读数刷新到 jd 时刻（az/el 用 skyfield 现算，读数才准）。"""
        self._cur_jd = float(jd)
        if self._follow:
            self._sync_slider(self._cur_jd)

        when = sp.jd_to_datetime(self._cur_jd)
        for idx, plot in enumerate(self._plots):
            _label, obs = self._stations[idx]
            try:
                ob = sp.observe(self._sat, self._cur_jd, obs)
                sun_az, sun_el = sp.sun_altaz(obs[0], obs[1], when)
                moon_az, moon_el = sp.moon_altaz(obs[0], obs[1], when)
            except Exception:
                continue
            alt = self._alt_at(self._cur_jd, plot.track)
            plot.set_now(self._cur_jd, ob['azimuth'], ob['elevation'],
                         ob['range_km'], 0.0 if alt is None else alt)
            plot.set_sun(sun_az, sun_el)
            plot.set_moon(moon_az, moon_el)

            if idx < len(self._readouts):
                rows = self._readouts[idx]
                rows['方位角'].setText('%.1f°' % ob['azimuth'])
                rows['仰角'].setText('%.1f°' % ob['elevation'])
                rows['距离'].setText('%.0f km' % ob['range_km'])
                rows['高度'].setText('—' if alt is None else '%.0f km' % alt)

        local = when.astimezone(LOCAL_TZ)
        self._time_lbl.setText(local.strftime('%Y-%m-%d %H:%M:%S'))
        self._update_progress()
        state = self._state_of_now()
        if state != self._state_text:
            self._state_text = state
            self._state_lbl.setText(i18n.tr(state))
            self._style_state()

    # ---- 交互 ----
    def _update_progress(self):
        """面板里的「本次窗口」进度条与已过 / 剩余文案。"""
        span = self._end_jd - self._start_jd
        frac = 0.0 if span <= 0 else (self._cur_jd - self._start_jd) / span
        frac = max(0.0, min(1.0, frac))
        self._meter.set_value(frac)
        left = (self._end - sp.jd_to_datetime(self._cur_jd)).total_seconds()
        self._prog_lbl.setText('%s %d%% ｜ %s %s' % (
            i18n.tr('已过'), int(round(frac * 100.0)), i18n.tr('剩余'),
            i18n.tr(_duration_text(max(0.0, left)))))

    def _tick(self):
        if not self._follow or not self.isVisible():
            return
        self._render_at(self._now_jd())

    def _on_live_toggled(self, checked):
        self._follow = bool(checked)
        if checked:
            self._render_at(self._now_jd())

    def _on_slider(self, value):
        if self._syncing:
            return
        if self._live_btn.isChecked():
            self._live_btn.blockSignals(True)
            self._live_btn.setChecked(False)
            self._live_btn.blockSignals(False)
        self._follow = False
        span = self._end_jd - self._start_jd
        self._render_at(self._start_jd + span * (value / 1000.0))

    # ---- 主题 ----
    def _style_state(self):
        """状态文字：不加底色、不加圆角，进行中用强调色，其余用次要文字色。"""
        pal = theme.palette(self)
        base = pal.color(QPalette.Base)
        text = pal.color(QPalette.WindowText)
        accent = pal.color(QPalette.Highlight)
        if self._state_text == '进行中':
            fg = accent
        else:
            fg = theme.blend(text, base, 0.22)
        self._state_lbl.setStyleSheet(
            'color:%s;background:transparent;padding:0;' % fg.name())

    def _on_theme(self):
        for plot in self._plots:
            plot.apply_theme()
        for lbl in self._hints:
            lbl.setStyleSheet(theme.hint_css())
        self._style_panel()
        if self._legend is not None:
            self._legend.update()
        self._style_state()

    # ---- 语言 ----
    def _retranslate(self):
        self._name_lbl.setText(self._sat_name)
        self._span_lbl.setText(self._span_text())
        if self._info:
            self._note_lbl.setText(i18n.tr(self._info))
        self._state_lbl.setText(i18n.tr(self._state_text or self._state_of_now()))
        self.setWindowTitle(i18n.tr('过境视图') + ' - ' + self._sat_name)
        for lbl, src in self._texts:
            lbl.setText(i18n.tr(src))
        for lbl in self._hints:
            lbl.setStyleSheet(theme.hint_css())
        if self._legend is not None:
            self._legend.update()
        if getattr(self, '_meter', None) is not None:
            self._update_progress()

    def changeEvent(self, event):
        if event.type() == QEvent.LanguageChange:
            self._retranslate()
        QMainWindow.changeEvent(self, event)

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        if self in _OPEN:
            _OPEN.remove(self)
        QMainWindow.closeEvent(self, event)


def _jd_key(value):
    """把 datetime / JD 统一成 JD 数值，用于判断「同一个过境窗口」。"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime.datetime):
        dt = value if value.tzinfo else value.replace(
            tzinfo=datetime.timezone.utc)
        return sp.datetime_to_jd(dt)
    return 0.0


def _pass_span(sat, obs, around_jd, pad_min=75):
    """找包含 around_jd 的那一次可见过境，返回 (aos_jd, los_jd)。

    双站视图要显示「双方的全部过境」，各站自己的 AOS→LOS 比可通联窗口更宽，
    这里以可通联窗口的中点为锚，在 ±pad_min 分钟内按 0° 地平线求 AOS/LOS。
    取不到时返回 None（调用方沿用传入的窗口）。
    """
    try:
        around = sp.jd_to_datetime(float(around_jd))
    except Exception:
        return None
    t0 = around - datetime.timedelta(minutes=pad_min)
    try:
        passes = sp.predict_passes(sat, obs, t0,
                                   duration_hours=pad_min / 30.0,
                                   min_elevation_deg=0.0, step_sec=15)
    except Exception:
        return None
    if not passes:
        return None
    for p in passes:
        if p['aos_jd'] <= float(around_jd) <= p['los_jd']:
            return p['aos_jd'], p['los_jd']
    p = min(passes, key=lambda q: abs(q['aos_jd'] - float(around_jd)))
    return p['aos_jd'], p['los_jd']


def _place_near(win, ref):
    """把窗口摆到来源窗口中间（夹在工作区里，不出屏）。"""
    try:
        fg = ref.frameGeometry()
        wg = win.frameGeometry()
        area = ref.screen().availableGeometry()
        x = fg.center().x() - wg.width() // 2
        y = fg.center().y() - wg.height() // 2
        win.move(max(area.left(), min(x, area.right() - wg.width() + 1)),
                 max(area.top(), min(y, area.bottom() - wg.height() + 1)))
    except Exception:
        pass


def open_sky(parent, sat_name, sat, stations, start_utc, end_utc, info='',
             emphasis=None, auto_spans=False):
    """打开过境视图窗口。

    parent    : 来源窗口（卫星过境 / 通联预测），**只用来定初始位置**，不设为 Qt 父对象
    sat_name  : 卫星显示名
    sat       : satellite_pred.Satrec
    stations  : [(站名, (lat, lon, alt)), ...]；1 个 = 单站，2 个 = A/B 双站并排
    start/end : 可见（或可通联）窗口的起止时刻，UTC datetime 或 Julian Date
    info      : 顶部副标题（中文原文，窗口内统一翻译）
    emphasis  : (起, 止)：需要加粗的时段（通联预测传可通联窗口）
    auto_spans: True 时按各站自己的 AOS→LOS 取轨迹（「双方的全部过境」），
                时间轴变成两者的并集；单站视图保持传入窗口即可

    坐标不设门槛：经纬度 0° 也是合法位置（赤道 / 本初子午线），照常绘制。

    窗口是**独立普通窗口**（与卫星地图一致）：不挂在来源窗口下面，所以最小化 /
    还原来源窗口时视图不动（Windows 下被拥有的窗口会跟着一起最小化），
    任务栏也有自己的按钮。

    同一颗卫星 + 同一个窗口时刻（站数相同）已打开时，直接聚焦那个窗口，
    不再堆出重复的视图。返回窗口对象；sat 为空时返回 None（调用方负责提示）。
    """
    if sat is None:
        return None
    key = (sat_name or '', len(stations), round(_jd_key(start_utc), 6),
           bool(auto_spans))
    for w in list(_OPEN):
        if getattr(w, '_sky_key', None) == key and w.isVisible():
            if w.isMinimized():
                w.showNormal()
            w.raise_()
            w.activateWindow()
            return w

    # 不把来源窗口当父对象——否则成为它「拥有的窗口」，Windows 下会随它一起最小化
    win = SkyWindow(None, sat_name, sat, stations, start_utc, end_utc, info,
                    emphasis=emphasis, auto_spans=auto_spans)
    win._sky_key = key
    win._source = parent
    if parent is not None:
        _place_near(win, parent)
    win.show()
    win.raise_()
    win.activateWindow()
    _OPEN.append(win)
    return win
