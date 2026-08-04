import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import datetime
import traceback

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QPixmap

import satellite_pred as sp
import satellite_map_window as mw

app = QApplication(sys.argv)

ok = True

# 1) ground_track 返回 5 元组，且两站仰角不同
sats = sp.load_amateur_satellites()
name, sat = sats[0]
home = (39.9, 116.4, 50.0)
b = (35.0, 139.0, 20.0)
gt = sp.ground_track(sat, datetime.datetime.now(datetime.timezone.utc),
                     1.0, 30, observer=home, observer_b=b)
assert isinstance(gt, list) and len(gt) == 30, 'ground_track 长度错误'
for p in gt:
    assert len(p) == 5, 'ground_track 应是 5 元组: %r' % (p,)
ea = gt[15][3]
eb = gt[15][4]
print('ground_track OK: 例点 elev_a=%.2f elev_b=%.2f' % (ea, eb))
assert ea is not None and eb is not None

# 2) _visible_runs 通用化
from satellite_map_window import MapCanvas, _split_dateline
canvas = MapCanvas()
# 构造 5 元组轨迹：elev_a 在中间一段可见，elev_b 在另一段可见
track = []
for i in range(20):
    ea_v = 30.0 if 5 <= i <= 12 else -5.0
    eb_v = 30.0 if 8 <= i <= 16 else -5.0
    track.append((i * 5.0, (i - 10) * 3.0, 500.0, ea_v, eb_v))
runs_a = canvas._visible_runs(track, 3, 0.0)
runs_b = canvas._visible_runs(track, 4, 0.0)
# A 可见: i 5..12 -> 至少一条 run 覆盖
a_idx = sorted(i for run in runs_a for i in range(len(track)) if track[i] in run)
print('A visible runs:', [[track[i][0] for i in range(len(track)) if track[i] in run] for run in runs_a])
assert any(track[i][3] >= 0.0 for i in range(len(track)) if track[i] in runs_a[0])
assert any(track[i][4] >= 0.0 for i in range(len(track)) if track[i] in runs_b[0])
print('visible_runs OK: A段数=%d B段数=%d' % (len(runs_a), len(runs_b)))

# 3) _draw_track 对 home_known + b_known 都不报错
canvas.entries = [{
    'name': name, 'color': mw._color_for(0), 'track': track,
    'current': (track[-1][0], track[-1][1], 500.0, 30.0, 30.0),
    'footprint': None, 'focus': True,
}]
canvas.home_known = True
canvas.b_known = True
canvas.min_elev = 0.0
canvas.min_elev_b = 0.0
pix = QPixmap(400, 200)
pp = QPainter(pix)
canvas._draw_track(pp, canvas.entries[0])
pp.end()
print('draw_track OK (home+bold + b dashed)')

# 4) MapWindow 独立窗口（parent=None）+ 5 元组 current
win = mw.MapWindow(None, sats[:3],
                   home=home, station_b=b,
                   min_elev=10.0, min_elev_b=15.0)
win._refresh_entries(datetime.datetime.now(datetime.timezone.utc))
for e in win.canvas.entries:
    assert e['current'] is not None and len(e['current']) == 5, 'current 应为 5 元组'
assert win.canvas.b_known is True, 'b_known 应为 True'
assert win.canvas.min_elev_b == 15.0
print('MapWindow OK: b_known=%s min_elev_b=%.1f' % (win.canvas.b_known, win.canvas.min_elev_b))
win.close()

print('\nALL OK')
