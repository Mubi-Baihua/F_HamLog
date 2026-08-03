import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import datetime
from PySide6.QtWidgets import QApplication

import satellite_pred as sp
import satellite_map_window as mw

app = QApplication(sys.argv)
sats = sp.load_amateur_satellites()[:2]
home = (39.9, 116.4, 50.0)
b = (35.0, 139.0, 20.0)

callsA, callsB = [], []

def cbA(a, bb):
    callsA.append((a, bb))

def cbB(a, bb):
    callsB.append((a, bb))

# 模拟「卫星过境」地图（无对方台）
winA = mw.MapWindow(None, sats, home=home, min_elev=5.0, on_min_elev_change=cbA)
# 模拟「通联预测」地图（有对方台）
winB = mw.MapWindow(None, sats, home=home, station_b=b,
                    min_elev=5.0, min_elev_b=8.0, on_min_elev_change=cbB)
# 手动登记到 _open_windows（open_map 才会加，这里直接构造）
mw._open_windows.append(winA)
mw._open_windows.append(winB)

# 1) 卫星过境地图调本台阈值 -> A 两侧一致，B 阈值不被污染，回调只触发 1 次
winA._on_el_a(12.0)
assert abs(winA.canvas.min_elev - 12.0) < 1e-6
assert abs(winB.canvas.min_elev - 12.0) < 1e-6, '对方地图本台阈值应同步'
assert abs(winB._min_elev_b - 8.0) < 1e-6, '对方地图 B 阈值不应被卫星过境地图覆盖'
assert len(callsA) == 1 and callsA[0] == (12.0, 5.0)
assert len(callsB) == 0, '对方地图不应因广播触发来源回调'
print('卫星过境改A: OK  A=%g B_b=%g  cbA=%s cbB=%s'
      % (winA.canvas.min_elev, winB._min_elev_b, callsA, callsB))

# 2) 通联预测地图调 B 阈值 -> B 两侧一致，回调 1 次，卫星过境地图无 B 不受影响
winB._on_el_b(20.0)
assert abs(winB.canvas.min_elev_b - 20.0) < 1e-6
assert abs(winA.canvas.min_elev_b - 5.0) < 1e-6, '卫星过境地图无 B，b 保持原值'
assert len(callsB) == 1 and callsB[0] == (12.0, 20.0)
assert len(callsA) == 1, '卫星过境地图回调不应触发'
print('通联预测改B: OK  B_b=%g  cbB=%s' % (winB.canvas.min_elev_b, callsB))

# 3) 来源窗口回推 set_min_elev（模拟卫星过境 el_spin 改动）-> 不触发回调、不循环
winA.set_min_elev(30.0)
assert abs(winA.canvas.min_elev - 30.0) < 1e-6
assert winA._el_a_spin.value() == 30
assert len(callsA) == 1, '来源回推不应再次触发地图回调（防循环）'
print('来源回推set_min_elev: OK  cbA仍=%s' % callsA)

# 4) set_stations 切换对方台 -> B 控件可见性联动
winB.show()
app.processEvents()
assert winB._el_b_spin.isVisible() is True   # 初始有对方台，控件可见
# 把对方台设为无效坐标（等价于用户清空）-> 控件隐藏
winB.set_stations(station_b=(0.0, 0.0, 0.0))
assert winB._el_b_spin.isVisible() is False
# 恢复有效坐标 -> 再次可见
winB.set_stations(station_b=b)
assert winB._el_b_spin.isVisible() is True
print('set_stations 可见性联动: OK')

winA.close()
winB.close()
print('\nALL OK')
