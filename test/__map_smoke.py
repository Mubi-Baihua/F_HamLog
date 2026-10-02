import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\F-Dev\BIG\F_HamLog')
from PySide6.QtWidgets import QApplication
import satellite_pred as sp
import satellite_map_window as mw

app = QApplication([])
l1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9005"
l2 = "2 25544  51.6400 208.9163 0006703  69.9862 290.2000 15.50000000 10000"
sat = sp.twoline2rv(l1, l2, name="ISS (ZARYA)")
sats = [("ISS (ZARYA)", sat)]
win = mw.open_map(None, sats, home=(39.9, 116.4, 50.0), selected_name=None, min_elev=10.0)
win._tick()
print("entries:", [(e['name'], e['focus']) for e in win.canvas.entries])

# 1) 下拉框选星聚焦
win._combo.setCurrentIndex(1)   # index0 = 全部, index1 = ISS
win._on_combo(1)
print("focus after combo select ISS:", win._focus)

# 2) 点击聚焦（on_pick 即 set_satellite）
win.canvas.on_pick("ISS (ZARYA)")
print("focus after on_pick ISS:", win._focus)

# 3) _pick_hit 命中：取 ISS 当前位置屏幕坐标
ent = win.canvas.entries[0]
cx, cy = win.canvas._xy(ent['current'][0], ent['current'][1])
print("pick_hit at ISS current =>", win.canvas._pick_hit(cx, cy))
print("pick_hit at (5,5) =>", win.canvas._pick_hit(5, 5))

# 4) 切回“全部”，焦点应保留
win._combo.setCurrentIndex(0)
win._on_combo(0)
print("focus after back to ALL:", win._focus)

win.close()
print("SMOKE_OK")
