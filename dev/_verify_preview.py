import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import datetime
from PySide6.QtWidgets import QApplication

import satellite_map_window as mw

app = QApplication(sys.argv)

canvas = mw.MapCanvas()
canvas.resize(960, 480)
canvas.home_known = True
canvas.b_known = True
canvas.min_elev = 0.0
canvas.min_elev_b = 0.0
canvas.show_track = True
canvas.show_footprint = False
canvas.show_labels = True

# 构造两颗卫星的合成轨迹：横贯地图的一条正弦路径，
# 各自有一段「本台可见」(实线加粗) 与「对方可见」(虚线加粗) 的弧段。
def make_track(phase, a_lo, a_hi, b_lo, b_hi):
    tr = []
    for i in range(120):
        t = i / 119.0
        lon = -150.0 + 300.0 * t
        lat = 40.0 + 35.0 * __import__('math').sin(t * 6.283 + phase)
        ea = 40.0 if a_lo <= i <= a_hi else -10.0
        eb = 40.0 if b_lo <= i <= b_hi else -10.0
        tr.append((lon, lat, 550.0, ea, eb))
    return tr

entries = [
    {'name': 'SAT-A', 'color': mw._color_for(0), 'track': make_track(0.0, 20, 55, 60, 95),
     'current': (make_track(0.0, 20, 55, 60, 95)[-1]), 'footprint': None, 'focus': True},
    {'name': 'SAT-B', 'color': mw._color_for(1), 'track': make_track(1.7, 70, 105, 10, 45),
     'current': (make_track(1.7, 70, 105, 10, 45)[-1]), 'footprint': None, 'focus': False},
]
canvas.entries = entries
canvas.stations = [(39.9, 116.4, 'Home', (200, 30, 30)),
                   (35.0, 139.0, 'Peer', (30, 90, 200))]

canvas.repaint()
app.processEvents()
pix = canvas.grab()
out = mw.__file__.replace('satellite_map_window.py', '') + '_preview_bold.png'
pix.save(out)
print('saved', out)
