import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
import satellite_map_window as mw

app = QApplication([])

# 1) 卫星过境：无对方台 -> 标签与微调框都应隐藏
w1 = mw.open_map(None, [('TEST', None)], home=(39.9, 116.4, 50),
                 selected_name=None, source=None, min_elev=5.0)
w1.show()
app.processEvents()
assert w1._el_b_label.isVisible() is False, 'pass: B label should be hidden'
assert w1._el_b_spin.isVisible() is False, 'pass: B spin should be hidden'
print('卫星过境打开 -> 对方最低仰角 已隐藏: OK')

# 2) 通联预测：有对方台 -> 标签与微调框都应显示
w2 = mw.open_map(None, [('TEST', None)], home=(39.9, 116.4, 50),
                 station_b=(35.0, 139.0, 10), selected_name=None, source=None,
                 min_elev=5.0, min_elev_b=5.0)
w2.show()
app.processEvents()
assert w2._el_b_label.isVisible() is True, 'mutual: B label should be visible'
assert w2._el_b_spin.isVisible() is True, 'mutual: B spin should be visible'
print('通联预测打开 -> 对方最低仰角 已显示: OK')

# 3) 运行中去掉对方台 -> 标签随之隐藏
w2.set_stations(home=None, station_b=(0.0, 0.0, 0))
app.processEvents()
assert w2._el_b_label.isVisible() is False, 'after removing B -> hidden'
print('运行中移除对方台 -> 标签随之隐藏: OK')

print('ALL_OK')
