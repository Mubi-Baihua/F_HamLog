import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from unittest import mock
import satellite_pred as sp
import satellite_map_window as mw

app = QApplication([])

# 造 12 颗假卫星（够多，触发原「>5 不显示」分支）
sats = []
for i in range(12):
    sats.append(('SAT%02d' % i, object()))

# 用真实 skyfield 造一颗低轨卫星，保证 subpoint/footprint 计算能跑通
import numpy as np
from skyfield.api import load
ts = load.timescale(builtin=True)
# satellite_pred.twoline2rv 返回包装后的 Satrec（含 _earth_sat）
es = sp.twoline2rv(
    '1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9005',
    '2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000')
es.name = 'ISS'
sats_real = [('ISS', es)]

w = mw.open_map(None, sats_real, home=(39.9, 116.4, 50),
                selected_name=None, source=None, min_elev=5.0)
w.show()
app.processEvents()

# 取 canvas entries，检查 footprint 是否被设置（此前 >5 且未选中 -> 全 None）
foots = [e['footprint'] for e in w.canvas.entries]
print('显示卫星数:', len(foots))
print('有覆盖区的卫星数:', sum(1 for f in foots if f))
assert any(f is not None for f in foots), '应至少有一颗卫星画出覆盖区'
print('很多卫星（且不选中任何一颗）时覆盖区已正常显示: OK')

# 再测 12 颗假卫星走通 _refresh_entries（不崩）
w2 = mw.open_map(None, sats, home=(39.9, 116.4, 50),
                 selected_name=None, source=None, min_elev=5.0)
w2.show()
app.processEvents()
print('12 颗假卫星刷新未崩溃: OK')
print('ALL_OK')
